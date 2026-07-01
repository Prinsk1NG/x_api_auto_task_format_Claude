# -*- coding: utf-8 -*-
"""
x_api_auto_task_xai_xml.py  v17.0 (语义反重复 + type 枚举 + 硬数据校验)
Architecture: TwitterAPI.io -> PPLX/Tavily -> xAI SDK (Reasoning) + Memory Bank

v17.0 变更（基于 v16 两个月 60 天回测的 7 项新改进）:
[继承] v16 反重复护栏 / 新鲜度衰减 / 冷门兜底 / 硬数据兜底 / 中国专项 / TOP_PICKS 去重 / 记忆库扩容 / 日 diff
[新增 v17]
1. 🆕 语义级反重复护栏：注入 "TITLE + NARRATIVE 前 40 字" 指纹（解决 Agent 通用词护栏失效）
2. 🆕 THEME type 强制枚举 {new, shift, advance, milestone}，parser 白名单校验，非法值降级 shift
3. 🆕 硬数据"含具体金额"二次校验：正则抓 $X.YB / XX 亿元，_is_data_thin 阈值 200→400
4. 🆕 Musk 类账号"按推文内容"衰减：只有 AI 无关的推文才对 WHALE 权重打折
5. 🆕 记忆库 60 天轮转清理：整个账号最后一条 <60 天前就整体移除
6. 🆕 视觉升级：叙事转向/新叙事观察 标红加粗；推文正文加粗+默认色
7. 🆕 hr_manager v4 独立部署：淘汰-晋升解耦 + 45 天僵尸自动淡出
"""

import os
import re
import json
import time
import math
import base64
import random
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests
from requests.exceptions import ConnectionError, Timeout

# 🚨 引入官方 xAI SDK
from xai_sdk import Client
from xai_sdk.chat import user, system

TEST_MODE = os.getenv("TEST_MODE_ENV", "false").lower() == "true"

# ── 环境变量配置 ──────────────────────────────
SF_API_KEY          = os.getenv("SF_API_KEY", "")
XAI_API_KEY         = os.getenv("XAI_API_KEY", "")
IMGBB_API_KEY       = os.getenv("IMGBB_API_KEY", "")

PPLX_API_KEY        = os.getenv("PPLX_API_KEY", "")
TWITTERAPI_IO_KEY   = os.getenv("twitterapi_io_KEY", "")

TAVILY_KEYS = []
for suffix in ["", "_2", "_3", "_4", "_5"]:
    tk = os.getenv(f"TAVILY_API_KEY{suffix}")
    if tk and tk.strip(): TAVILY_KEYS.append(tk.strip())

def get_random_tavily_key():
    if not TAVILY_KEYS: return ""
    return random.choice(TAVILY_KEYS)

def D(b64_str):
    return base64.b64decode(b64_str).decode("utf-8")

URL_SF_IMAGE   = D("aHR0cHM6Ly9hcGkuc2lsaWNvbmZsb3cuY24vdjEvaW1hZ2VzL2dlbmVyYXRpb25z")
URL_IMGBB      = D("aHR0cHM6Ly9hcGkuaW1nYmIuY29tLzEvdXBsb2Fk")

# ── 基础配置与时间窗 ──────────────────────────────
BASE_URL = "https://api.twitterapi.io"
NOW_UTC = datetime.now(timezone.utc)
SINCE_24H = NOW_UTC - timedelta(days=1)
SINCE_TS = int(SINCE_24H.timestamp())
SINCE_DATE_STR = SINCE_24H.strftime("%Y-%m-%d")

# 🚨 动态读取外部名单系统
def load_account_list(filename):
    if not os.path.exists(filename): return []
    with open(filename, "r", encoding="utf-8") as f:
        return [line.strip().replace("@", "").lower() for line in f if line.strip() and not line.strip().startswith("#")]

WHALE_ACCOUNTS = load_account_list("whales.txt")
EXPERT_ACCOUNTS = load_account_list("experts.txt")

if TEST_MODE:
    WHALE_ACCOUNTS = WHALE_ACCOUNTS[:2]
    EXPERT_ACCOUNTS = EXPERT_ACCOUNTS[:4]

TARGET_SET = set(WHALE_ACCOUNTS + EXPERT_ACCOUNTS)

# ── v16/v17 近期上下文加载（供反重复护栏 + 新鲜度衰减使用）───────────
def load_recent_themes(days: int = 7) -> list:
    """v17 升级：读过去 N 天 <THEME> 完整结构，返回语义指纹（TITLE + NARRATIVE 前 40 字）。
    用于 Prompt 语义级反重复护栏——单靠关键词已无法拦截 Agent 这种通用词。"""
    out = []
    tz = timezone(timedelta(hours=8))
    base = datetime.now(tz).date()
    for i in range(1, days + 1):
        d = (base - timedelta(days=i)).strftime("%Y-%m-%d")
        fp = Path(f"data/{d}/daily_report.txt")
        if not fp.exists(): continue
        try:
            txt = fp.read_text(encoding="utf-8")
            # 抓每个 <THEME> 块内的 TITLE 与 NARRATIVE
            for tm in re.finditer(r'<THEME[^>]*>(.*?)</THEME>', txt, re.DOTALL):
                body = tm.group(1)
                t_m = re.search(r'<TITLE>(.*?)</TITLE>', body, re.DOTALL)
                n_m = re.search(r'<NARRATIVE>(.*?)</NARRATIVE>', body, re.DOTALL)
                if not t_m: continue
                title = t_m.group(1).strip()
                narr = (n_m.group(1).strip()[:40] + "...") if n_m else ""
                out.append(f"[{d}] {title} — {narr}" if narr else f"[{d}] {title}")
        except Exception as e:
            print(f"⚠️ [load_recent_themes] {d} 读取失败: {e}", flush=True)
    return out

def load_recent_used_authors(days: int = 7) -> dict:
    """读过去 N 天 daily_report.txt 中 account= 引用，统计每位作者被引用次数"""
    from collections import Counter
    counter = Counter()
    tz = timezone(timedelta(hours=8))
    base = datetime.now(tz).date()
    for i in range(1, days + 1):
        d = (base - timedelta(days=i)).strftime("%Y-%m-%d")
        fp = Path(f"data/{d}/daily_report.txt")
        if not fp.exists(): continue
        try:
            txt = fp.read_text(encoding="utf-8")
            for m in re.finditer(r'account=[\'"]([^\'"]+)[\'"]', txt, re.IGNORECASE):
                counter[m.group(1).replace("@", "").strip().lower()] += 1
        except Exception:
            pass
    return dict(counter)

def load_account_stats_safe() -> dict:
    """安全读取 account_stats.json（不存在或损坏时返回空字典）"""
    fp = Path("data/account_stats.json")
    if not fp.exists(): return {}
    try:
        return json.loads(fp.read_text(encoding="utf-8"))
    except Exception:
        return {}

# ── 渠道分发逻辑 ──────────────────────────────
def get_feishu_webhooks() -> list:
    urls = []
    if TEST_MODE:
        # 测试模式：优先读无后缀，fallback 到 _1
        for key in ["FEISHU_WEBHOOK_URL", "FEISHU_WEBHOOK_URL_1"]:
            url = os.getenv(key, "")
            if url:
                urls.append(url)
                break
    else:
        for suffix in ["", "_1", "_2", "_3"]:
            url = os.getenv(f"FEISHU_WEBHOOK_URL{suffix}", "")
            if url: urls.append(url)
    return urls

def get_wechat_webhooks() -> list:
    urls = []
    for key in ["JIJYUN_WEBHOOK_URL", "OriSG_WEBHOOK_URL", "OriCN_WEBHOOK_URL"]:
        url = os.getenv(key, "")
        if url: urls.append(url)
    return urls

def get_dates() -> tuple:
    tz = timezone(timedelta(hours=8))
    today = datetime.now(tz)
    yesterday = today - timedelta(days=1)
    return today.strftime("%Y-%m-%d"), yesterday.strftime("%Y-%m-%d")


# ==============================================================================
# 🎯 V15.0 对数打分引擎
# ==============================================================================
AI_KEYWORDS = [
    "ai", "llm", "agent", "model", "gpt", "release", "inference",
    "open-source", "agi", "claude", "openai", "anthropic", "gemini",
    "reasoning", "transformer", "fine-tune", "rlhf", "mcp", "context window",
    "scaling", "benchmark", "frontier", "safety", "alignment"
]

def unify_schema(t):
    author_obj = t.get("author", {})
    if isinstance(author_obj, str):
        author_handle = author_obj
    else:
        author_handle = author_obj.get("userName", "unknown")
    author_handle = author_handle.replace("@", "").strip().lower()

    created_at = t.get("createdAt", t.get("created_at", ""))
    created_ts = 0
    if created_at:
        try:
            created_ts = datetime.fromisoformat(created_at.replace('Z', '+00:00')).timestamp()
        except Exception:
            try:
                created_ts = datetime.strptime(created_at, "%a %b %d %H:%M:%S %z %Y").timestamp()
            except Exception:
                print(f"⚠️ [日期解析失败] 未知时间格式: {created_at}", flush=True)

    return {
        "id": str(t.get("id", t.get("tweet_id", "None"))),
        "text": t.get("text", t.get("full_text", "")),
        "author": author_handle,
        "created_ts": created_ts,
        "likes": int(t.get("likeCount", t.get("favorite_count", 0))),
        "replies": int(t.get("replyCount", t.get("reply_count", 0))),
        "quotes": int(t.get("quoteCount", t.get("quote_count", 0))),
        "deep_replies": []
    }

def score_and_filter(tweets):
    """对数打分 + v16 新鲜度衰减 + 冷门高产账号兜底
    打分公式：
    - 基础：log1p(likes)*10 + log1p(replies)*15 + log1p(quotes)*20
    - 身份：WHALE +200 / EXPERT +50（若近 2 日已被引用 ≥2 次 → 减半）
    - 主题：AI 关键词 +80
    - 兜底：累计 used_in_reports=0 且 total_tweets ≥ 5 的"沉默账号"+60
    - 惩罚：长度<15 字符 -200；@ 超过 5 次 -500
    """
    # v16 新增：加载近期上下文，用于动态调权
    recent_used = load_recent_used_authors(days=7)   # {author: 被引用次数}
    stats_all = load_account_stats_safe()

    unique_tweets = {}
    for t in tweets:
        t_id = t["id"]
        if not t_id or t_id == "None": continue
        if t_id in unique_tweets: continue

        # 对数打分：log(1+likes)*10 + log(1+replies)*15 + log(1+quotes)*20
        score = (math.log1p(t["likes"]) * 10
               + math.log1p(t["replies"]) * 15
               + math.log1p(t["quotes"]) * 20)

        text_lower = t["text"].lower()
        author = t["author"]

        # v17 ① 身份加权 + 按推文 AI 相关性的智能衰减
        # 回测发现：v16 的一刀切衰减把 Musk 6 月直接压到 0% —— 他仍在活跃发推，
        # 只是主题偏 SpaceX/政治。改为：只有该推文本身"不含 AI 关键词"时才对已高频账号衰减
        text_ai_relevant = any(kw in text_lower for kw in AI_KEYWORDS)

        if author in WHALE_ACCOUNTS:
            base_w = 200
            if recent_used.get(author, 0) >= 2 and not text_ai_relevant:
                base_w = 100   # 只有 AI 无关的推文才衰减，保留高价值 AI 推文
                print(f"  ⚖️ [新鲜度衰减] @{author} 近 7 日引用 {recent_used[author]} 次+推文非 AI 主题，WHALE 权重 200→100", flush=True)
            score += base_w
        elif author in EXPERT_ACCOUNTS:
            base_w = 50
            if recent_used.get(author, 0) >= 2 and not text_ai_relevant:
                base_w = 25
            score += base_w

        # AI 关键词加权
        if any(kw in text_lower for kw in AI_KEYWORDS):
            score += 80

        # v16 ② 冷门高产账号兜底加分
        acc_stats = stats_all.get(author, {})
        if (acc_stats.get("used_in_reports", 0) == 0
            and acc_stats.get("total_tweets", 0) >= 5):
            score += 60
            print(f"  🔦 [沉默账号兜底] @{author} 累计 {acc_stats.get('total_tweets')} 条 / 0 引用，+60 强制曝光", flush=True)

        # 质量惩罚
        clean_text = re.sub(r'https?://\S+|@\w+', '', text_lower).strip()
        if len(clean_text) < 15: score -= 200
        if t["text"].count('@') > 5: score -= 500

        t["score"] = max(0, round(score, 1))
        if t["score"] > 0 or t["likes"] > 15: unique_tweets[t_id] = t

    scored_list = sorted(unique_tweets.values(), key=lambda x: x["score"], reverse=True)

    # 每作者上限：whale 5条，expert 3条，其他 1条
    author_counts = {}
    final_capped = []
    for t in scored_list:
        author = t["author"]
        cap = 5 if author in WHALE_ACCOUNTS else (3 if author in EXPERT_ACCOUNTS else 1)
        if author_counts.get(author, 0) < cap:
            final_capped.append(t)
            author_counts[author] = author_counts.get(author, 0) + 1

    return final_capped

# ==============================================================================
# 🧩 宏观数据辅助
# ==============================================================================
def _pplx_query(prompt_text: str) -> str:
    """单次 Perplexity 调用，返回内容字符串（失败返回空串）"""
    if not PPLX_API_KEY: return ""
    try:
        headers = {"Authorization": f"Bearer {PPLX_API_KEY}", "Content-Type": "application/json"}
        payload = {"model": "sonar-pro", "messages": [{"role": "user", "content": prompt_text}], "temperature": 0.1}
        resp = requests.post("https://api.perplexity.ai/chat/completions", headers=headers, json=payload, timeout=60)
        if resp.status_code == 200:
            return resp.json()["choices"][0]["message"]["content"]
        print(f"  ⚠️ [Perplexity 报错] 状态码: {resp.status_code}, 详情: {resp.text}", flush=True)
    except Exception as e:
        print(f"  ⚠️ [Perplexity 异常]: {e}", flush=True)
    return ""

# v17 新增：正则抓"具体金额"，识别 $X.YB / XX 亿(美)元 等
_MONEY_RE = re.compile(
    r'\$\s?\d+(?:\.\d+)?\s?[BMK]?'                                        # $500M / $1.2B
    r'|\d+(?:\.\d+)?\s*(?:亿|万亿|千万|百万)\s*(?:美)?元'                 # 12 亿元 / 3.5 亿美元
    r'|(?:USD|EUR|CNY|RMB)\s?\d+(?:\.\d+)?\s?[BMK]',                     # USD500M
    re.IGNORECASE
)

def has_specific_money(text: str) -> bool:
    """v17: 判定文本里是否含≥1 个可识别的具体货币金额（融资/估值/并购必备）"""
    return bool(_MONEY_RE.search(text or ""))

def _is_data_thin(text: str) -> bool:
    """v17 升级：三重判定
    1) 文本 < 400 字（原 200 太宽松易被"看似有内容但没金额"的返回蒙混过关）
    2) 显式空窗措辞（无具体披露 / no major 等）
    3) 全文找不到任何具体金额（融资/并购题材必须要有金额，否则视为空窗）
    """
    if not text or len(text) < 400: return True
    fingerprints = ["无具体", "无具体披露", "未披露", "无权威", "暂无", "no specific", "no major", "not disclosed"]
    if any(fp in text.lower() if fp.startswith("no") else fp in text for fp in fingerprints):
        return True
    if not has_specific_money(text):
        print("  🔎 [_is_data_thin] 文本无具体金额，判定为空窗", flush=True)
        return True
    return False

def fetch_macro_with_perplexity() -> str:
    """v16: 24h 命中空 → 自动降级到 72h 硬数据兜底"""
    if not PPLX_API_KEY: return ""
    print("\n🕵️ [Perplexity] 24h 硬数据查询...", flush=True)
    primary_prompt = """你是顶级 AI 行业分析师。请仅检索过去 24 小时内 AI 行业的【硬核客观数据】。只抓取：1. 具体的融资金额与并购案（必须带美元金额）。2. GitHub上刚发布的AI开源项目或硬件（带 stars / 模型尺寸）。绝对禁止将Perplexity作为来源。如确实无数据请明确回答"24 小时内无具体融资披露"。"""
    primary = _pplx_query(primary_prompt)
    print(f"  ✅ Perplexity 24h 收集完毕 ({len(primary)} 字)", flush=True)

    if _is_data_thin(primary):
        print("  ⚠️ [硬数据空窗] 24h 数据不足，降级到 72h 兜底查询...", flush=True)
        fallback_prompt = """你是顶级 AI 行业分析师。过去 24 小时没有重大事件。请改为列出【过去 72 小时】影响最大的 3-5 起 AI 融资/并购，必须每条都给出具体美元金额、投资方、估值。如仍无，则列举过去一周 GitHub 趋势 AI 项目（含 stars 数）。绝对禁止把 Perplexity 作为来源。"""
        fb = _pplx_query(fallback_prompt)
        if fb:
            primary = (primary + "\n\n### [72h 兜底]\n" + fb) if primary else fb
            print(f"  ✅ 72h 兜底收集完毕 ({len(fb)} 字)", flush=True)
    return primary

def fetch_china_ai_with_perplexity() -> str:
    """v16 新增：中国 AI 公司专项查询，解决"中国视角"空话问题"""
    if not PPLX_API_KEY: return ""
    print("\n🐉 [Perplexity] 中国 AI 专项查询...", flush=True)
    prompt = """你是顶级 AI 行业分析师。请仅检索过去 48 小时内【中国 AI 公司】的【具体硬数据】，必须覆盖以下任意公司：DeepSeek、Kimi (月之暗面)、智谱 GLM、Qwen (通义)、字节豆包、腾讯混元、百度文心、商汤、Minimax、阶跃星辰、无问芯穹、面壁智能。
对每条数据，给出：1) 公司名 2) 事件类型（融资 / 开源发布 / 产品更新 / 监管 / Benchmark） 3) 具体数字（金额 / 参数 / 速度 / 价格）。如有海外大佬对中国 AI 的具体评价，也列出。
严禁泛泛而谈，无具体数据宁可不写。绝对禁止把 Perplexity 作为来源。"""
    text = _pplx_query(prompt)
    if text:
        print(f"  ✅ 中国 AI 专项收集完毕 ({len(text)} 字)", flush=True)
    return f"\n### [Perplexity 中国 AI 专项]\n{text}" if text else ""

def fetch_global_news_with_tavily() -> str:
    if not TAVILY_KEYS: return ""
    print(f"\n🌍 [Tavily] 扫描全网 AI 热点...", flush=True)
    try:
        url = "https://api.tavily.com/search"
        headers = {"Content-Type": "application/json"}
        payload = {"api_key": get_random_tavily_key(), "query": "AI startup funding, mergers and acquisitions, new AI hardware releases, and trending open-source AI GitHub projects globally in the last 24 hours", "search_depth": "advanced", "topic": "news", "days": 1, "include_answer": True}
        resp = requests.post(url, json=payload, headers=headers, timeout=45)

        if resp.status_code == 200:
            data = resp.json()
            print("  ✅ Tavily 扫描完毕。", flush=True)
            return f"### [Tavily 全网客观数据]\n" + data.get("answer", "")
        else:
            print(f"  ⚠️ [Tavily 报错] 状态码: {resp.status_code}, 详情: {resp.text}", flush=True)
    except Exception as e:
        print(f"  ⚠️ [Tavily 异常] 网络断开或超时: {e}", flush=True)
    return ""

# ==============================================================================
# 🧠 动态记忆库模块 (Memory Bank)
# ==============================================================================
MEMORY_FILE = Path("data/character_memory.json")

def load_memory():
    if MEMORY_FILE.exists():
        try:
            with open(MEMORY_FILE, 'r', encoding='utf-8') as f: return json.load(f)
        except: pass
    return {}

def save_memory(memory_data):
    MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(MEMORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(memory_data, f, ensure_ascii=False, indent=2)

def update_character_memory(parsed_data, today_str):
    memory = load_memory()
    count = 0
    for theme in parsed_data.get('themes', []):
        for tweet in theme.get('tweets', []):
            acc = tweet.get('account', '').lower().replace('@', '')
            content = tweet.get('content', '')
            if not acc or not content: continue

            if acc not in memory: memory[acc] = []
            # 去重：只比较内容部分（去掉日期前缀），防止同一条推文因日期不同被反复存入
            existing_contents = set()
            for e in memory[acc]:
                if isinstance(e, str) and "]: " in e:
                    existing_contents.add(e.split("]: ", 1)[1].strip()[:80])
                elif isinstance(e, dict):
                    existing_contents.add(e.get("content", "")[:80])
            if content.strip()[:80] not in existing_contents:
                new_entry = f"[{today_str}]: {content}"
                memory[acc].append(new_entry)
                # v16: 5 → 12 条，覆盖约 1 个月窗口，支持更深度的"叙事演变"判断
                memory[acc] = memory[acc][-12:]
                count += 1
    # v17 新增：60 天轮转清理——某个账号最新一条记忆距今 > 60 天 → 整个条目移除
    # 回测发现 5 月 v16 部署 34 天后仍有 21% 账号是"死记忆"，文件在膨胀
    try:
        tz = timezone(timedelta(hours=8))
        cutoff = (datetime.now(tz) - timedelta(days=60)).strftime("%Y-%m-%d")
        purged = []
        for acc in list(memory.keys()):
            dates = []
            for e in memory[acc]:
                if isinstance(e, str):
                    m = re.match(r'\[(\d{4}-\d{2}-\d{2})\]', e)
                    if m: dates.append(m.group(1))
                elif isinstance(e, dict) and e.get("date"):
                    dates.append(e["date"])
            if dates and max(dates) < cutoff:
                purged.append(acc)
                del memory[acc]
        if purged:
            print(f"[Memory 清理] 🗑️  已移除 {len(purged)} 个 60 天沉默账号: {', '.join('@'+p for p in purged[:5])}{'...' if len(purged)>5 else ''}", flush=True)
            count += 1  # 触发保存
    except Exception as e:
        print(f"⚠️ [Memory 清理异常] {e}", flush=True)

    if count > 0:
        save_memory(memory)
        print(f"\n[Memory] 🧠 已更新 {count} 条历史记忆存入账本。", flush=True)

# ==============================================================================
# 🚀 xAI 大模型调用与 XML 提示词
# ==============================================================================
def _build_xml_prompt(combined_jsonl: str, today_str: str, macro_info: str,
                     tavily_info: str, memory_context: str,
                     recent_themes_str: str = "") -> str:
    return f"""
你是一位顶级的 AI 行业一级市场投资分析师及新媒体主编。
你的任务是基于提供的【一手推特数据】、外部宏观新闻及大佬历史记忆，提炼出今日硅谷的【重大叙事动态】。

【封面图生成指令】：
你必须为 <COVER> 标签生成一个高度定制化的 prompt 属性：
1. 严禁千篇一律地使用"赛博朋克、霓虹、紫色"！
2. 构图原则：必须紧扣你为本次日报拟定的"爆款标题"。
   - 若标题涉及【硬件/机器人】：风格应为"超写实工业设计感 (Industrial Design, 8K, cinematic lighting)"。
   - 若标题涉及【模型开源/软件突破】：风格应为"科技极简或数据流艺术 (Minimalism, data visualization, neural nodes)"。
   - 若标题涉及【行业并购/商业策略】：风格应为"宏大的未来感建筑或战棋推演感 (Grand architectural metaphors, strategic map)"。
3. 提示词要求：100字左右的纯英文，包含具体的构图、材质、光影细节。

【核心任务：叙事挖掘】
不要做推文的搬运工。请像研究员一样，从推文中分析出：
1. 哪些是正在产生的【新叙事】（从未见过的新观点、新项目或新范式）。
2. 哪些叙事发生了【重大转向】（大佬打脸、共识瓦解或风向掉头）。
3. 哪些是原有叙事的【深度推进】（核心瓶颈突破、关键里程碑）。

🚨【防重复铁律 A：素材来源】(违反此规则等于任务失败)
- <TWEET> 标签里引用的推文必须且只能来自下方"X平台一手原始推文"数据，严禁引用历史记忆中的旧推文。
- 历史记忆的唯一用途是帮你判断叙事是"新的"还是"转向"或"推进"，以及提供态度对比的背景，绝不能作为引用素材。
- 如果今天的推文数据中没有某个话题的新内容，就不要写这个话题。宁可少写一个THEME，也不要用旧推文充数。

🚨【防重复铁律 B：7 日语义去重】(v17 升级，违反等于任务失败)
下面是过去 7 天已用主题的【语义指纹】（TITLE — NARRATIVE 前 40 字）。今天写主题时：
- 🎯 逐一比对：如果你想写的 THEME 与下面某个指纹在【核心论点 + 结论方向】两个维度都高度相似，判定为重复，必须换角度或直接删掉。
- ✅ 关键词碰巧一致（比如都含 "Agent" / "Codex" / "OpenAI"）不算重复——只要核心论点或立论方向不同即可。
- ✅ 相反：即使一个关键词都不共享，如果结论方向雷同（如都在讲"AI 让企业裁员"），也算重复。
- 🔍 输出前请在心里做一次自检："如果读者昨天刚看过报告，今天读这条 THEME 还有新收获吗？" 没有 → 删掉。
- 📉 第 1 主题严禁与过去 3 天的第 1 主题语义重复。
- 📊 如果今天信号确实不足以产生 4 个新颖主题，宁可只写 3 个 THEME，也不要凑数。

# 近 7 日主题指纹（按日期倒序）:
{recent_themes_str if recent_themes_str else "（无历史数据，首次运行）"}

🚨【历史记忆使用规则】(v16 新增)
- 仅当今天推文与历史记忆形成清晰的【延续 / 转向 / 反差】关系时引用；
- 单期 6 段 NARRATIVE 中，显式提及"历史记忆"的不得超过 3 段（即 ≤50%）；
- 严禁为了凑论证而强行拉历史。如不确定关系，不引用即可，留给推文本身说话。

【输出规模要求】(必须严格遵守)
- 必须生成 4 到 6 个 <THEME> 模块（信号充分时 6 个；不充分时宁可 3-4 个高质量）。
- 必须挑选 6 到 10 条最具代表性的原始推文放入 <TOP_PICKS>。
- 每个 THEME 必须引用至少 1-2 条相关推文。
- <INVESTMENT_RADAR> 必须包含 3-5 个 <ITEM>（不再是 2 个），尽可能带具体金额 / 数字。
- <RISK_CHINA_VIEW> 必须包含 2-3 个 <ITEM>，且 "中国 AI 评价" 类目下必须出现具体中国公司名（DeepSeek/Kimi/Qwen/智谱/字节/腾讯/百度…任意）。

🚨【THEME type 枚举约束】(v17 新增，违反等于任务失败)
每个 <THEME> 的 type 属性只能取以下 4 个值之一（严格小写，不允许任何变体）：
  - "new"       ：全新叙事（今日首次出现的观点/项目/范式）
  - "shift"     ：叙事转向（大佬打脸/共识瓦解/风向掉头）
  - "advance"   ：深度推进（既有叙事的核心突破/关键里程碑）
  - "milestone" ：重大里程碑（改变行业分水岭的事件、如 GPT-5.5 发布、Anthropic IPO）

⛔ 严禁使用 "deepening" / "advancement" / "depth" / "deep" / "deepen" 等任何变体——parser 会静默降级为 shift 导致读者看到错误标签。
📊 平衡性要求：单期 5-6 个 THEME 中，至少要有 1 个是 advance 或 milestone 类型（不能全是 new+shift，回测显示 advance/milestone 长期只占 6%，"深度推进"叙事被系统性忽略）。

🚨【TOP_PICKS 去重铁律】(v16 新增)
本节 6-10 条精选推文必须满足：
- 至少 50% 的推文是 THEME 中"未被引用"但同样有信息密度的补充信号（如：冷门技术细节、行业八卦、监管动态、个人哲思、产品发布的边角料）；
- 严禁与某个 THEME 的 <TWEET> 完全重复；引用同一作者时换不同语录；
- 优先挑选那些"虽然不构成完整 THEME，但单条价值很高"的推文。

【输出结构规范】(必须严格输出纯净XML)
<REPORT>
  <COVER title="10-20字爆款标题" prompt="[基于上述原则生成的定制化英文提示词]" insight="30字核心洞察"/>
  <PULSE>用一句话总结今日最核心的叙事流向。</PULSE>

  <THEMES>
    <THEME type="shift" emoji="⚔️">
      <TITLE>主题标题（如：从算力崇拜转向数据墙突破）</TITLE>
      <NARRATIVE>解析该叙事的演变逻辑（结合历史记忆点评其态度转变或冲突点）</NARRATIVE>
      <TWEET account="..." role="...">【严禁纯英文】以中文为主精练原文。🚨末尾附带真实互动数据（如 ❤️ 39190 | 💬 1904）</TWEET>
      <CONSENSUS>行业内已形成的最新共识</CONSENSUS>
      <DIVERGENCE>目前大佬们最激烈的争论点或未解之谜</DIVERGENCE>
    </THEME>

    <THEME type="new" emoji="🌱">
      <TITLE>主题标题（如：AI原生硬件的第三条道路）</TITLE>
      <NARRATIVE>定义新叙事的内涵及它试图解决的底层问题</NARRATIVE>
      <TWEET account="..." role="...">...</TWEET>
      <OUTLOOK>该叙事对未来 6-12 个月行业格局的影响</OUTLOOK>
      <OPPORTUNITY>一级市场可能的投资机会或应用切入点</OPPORTUNITY>
      <RISK>该新概念是否为短期泡沫或存在技术硬伤</RISK>
    </THEME>

    <THEME type="advance" emoji="🚀">
      <TITLE>主题标题（如：多模态模型突破 1M token 上下文）</TITLE>
      <NARRATIVE>说明既有叙事的关键突破点：技术瓶颈如何被打破、里程碑数据</NARRATIVE>
      <TWEET account="..." role="...">...</TWEET>
      <CONSENSUS>此次推进已形成的行业新共识</CONSENSUS>
      <DIVERGENCE>推进后还未解决的技术/商业争议</DIVERGENCE>
    </THEME>

    <THEME type="milestone" emoji="🏆">
      <TITLE>主题标题（如：Anthropic 首次盈利：AI 商业化拐点）</TITLE>
      <NARRATIVE>说明为什么这是行业分水岭事件（改变什么、影响谁）</NARRATIVE>
      <TWEET account="..." role="...">...</TWEET>
      <CONSENSUS>市场对该里程碑的一致解读</CONSENSUS>
      <DIVERGENCE>是否有质疑声音或后续风险争论</DIVERGENCE>
    </THEME>

    </THEMES>

  <INVESTMENT_RADAR>
    <ITEM category="投融资快讯">...</ITEM>
    <ITEM category="VC views">...</ITEM>
  </INVESTMENT_RADAR>

  <RISK_CHINA_VIEW>
    <ITEM category="中国 AI 评价">...</ITEM>
    <ITEM category="全球映射">...</ITEM>
  </RISK_CHINA_VIEW>

  <TOP_PICKS>
    <TWEET account="..." role="...">流畅中文精译。🚨末尾附带真实互动数据</TWEET>
    <TWEET account="..." role="...">...</TWEET>
    <TWEET account="..." role="...">...</TWEET>
  </TOP_PICKS>
</REPORT>

# 🧠 本期上榜大佬的近期历史记忆:
{memory_context if memory_context else "无历史记录"}

# 外部宏观背景:
{macro_info}
{tavily_info}

# X平台一手原始推文 (这是你的主要分析素材，请深入挖掘):
{combined_jsonl}

# 日期: {today_str}
"""

def llm_call_xai(combined_jsonl: str, today_str: str, macro_info: str, tavily_info: str,
                memory_context: str, recent_themes_str: str = "") -> str:
    api_key = XAI_API_KEY.strip()
    if not api_key:
        print("❌ [xAI 报错] XAI_API_KEY 为空！", flush=True)
        return ""

    data = combined_jsonl[:100000] if len(combined_jsonl) > 100000 else combined_jsonl
    prompt = _build_xml_prompt(data, today_str, macro_info, tavily_info, memory_context, recent_themes_str)

    model_name = "grok-4.20-0309-reasoning"
    print(f"\n[xAI] Requesting {model_name} via Official SDK...", flush=True)
    client = Client(api_key=api_key)

    for attempt in range(1, 4):
        try:
            chat = client.chat.create(model=model_name)
            chat.append(system("You are a professional analytical bot. You strictly output in XML format as instructed."))
            chat.append(user(prompt))

            result = chat.sample().content.strip()

            result = re.sub(r'<think>.*?</think>', '', result, flags=re.DOTALL | re.IGNORECASE).strip()
            result = re.sub(r'^`{3}(?:xml|jsonl|json)?\n', '', result, flags=re.MULTILINE)
            result = re.sub(r'^`{3}\n?', '', result, flags=re.MULTILINE)

            print(f"[xAI] OK Response received ({len(result)} chars)", flush=True)
            return result
        except Exception as e:
            print(f"⚠️ [xAI 异常] Attempt {attempt} failed: {e}", flush=True)
            time.sleep(2 ** attempt)

    print("❌ [xAI 彻底失败] 所有重试均告失败。", flush=True)
    return ""

# v17 新增：THEME type 白名单
ALLOWED_THEME_TYPES = {"new", "shift", "advance", "milestone"}
# 常见 LLM 自创变体的兼容映射（尽量还原语义，而不是一律 shift）
THEME_TYPE_ALIAS = {
    "deepening": "advance", "advancement": "advance", "depth": "advance",
    "deep": "advance", "deepen": "advance", "progress": "advance",
    "landmark": "milestone", "breakthrough": "milestone",
    "novel": "new", "emerging": "new",
    "pivot": "shift", "turn": "shift", "reversal": "shift",
}

def parse_llm_xml(xml_text: str) -> dict:
    data = {"cover": {"title": "", "prompt": "", "insight": ""}, "pulse": "", "themes": [], "investment_radar": [], "risk_china_view": [], "top_picks": []}
    if not xml_text: return data

    cover_match = re.search(r'<COVER\s+title=[\'"""](.*?)[\'"""]\s+prompt=[\'"""](.*?)[\'"""]\s+insight=[\'"""](.*?)[\'"""]\s*/?>', xml_text, re.IGNORECASE | re.DOTALL)
    if not cover_match:
        cover_match = re.search(r'<COVER\s+title="(.*?)"\s+prompt="(.*?)"\s+insight="(.*?)"\s*/?>', xml_text, re.IGNORECASE | re.DOTALL)
    if cover_match:
        data["cover"] = {"title": cover_match.group(1).strip(), "prompt": cover_match.group(2).strip(), "insight": cover_match.group(3).strip()}

    pulse_match = re.search(r'<PULSE>(.*?)</PULSE>', xml_text, re.IGNORECASE | re.DOTALL)
    if pulse_match: data["pulse"] = pulse_match.group(1).strip()

    # v17 修复隐藏 bug：原 regex '<THEME([^>]*)>' 会误匹配 '<THEMES>'（多吞一个 S），
    # 导致 60 天回测里第 1 个 THEME 的 type 全部丢失、默认降级 shift。加空格边界。
    for theme_match in re.finditer(r'<THEME(\s[^>]*)?>(.*?)</THEME>', xml_text, re.IGNORECASE | re.DOTALL):
        attrs = theme_match.group(1) or ""
        theme_body = theme_match.group(2)

        type_m = re.search(r'type\s*=\s*[\'"""](.*?)[\'"""]', attrs, re.IGNORECASE)
        emoji_m = re.search(r'emoji\s*=\s*[\'"""](.*?)[\'"""]', attrs, re.IGNORECASE)
        raw_type = type_m.group(1).strip().lower() if type_m else "shift"
        # v17 白名单校验：非法 type 优先按语义别名回落，其次归 shift
        if raw_type in ALLOWED_THEME_TYPES:
            theme_type = raw_type
        elif raw_type in THEME_TYPE_ALIAS:
            theme_type = THEME_TYPE_ALIAS[raw_type]
            print(f"  ⚠️ [parser] THEME type '{raw_type}' 通过别名映射到 '{theme_type}'", flush=True)
        else:
            theme_type = "shift"
            if raw_type: print(f"  ⚠️ [parser] THEME type '{raw_type}' 未知，降级为 shift", flush=True)
        emoji = emoji_m.group(1).strip() if emoji_m else "🔥"

        t_tag = re.search(r'<TITLE>(.*?)</TITLE>', theme_body, re.IGNORECASE | re.DOTALL)
        theme_title = t_tag.group(1).strip() if t_tag else ""

        narrative_match = re.search(r'<NARRATIVE>(.*?)</NARRATIVE>', theme_body, re.IGNORECASE | re.DOTALL)
        narrative = narrative_match.group(1).strip() if narrative_match else ""

        tweets = []
        for t_match in re.finditer(r'<TWEET\s+account=[\'"""](.*?)[\'"""]\s+role=[\'"""](.*?)[\'"""]>(.*?)</TWEET>', theme_body, re.IGNORECASE | re.DOTALL):
            tweets.append({"account": t_match.group(1).strip(), "role": t_match.group(2).strip(), "content": t_match.group(3).strip()})

        con_match = re.search(r'<CONSENSUS>(.*?)</CONSENSUS>', theme_body, re.IGNORECASE | re.DOTALL)
        consensus = con_match.group(1).strip() if con_match else ""
        div_match = re.search(r'<DIVERGENCE>(.*?)</DIVERGENCE>', theme_body, re.IGNORECASE | re.DOTALL)
        divergence = div_match.group(1).strip() if div_match else ""

        out_match = re.search(r'<OUTLOOK>(.*?)</OUTLOOK>', theme_body, re.IGNORECASE | re.DOTALL)
        outlook = out_match.group(1).strip() if out_match else ""
        opp_match = re.search(r'<OPPORTUNITY>(.*?)</OPPORTUNITY>', theme_body, re.IGNORECASE | re.DOTALL)
        opportunity = opp_match.group(1).strip() if opp_match else ""
        risk_match = re.search(r'<RISK>(.*?)</RISK>', theme_body, re.IGNORECASE | re.DOTALL)
        risk = risk_match.group(1).strip() if risk_match else ""

        data["themes"].append({
            "type": theme_type, "emoji": emoji, "title": theme_title, "narrative": narrative, "tweets": tweets,
            "consensus": consensus, "divergence": divergence, "outlook": outlook, "opportunity": opportunity, "risk": risk
        })

    def extract_items(tag_name, target_list):
        block_match = re.search(rf'<{tag_name}>(.*?)</{tag_name}>', xml_text, re.IGNORECASE | re.DOTALL)
        if block_match:
            for item in re.finditer(r'<ITEM\s+category=[\'"""](.*?)[\'"""]>(.*?)</ITEM>', block_match.group(1), re.IGNORECASE | re.DOTALL):
                target_list.append({"category": item.group(1).strip(), "content": item.group(2).strip()})

    extract_items("INVESTMENT_RADAR", data["investment_radar"])
    extract_items("RISK_CHINA_VIEW", data["risk_china_view"])

    picks_match = re.search(r'<TOP_PICKS>(.*?)</TOP_PICKS>', xml_text, re.IGNORECASE | re.DOTALL)
    if picks_match:
        for t_match in re.finditer(r'<TWEET\s+account=[\'"""](.*?)[\'"""]\s+role=[\'"""](.*?)[\'"""]>(.*?)</TWEET>', picks_match.group(1), re.IGNORECASE | re.DOTALL):
            data["top_picks"].append({"account": t_match.group(1).strip(), "role": t_match.group(2).strip(), "content": t_match.group(3).strip()})

    return data

# ==============================================================================
# 🚀 渲染与生图模块
# ==============================================================================
def render_feishu_card(parsed_data: dict, today_str: str):
    webhooks = get_feishu_webhooks()
    if not webhooks or not parsed_data.get("pulse"): return
    elements = []
    elements.append({"tag": "markdown", "content": f"**▌ ⚡️ 今日看板 (The Pulse)**\n<font color='grey'>{parsed_data['pulse']}</font>"})
    elements.append({"tag": "hr"})

    if parsed_data["themes"]:
        elements.append({"tag": "markdown", "content": "**▌ 🧠 深度叙事追踪**"})
        for idx, theme in enumerate(parsed_data["themes"]):
            theme_md = f"**{theme['emoji']} {theme['title']}**\n"
            # v17：4 种 type 各自的中文标签
            _TYPE_LABEL = {
                "new": "🔭 新叙事观察",
                "shift": "💡 叙事转向",
                "advance": "🚀 深度推进",
                "milestone": "🏆 重大里程碑",
            }
            prefix = _TYPE_LABEL.get(theme.get("type", "shift"), "💡 叙事转向")
            # v16.1 视觉升级 ①：标签标红加粗，narrative 内容斜体
            theme_md += f"<font color='red'>**{prefix}：**</font><font color='grey'>*{theme['narrative']}*</font>\n"
            for t in theme["tweets"]:
                # v16.1 视觉升级 ②：推文正文加粗，弃用 grey 让飞书用默认色（深色更清晰）
                theme_md += f"🗣️ **@{t['account']} | {t['role']}**\n**\u201c{t['content']}\u201d**\n"
            if theme.get("type") == "new":
                if theme.get("outlook"): theme_md += f"<font color='blue'>**🔮 解读与展望：**</font> {theme['outlook']}\n"
                if theme.get("opportunity"): theme_md += f"<font color='green'>**🎯 潜在机会：**</font> {theme['opportunity']}\n"
                if theme.get("risk"): theme_md += f"<font color='red'>**⚠️ 潜在风险：**</font> {theme['risk']}\n"
            else:
                if theme.get("consensus"): theme_md += f"<font color='red'>**🔥 核心共识：**</font> {theme['consensus']}\n"
                if theme.get("divergence"): theme_md += f"<font color='red'>**⚔️ 最大分歧：**</font> {theme['divergence']}\n"
            elements.append({"tag": "markdown", "content": theme_md.strip()})
            if idx < len(parsed_data["themes"]) - 1: elements.append({"tag": "hr"})
        elements.append({"tag": "hr"})

    def add_list_section(title, icon, items):
        if not items: return
        content = f"**▌ {icon} {title}**\n\n"
        for item in items:
            content += f"👉 **{item['category']}**：<font color='grey'>{item['content']}</font>\n"
        elements.append({"tag": "markdown", "content": content.strip()})
        elements.append({"tag": "hr"})

    add_list_section("资本与估值雷达", "💰", parsed_data["investment_radar"])
    add_list_section("风险与中国视角", "📊", parsed_data["risk_china_view"])

    if parsed_data["top_picks"]:
        picks_md = "**▌ 📣 今日精选推文 (Top 5 Picks)**\n"
        for t in parsed_data["top_picks"]:
            # v16.1 视觉升级 ③：TOP_PICKS 推文与 THEME 内保持一致
            picks_md += f"\n🗣️ **@{t['account']} | {t['role']}**\n**\u201c{t['content']}\u201d**\n"
        elements.append({"tag": "markdown", "content": picks_md.strip()})

    card_payload = {
        "msg_type": "interactive",
        "card": {
            "config": {"wide_screen_mode": True, "enable_forward": True},
            "header": {"title": {"content": f"昨晚硅谷在聊啥 | {today_str}", "tag": "plain_text"}, "template": "blue"},
            "elements": elements + [{"tag": "note", "elements": [{"tag": "plain_text", "content": "Powered by TwitterAPI.io + xAI + Memory | v15.0"}]}]
        }
    }
    for url in webhooks:
        try:
            resp = requests.post(url, json=card_payload, timeout=20)
            if resp.status_code != 200:
                print(f"⚠️ [飞书 Webhook 报错] 状态码: {resp.status_code}, 返回: {resp.text}", flush=True)
        except Exception as e:
            print(f"⚠️ [飞书网络异常] 推送断开: {e}", flush=True)

def render_wechat_html(parsed_data: dict, cover_url: str = "") -> str:
    html_lines = []
    if cover_url: html_lines.append(f'<p style="text-align:center;margin:0 0 16px 0;"><img src="{cover_url}" style="max-width:100%;border-radius:8px;" /></p>')
    def make_h3(title): return f'<h3 style="margin:24px 0 12px 0;font-size:18px;border-left:4px solid #4A90E2;padding-left:10px;color:#2c3e50;font-weight:bold;">{title}</h3>'
    def make_quote(content): return f'<div style="background:#f8f9fa;border-left:4px solid #8c98a4;padding:10px 14px;color:#555;font-size:15px;border-radius:0 4px 4px 0;margin:6px 0 10px 0;line-height:1.6;">{content}</div>'

    html_lines.append(make_h3("⚡️ 今日看板 (The Pulse)"))
    html_lines.append(make_quote(parsed_data.get('pulse', '')))

    if parsed_data["themes"]:
        html_lines.append(make_h3("🧠 深度叙事追踪"))
        for idx, theme in enumerate(parsed_data["themes"]):
            if idx > 0: html_lines.append('<hr style="border:none;border-top:1px solid #cbd5e1;margin:32px 0 24px 0;"/>')
            html_lines.append(f'<p style="font-weight:bold;font-size:16px;color:#1e293b;margin:16px 0 8px 0;">{theme["emoji"]} {theme["title"]}</p>')

            if theme.get("type") == "new": html_lines.append(f'<div style="background:#f4f8fb; padding:10px 12px; border-radius:6px; margin:0 0 8px 0; font-size:14px; color:#2c3e50;"><strong>🔭 新叙事观察：</strong>{theme["narrative"]}</div>')
            else: html_lines.append(f'<div style="background:#f4f8fb; padding:10px 12px; border-radius:6px; margin:0 0 8px 0; font-size:14px; color:#2c3e50;"><strong>💡 叙事转向：</strong>{theme["narrative"]}</div>')

            for t in theme["tweets"]:
                html_lines.append(f'<p style="margin:8px 0 2px 0;font-size:14px;font-weight:bold;color:#2c3e50;">🗣️ @{t["account"]} <span style="color:#94a3b8;font-weight:normal;">| {t["role"]}</span></p>')
                html_lines.append(make_quote(f'\u201c{t["content"]}\u201d'))

            if theme.get("type") == "new":
                if theme.get("outlook"): html_lines.append(f'<p style="margin:6px 0; font-size:15px; line-height:1.6; background:#eef2ff; padding: 8px 12px; border-radius: 4px;"><strong style="color:#4f46e5;">🔮 解读与展望：</strong>{theme["outlook"]}</p>')
                if theme.get("opportunity"): html_lines.append(f'<p style="margin:6px 0; font-size:15px; line-height:1.6; background:#f0fdf4; padding: 8px 12px; border-radius: 4px;"><strong style="color:#16a34a;">🎯 潜在机会：</strong>{theme["opportunity"]}</p>')
                if theme.get("risk"): html_lines.append(f'<p style="margin:6px 0; font-size:15px; line-height:1.6; background:#fef2f2; padding: 8px 12px; border-radius: 4px;"><strong style="color:#dc2626;">⚠️ 潜在风险：</strong>{theme["risk"]}</p>')
            else:
                if theme.get("consensus"): html_lines.append(f'<p style="margin:6px 0; font-size:15px; line-height:1.6; background:#fff5f5; padding: 8px 12px; border-radius: 4px;"><strong style="color:#d35400;">🔥 核心共识：</strong>{theme["consensus"]}</p>')
                if theme.get("divergence"): html_lines.append(f'<p style="margin:6px 0; font-size:15px; line-height:1.6; background:#fff5f5; padding: 8px 12px; border-radius: 4px;"><strong style="color:#d35400;">⚔️ 最大分歧：</strong>{theme["divergence"]}</p>')

    def make_list_section(title, items):
        if not items: return
        html_lines.append(make_h3(title))
        for item in items: html_lines.append(f'<p style="margin:10px 0;font-size:15px;line-height:1.6;">👉 <strong style="color:#2c3e50;">{item["category"]}：</strong><span style="color:#333;">{item["content"]}</span></p>')

    make_list_section("💰 资本与估值雷达", parsed_data["investment_radar"])
    make_list_section("📊 风险与中国视角", parsed_data["risk_china_view"])

    if parsed_data["top_picks"]:
        html_lines.append(make_h3("📣 今日精选推文 (Top 5 Picks)"))
        for t in parsed_data["top_picks"]:
             html_lines.append(f'<p style="margin:12px 0 4px 0;font-size:14px;font-weight:bold;color:#2c3e50;">🗣️ @{t["account"]} <span style="color:#94a3b8;font-weight:normal;">| {t["role"]}</span></p>')
             html_lines.append(make_quote(f'\u201c{t["content"]}\u201d'))
    return "".join(html_lines)

def generate_cover_image(prompt):
    if not SF_API_KEY or not prompt:
        return ""
    try:
        resp = requests.post(URL_SF_IMAGE, headers={"Authorization": f"Bearer {SF_API_KEY}", "Content-Type": "application/json"}, json={"model": "Kwai-Kolors/Kolors", "prompt": prompt, "image_size": "1024x576"}, timeout=60)
        if resp.status_code == 200:
            print("  🎨 硅基流动生图成功！", flush=True)
            return resp.json().get("images", [{}])[0].get("url") or resp.json().get("data", [{}])[0].get("url")
        else:
            print(f"  ⚠️ [SiliconFlow 生图报错] 状态码: {resp.status_code}, 详情: {resp.text}", flush=True)
    except Exception as e:
        print(f"  ⚠️ [SiliconFlow 网络异常] 生图请求断开: {e}", flush=True)
    return ""

def upload_to_imgbb_via_url(sf_url):
    if not IMGBB_API_KEY or not sf_url: return sf_url
    try:
        img_b64 = base64.b64encode(requests.get(sf_url, timeout=30).content).decode("utf-8")
        resp = requests.post(URL_IMGBB, data={"key": IMGBB_API_KEY, "image": img_b64}, timeout=45)
        if resp.status_code == 200:
            return resp.json()["data"]["url"]
        else:
            print(f"  ⚠️ [ImgBB 报错] 图床上传失败: {resp.text}", flush=True)
    except Exception as e:
        print(f"  ⚠️ [ImgBB 异常] 上传断开: {e}", flush=True)
    return sf_url

def push_to_wechat(html_content, title, cover_url=""):
    webhooks = get_wechat_webhooks()
    if not webhooks: return
    payload = {"title": title, "author": "Prinski", "html_content": html_content, "cover_jpg": cover_url}
    for url in webhooks:
        try:
            resp = requests.post(url, json=payload, timeout=30)
            if resp.status_code == 200:
                print(f"  ✅ [微信推送成功] Sent to {url.split('//')[-1][:15]}...", flush=True)
            else:
                print(f"  ⚠️ [微信 Webhook 报错] 状态码 {resp.status_code}, 详情: {resp.text}", flush=True)
        except Exception as e:
            print(f"  ⚠️ [微信推送异常] 网络断开: {e}", flush=True)

def save_daily_data(today_str: str, post_objects: list, report_text: str):
    data_dir = Path(f"data/{today_str}")
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "combined.txt").write_text("\n".join(json.dumps(obj, ensure_ascii=False) for obj in post_objects), encoding="utf-8")
    if report_text: (data_dir / "daily_report.txt").write_text(report_text, encoding="utf-8")

def generate_daily_diff(today_str: str, parsed_data: dict) -> str:
    """v16 新增：今日 vs 昨日 TITLE diff，方便运营快速判断叙事是否真在演化"""
    today_titles = [t.get("title", "").strip() for t in parsed_data.get("themes", []) if t.get("title")]
    if not today_titles: return ""

    tz = timezone(timedelta(hours=8))
    yesterday = (datetime.strptime(today_str, "%Y-%m-%d").replace(tzinfo=tz) - timedelta(days=1)).strftime("%Y-%m-%d")
    yfp = Path(f"data/{yesterday}/daily_report.txt")
    if not yfp.exists():
        return f"\n📊 [Daily Diff] 昨日({yesterday})无报告，跳过 diff。\n"

    y_titles = [m.group(1).strip() for m in re.finditer(r'<TITLE>(.*?)</TITLE>', yfp.read_text(encoding="utf-8"))]

    # 简单关键词重叠判定：共享 ≥2 个 2+字中文 token 视为"延续"
    def tokens(s):
        s = re.sub(r'[、，。：；！？\s\-:,；]+', ' ', s)
        return set(re.findall(r'[A-Za-z]{2,}|[一-鿿]{2,4}', s))

    new_t, continued_t = [], []
    for tt in today_titles:
        is_continued = False
        for yt in y_titles:
            shared = tokens(tt) & tokens(yt)
            if len(shared) >= 2:
                continued_t.append((tt, yt, shared))
                is_continued = True
                break
        if not is_continued:
            new_t.append(tt)

    dropped_t = []
    today_tokens_union = set().union(*[tokens(t) for t in today_titles]) if today_titles else set()
    for yt in y_titles:
        if len(tokens(yt) & today_tokens_union) < 2:
            dropped_t.append(yt)

    lines = ["\n📊 [Daily Diff] 今日 vs 昨日叙事演化"]
    lines.append(f"  ✨ 新出现({len(new_t)}): " + " | ".join(new_t) if new_t else "  ✨ 新出现: 无")
    lines.append(f"  🔁 延续({len(continued_t)}): " + " | ".join(f"{ct[0]} ← {ct[1]}" for ct in continued_t) if continued_t else "  🔁 延续: 无")
    lines.append(f"  💨 消失({len(dropped_t)}): " + " | ".join(dropped_t) if dropped_t else "  💨 消失: 无")
    msg = "\n".join(lines)
    print(msg, flush=True)
    return msg

def update_account_stats(final_feed: list, parsed_data: dict):
    """只统计名单内的账号，杜绝噪音污染"""
    stats_file = Path("data/account_stats.json")
    stats = {}
    if stats_file.exists():
        try: stats = json.loads(stats_file.read_text(encoding="utf-8"))
        except: pass

    today_str = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d")
    used_accounts = set()
    for theme in parsed_data.get("themes", []):
        for t in theme.get("tweets", []): used_accounts.add(t.get("account", "").lower())
    for t in parsed_data.get("top_picks", []): used_accounts.add(t.get("account", "").lower())

    for t in final_feed:
        acc = t.get("a", "unknown").lower()
        # 只统计名单内的账号
        if acc not in TARGET_SET: continue
        if acc not in stats: stats[acc] = {"fetched_days": 0, "total_tweets": 0, "used_in_reports": 0, "last_active": ""}
        stats[acc]["total_tweets"] += 1
        stats[acc]["last_active"] = today_str

    for acc in used_accounts:
        acc_clean = acc.replace("@", "")
        if acc_clean in stats: stats[acc_clean]["used_in_reports"] += 1

    stats_file.parent.mkdir(parents=True, exist_ok=True)
    stats_file.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")

# ==============================================================================
# 🔄 带翻页的 Twitter 搜索
# ==============================================================================
def search_with_pagination(query: str, query_type: str = "Latest", max_pages: int = 2) -> list:
    """调用 TwitterAPI.io advanced_search，支持翻页（最多 max_pages 页）"""
    all_tweets = []
    cursor = None

    for page in range(max_pages):
        params = {"query": query, "queryType": query_type}
        if cursor:
            params["cursor"] = cursor

        try:
            resp = requests.get(
                f"{BASE_URL}/twitter/tweet/advanced_search",
                headers={"X-API-Key": TWITTERAPI_IO_KEY},
                params=params,
                timeout=25
            )
            if resp.status_code == 200:
                data = resp.json()
                # 🔍 诊断：打印 API 返回的顶层 key 和前 200 字符（仅首页首批）
                if page == 0 and not all_tweets:
                    print(f"  🔍 [API诊断] keys={list(data.keys())}, raw={str(data)[:300]}", flush=True)
                tweets = data.get("tweets", [])
                if not tweets:
                    break

                valid_c, old_c = 0, 0
                for t in tweets:
                    ct = unify_schema(t)
                    if ct["created_ts"] >= SINCE_TS:
                        all_tweets.append(ct)
                        valid_c += 1
                    else:
                        old_c += 1

                if valid_c == 0 and old_c > 0:
                    # 已经翻到 24 小时前的推文了，没必要继续翻页
                    break

                # 检查是否有下一页
                next_cursor = data.get("next_cursor", data.get("cursor", ""))
                if not next_cursor or next_cursor == cursor:
                    break
                cursor = next_cursor

                if page < max_pages - 1:
                    time.sleep(1)
            else:
                print(f"❌ [TwitterAPI 报错] HTTP {resp.status_code}: {resp.text}", flush=True)
                break
        except Exception as e:
            print(f"⚠️ [TwitterAPI 网络异常] 抓取断开: {e}", flush=True)
            break

    return all_tweets

# ==============================================================================
# 🚀 MAIN 入口
# ==============================================================================
def main():
    print("=" * 60, flush=True)
    print(f"昨晚硅谷在聊啥 v15.0 (精简名单 + 对数打分 + 翻页版)", flush=True)
    print(f"Whales: {len(WHALE_ACCOUNTS)} | Experts: {len(EXPERT_ACCOUNTS)} | Total: {len(TARGET_SET)}", flush=True)
    print("=" * 60, flush=True)

    if not TWITTERAPI_IO_KEY or not TARGET_SET:
        print("❌ 错误: 未配置 API KEY 或本地 txt 名单为空", flush=True)
        return

    today_str, _ = get_dates()

    # ---------------------------------------------------------
    # 🎯 步骤 1: 只抓原创推文，带翻页（砍掉回响查询）
    # ---------------------------------------------------------
    print(f"\n🚀 开始抓取 {len(TARGET_SET)} 位核心节点的最新动态...", flush=True)
    all_raw = []
    acc_list = list(TARGET_SET)

    # Whale 单独抓（翻2页，确保不漏）
    print(f"  🔍 [诊断] SINCE_DATE_STR={SINCE_DATE_STR}, SINCE_TS={SINCE_TS}", flush=True)
    for whale in WHALE_ACCOUNTS:
        q = f"from:{whale} since_time:{SINCE_TS} -filter:retweets"
        print(f"  🔍 [Query] {q}", flush=True)
        tweets = search_with_pagination(q, "Latest", max_pages=2)
        all_raw.extend(tweets)
        if tweets:
            print(f"  🐳 @{whale}: {len(tweets)} 条", flush=True)
        else:
            print(f"  🐳 @{whale}: 0 条", flush=True)
        time.sleep(0.5)

    # Expert 按批次抓（每批10人，翻1页）
    for i in range(0, len(EXPERT_ACCOUNTS), 10):
        chunk = EXPERT_ACCOUNTS[i:i+10]
        q = "(" + " OR ".join([f"from:{a}" for a in chunk]) + f") since_time:{SINCE_TS} -filter:retweets"
        tweets = search_with_pagination(q, "Latest", max_pages=1)
        all_raw.extend(tweets)
        print(f"  📡 批次 {i//10+1}: {len(tweets)} 条 ({', '.join(chunk[:3])}...)", flush=True)
        time.sleep(1.5)

    if not all_raw:
        print("❌ [终极警告] 本次运行未能获取任何有效数据！程序终止。", flush=True)
        return

    print(f"\n📊 原始抓取总计: {len(all_raw)} 条推文", flush=True)
    top_feed = score_and_filter(all_raw)
    tier_1 = top_feed[:15]
    tier_2 = top_feed[15:75]

    # ---------------------------------------------------------
    # 🔍 步骤 2: 只对 Top 5 抓神回复（从15缩减到5）
    # ---------------------------------------------------------
    print(f"\n[深挖] 正在为 Top 5 高分话题抓取神回复...", flush=True)
    for t in tier_1[:5]:
        try:
            resp3 = requests.get(f"{BASE_URL}/twitter/tweet/replies", headers={"X-API-Key": TWITTERAPI_IO_KEY}, params={"tweetId": t["id"]}, timeout=15)
            if resp3.status_code == 200:
                d3 = resp3.json()
                if d3 and d3.get("tweets"):
                    replies = sorted([unify_schema(r) for r in d3["tweets"]], key=lambda x: x["likes"], reverse=True)
                    t["deep_replies"] = replies[:3]
            else:
                print(f"❌ [TwitterAPI 报错] 评论钻取 HTTP {resp3.status_code}: {resp3.text}", flush=True)
        except Exception as e:
            print(f"⚠️ [TwitterAPI 网络异常] 评论抓取断开: {e}", flush=True)
        time.sleep(1)

    formatted_feed = []
    for t in tier_1:
        reply_strs = [f"[神回复 @{r['author']}]: {r['text'][:150]} (❤️ {r['likes']})" for r in t["deep_replies"]]
        s_text = t["text"] + ("\n\n" + "\n".join(reply_strs) if reply_strs else "")
        formatted_feed.append({"a": t["author"], "tweet_id": t["id"], "l": t["likes"], "r": t["replies"], "score": t["score"], "t": t["created_ts"], "s": s_text})

    for t in tier_2:
        formatted_feed.append({"a": t["author"], "tweet_id": t["id"], "l": t["likes"], "r": t["replies"], "score": t["score"], "t": t["created_ts"], "s": t["text"]})

    combined_jsonl = "\n".join(json.dumps(obj, ensure_ascii=False) for obj in formatted_feed)

    # ---------------------------------------------------------
    # 🧠 步骤 3: 提取历史记忆并呼叫 Grok
    # ---------------------------------------------------------
    today_accounts = set(t.get("a", "").lower() for t in formatted_feed)
    memory = load_memory()
    memory_context_lines = []
    for acc in today_accounts:
        if acc in memory and memory[acc]:
            entries = [e if isinstance(e, str) else e.get("summary", str(e)) for e in memory[acc]]
            memory_context_lines.append(f"@{acc} 近期观点:\n- " + "\n- ".join(entries))
    memory_context = "\n\n".join(memory_context_lines)

    macro_info = fetch_macro_with_perplexity()
    china_info = fetch_china_ai_with_perplexity()         # v16 新增
    if china_info:
        macro_info = (macro_info + "\n\n" + china_info) if macro_info else china_info
    tavily_info = fetch_global_news_with_tavily()

    # v16 新增：读取近 7 日已用主题，注入 prompt 反重复护栏
    recent_themes_list = load_recent_themes(days=7)
    recent_themes_str = "\n".join(recent_themes_list) if recent_themes_list else ""
    if recent_themes_list:
        print(f"\n🛡️ [反重复护栏] 加载近 7 日 {len(recent_themes_list)} 个历史主题注入 prompt", flush=True)

    if combined_jsonl.strip() or macro_info or tavily_info:
        xml_result = llm_call_xai(combined_jsonl, today_str, macro_info, tavily_info,
                                  memory_context, recent_themes_str)
        if xml_result:
            parsed_data = parse_llm_xml(xml_result)

            # v16 新增：今日 vs 昨日 diff
            generate_daily_diff(today_str, parsed_data)

            update_character_memory(parsed_data, today_str)

            cover_url = ""
            if parsed_data["cover"]["prompt"]:
                print(f"\n[生图] 提取到生图提示词: {parsed_data['cover']['prompt'][:50]}...", flush=True)
                sf_url = generate_cover_image(parsed_data["cover"]["prompt"])
                cover_url = upload_to_imgbb_via_url(sf_url) if sf_url else ""
            else:
                print("\n⚠️ [渲染警报] 未能从 Grok 报告中解析出生图 prompt 属性！", flush=True)

            render_feishu_card(parsed_data, today_str)

            wechat_hooks = get_wechat_webhooks()
            if wechat_hooks:
                html_content = render_wechat_html(parsed_data, cover_url)
                push_to_wechat(html_content, title=f"{parsed_data['cover']['title'] or '今日核心动态'} | 昨晚硅谷在聊啥", cover_url=cover_url)

            save_daily_data(today_str, formatted_feed, xml_result)
            update_account_stats(formatted_feed, parsed_data)

            print("\n🎉 V15.0 全链路执行完毕！", flush=True)
        else:
            print("❌ [终极警告] LLM 处理失败，无报告输出！", flush=True)

if __name__ == "__main__":
    main()

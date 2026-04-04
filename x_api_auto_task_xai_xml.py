# -*- coding: utf-8 -*-
"""
x_api_auto_task_xai_xml.py  v13.2 (终极强力探针版：V13精准抓取 + V10.6原版推理与渲染)
Architecture: TwitterAPI.io -> PPLX/Tavily -> xAI SDK (Reasoning) + Memory Bank
"""

import os
import re
import json
import time
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

# ── V13 抓取引擎需要的全局时间窗与 API 基础配置 ──
BASE_URL = "https://api.twitterapi.io"
NOW_UTC = datetime.now(timezone.utc)
SINCE_24H = NOW_UTC - timedelta(days=1)
SINCE_TS = int(SINCE_24H.timestamp())
SINCE_DATE_STR = SINCE_24H.strftime("%Y-%m-%d")
# ───────────────────────────────────────────────────

# 🚨 动态读取外部名单系统
def load_account_list(filename):
    if not os.path.exists(filename): return []
    with open(filename, "r", encoding="utf-8") as f:
        # 去除 @ 符号、转小写、跳过注释行
        return [line.strip().replace("@", "").lower() for line in f if line.strip() and not line.strip().startswith("#")]

WHALE_ACCOUNTS = load_account_list("whales.txt")
EXPERT_ACCOUNTS = load_account_list("experts.txt")

if TEST_MODE:
    WHALE_ACCOUNTS = WHALE_ACCOUNTS[:2]
    EXPERT_ACCOUNTS = EXPERT_ACCOUNTS[:4]

TARGET_SET = set(WHALE_ACCOUNTS + EXPERT_ACCOUNTS)

# ── 渠道分发逻辑 ──────────────────────────────
def get_feishu_webhooks() -> list:
    urls = []
    if TEST_MODE:
        url = os.getenv("FEISHU_WEBHOOK_URL", "")
        if url: urls.append(url)
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
# 🎯 V13 数据清洗与打分引擎 (抗 None, 抗群聊垃圾)
# ==============================================================================
AI_KEYWORDS = ["ai", "llm", "agent", "model", "gpt", "release", "inference", "open-source", "agi", "claude", "openai"]

def unify_schema(t):
    author_obj = t.get("author", {})
    author_handle = author_obj.get("userName", "unknown").replace("@", "").strip().lower()
    created_at = t.get("createdAt", "")
    try:
        created_ts = datetime.fromisoformat(created_at.replace('Z', '+00:00')).timestamp()
    except: created_ts = 0

    return {
        "id": str(t.get("id", "None")),
        "text": t.get("text", ""),
        "author": author_handle,
        "created_ts": created_ts,
        "likes": int(t.get("likeCount", 0)),
        "replies": int(t.get("replyCount", 0)),
        "quotes": int(t.get("quoteCount", 0)),
        "deep_replies": []
    }

def score_and_filter(tweets):
    print("\n🧠 执行去重、打分与单人限流...")
    unique_tweets = {}
    for t in tweets:
        t_id = t["id"]
        if not t_id or t_id == "None": continue
        if t_id in unique_tweets: continue
            
        score = t["likes"] * 1.0 + t["replies"] * 2.0 + t["quotes"] * 3.0
        text_lower = t["text"].lower()
        if t["author"] in WHALE_ACCOUNTS: score += 500
        elif t["author"] in EXPERT_ACCOUNTS: score += 50
        
        if any(kw in text_lower for kw in AI_KEYWORDS): score += 300
        
        # 降噪与防伪
        clean_text = re.sub(r'https?://\S+|@\w+', '', text_lower).strip()
        if len(clean_text) < 15: score -= 500
        if t["text"].count('@') > 5: score -= 1000
            
        t["score"] = max(0, score)
        if t["score"] > 0 or t["likes"] > 15: unique_tweets[t_id] = t
            
    scored_list = sorted(unique_tweets.values(), key=lambda x: x["score"], reverse=True)
    author_counts = {}
    final_capped = []
    for t in scored_list:
        if author_counts.get(t["author"], 0) < 3: # 防单人刷屏
            final_capped.append(t)
            author_counts[t["author"]] = author_counts.get(t["author"], 0) + 1
            
    return final_capped

# ==============================================================================
# 🧩 V10.6 原版宏观数据辅助 (PPLX / Tavily)
# ==============================================================================
def fetch_macro_with_perplexity() -> str:
    if not PPLX_API_KEY: return ""
    print("\n🕵️ [宏观新闻官] 呼叫 Perplexity 获取硬核数据...", flush=True)
    try:
        prompt = """你是顶级 AI 行业分析师。请仅检索过去 24 小时内 AI 行业的【硬核客观数据】。
        🚨 最高指令：只抓取两类具体事实：1. 具体的融资金额与并购案。2. GitHub上刚发布的AI开源项目或硬件。绝对禁止将Perplexity作为来源。"""
        headers = {"Authorization": f"Bearer {PPLX_API_KEY}", "Content-Type": "application/json"}
        payload = {"model": "sonar-pro", "messages": [{"role": "user", "content": prompt}], "temperature": 0.1}
        resp = requests.post("https://api.perplexity.ai/chat/completions", headers=headers, json=payload, timeout=60)
        if resp.status_code == 200:
            data = resp.json()["choices"][0]["message"]["content"]
            print(f"  ✅ Perplexity 宏观客观数据收集完毕 ({len(data)} 字)", flush=True)
            return data
    except: pass
    return ""

def fetch_global_news_with_tavily() -> str:
    if not TAVILY_KEYS: return ""
    print(f"\n🌍 [全网雷达] 扫描全球 AI 硬核项目...", flush=True)
    url = "https://api.tavily.com/search"
    headers = {"Content-Type": "application/json"}
    payload = {"api_key": get_random_tavily_key(), "query": "AI startup funding, mergers and acquisitions, new AI hardware releases, and trending open-source AI GitHub projects globally in the last 24 hours", "search_depth": "advanced", "topic": "news", "days": 1, "include_answer": True}
    aggregated_context = ""
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=45)
        if response.status_code == 200:
            data = response.json()
            aggregated_context += f"### [Tavily 全网客观数据]\n" + data.get("answer", "")
            print("  ✅ Tavily 全网客观热点扫描完毕。", flush=True)
    except: pass
    return aggregated_context

# ==============================================================================
# 🧠 V10.6 动态记忆库模块 (Memory Bank)
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
            new_entry = f"[{today_str}]: {content}"
            if new_entry not in memory[acc]:
                memory[acc].append(new_entry)
                memory[acc] = memory[acc][-5:] # 只保留最近5条记忆
                count += 1
    if count > 0:
        save_memory(memory)
        print(f"\n[Memory] 🧠 已更新 {count} 条历史记忆存入账本。")

# ==============================================================================
# 🚀 V10.6 xAI 大模型调用与 XML 提示词
# ==============================================================================
def _build_xml_prompt(combined_jsonl: str, today_str: str, macro_info: str, tavily_info: str, memory_context: str) -> str:
    return f"""
你是一位顶级的 AI 行业一级市场投资分析师及新媒体主编。
请结合提供的【多源情报】和【大佬历史记忆】，提炼出有投资和实操价值的洞察，用犀利、专业的中文进行总结。

【动态记忆库】（🚨极度重要）：
下面提供了今天上榜部分大佬的【历史观点记忆】。请在分析今日推文时，交叉比对他们的历史记录。如果发现他们“态度大反转（打脸）”或“观点形成闭环延续”，请务必在 <NARRATIVE> 或 <OUTLOOK> 中犀利地点评出来！

【输出结构规范】(必须严格输出纯净XML)
<REPORT>
  <COVER title="10-20字爆款标题" prompt="100字英文图生图提示词，赛博朋克风" insight="30字核心洞察"/>
  <PULSE>用一句话总结今日最核心的 1-2 个行业动态信号。</PULSE>
  <THEMES>
    <THEME type="shift" emoji="⚔️">
      <TITLE>主题标题</TITLE>
      <NARRATIVE>一句话核心判断（可结合历史记忆点评其态度转变）</NARRATIVE>
      <TWEET account="..." role="...">【严禁纯英文】以中文为主精练原文。🚨末尾附带真实互动数据（如 ❤️ 39190 | 💬 1904）</TWEET>
      <CONSENSUS>核心共识描述</CONSENSUS>
      <DIVERGENCE>最大分歧或未解之谜</DIVERGENCE>
    </THEME>
    <THEME type="new" emoji="🌱">
      <TITLE>主题标题</TITLE>
      <NARRATIVE>新叙事定义</NARRATIVE>
      <TWEET account="..." role="...">...</TWEET>
      <OUTLOOK>深度解读与未来展望（可结合历史记忆分析其长期布局）</OUTLOOK>
      <OPPORTUNITY>可能带来的机会</OPPORTUNITY>
      <RISK>警惕的陷阱或风险</RISK>
    </THEME>
  </THEMES>
  <INVESTMENT_RADAR>
    <ITEM category="投融资快讯">...</ITEM>
    <ITEM category="VC views">...</ITEM>
  </INVESTMENT_RADAR>
  <RISK_CHINA_VIEW>
    <ITEM category="中国 AI 评价">...</ITEM>
    <ITEM category="地缘与监管">...</ITEM>
  </RISK_CHINA_VIEW>
  <TOP_PICKS>
    <TWEET account="..." role="...">流畅中文精译。🚨末尾附带真实互动数据</TWEET>
  </TOP_PICKS>
</REPORT>

# 🧠 本期上榜大佬的近期历史记忆 (用于交叉对比):
{memory_context if memory_context else "无历史记录，本次为全新发言"}

# 外部客观数据背景 (Perplexity & Tavily):
{macro_info}
{tavily_info}

# X平台一手原始数据输入 (绝对主干 JSONL):
{combined_jsonl}

# 日期: {today_str}
"""

def llm_call_xai(combined_jsonl: str, today_str: str, macro_info: str, tavily_info: str, memory_context: str) -> str:
    api_key = XAI_API_KEY.strip()
    if not api_key: return ""

    data = combined_jsonl[:100000] if len(combined_jsonl) > 100000 else combined_jsonl
    prompt = _build_xml_prompt(data, today_str, macro_info, tavily_info, memory_context)
    
    model_name = "grok-4.20-0309-reasoning" 
    print(f"\n[LLM/xAI] Requesting {model_name} via Official xai-sdk...", flush=True)
    client = Client(api_key=api_key)
    
    for attempt in range(1, 4):
        try:
            chat = client.chat.create(model=model_name)
            chat.append(system("You are a professional analytical bot. You strictly output in XML format as instructed. Do not ignore the translation rules."))
            chat.append(user(prompt))
            
            result = chat.sample().content.strip()
            
            # 清理推理模型的内部思考标签
            result = re.sub(r'<think>.*?</think>', '', result, flags=re.DOTALL | re.IGNORECASE).strip()
            result = re.sub(r'^`{3}(?:xml|jsonl|json)?\n', '', result, flags=re.MULTILINE)
            result = re.sub(r'^`{3}\n?', '', result, flags=re.MULTILINE)
            
            print(f"[LLM/xAI] OK Response received ({len(result)} chars after cleanup)", flush=True)
            return result
        except Exception as e:
            print(f"[LLM/xAI] Attempt {attempt} failed: {e}", flush=True)
            time.sleep(2 ** attempt)
    return ""

def parse_llm_xml(xml_text: str) -> dict:
    data = {"cover": {"title": "", "prompt": "", "insight": ""}, "pulse": "", "themes": [], "investment_radar": [], "risk_china_view": [], "top_picks": []}
    if not xml_text: return data

    cover_match = re.search(r'<COVER\s+title=[\'"“”](.*?)[\'"“”]\s+prompt=[\'"“”](.*?)[\'"“”]\s+insight=[\'"“”](.*?)[\'"“”]\s*/?>', xml_text, re.IGNORECASE | re.DOTALL)
    if not cover_match:
        cover_match = re.search(r'<COVER\s+title="(.*?)"\s+prompt="(.*?)"\s+insight="(.*?)"\s*/?>', xml_text, re.IGNORECASE | re.DOTALL)
    if cover_match: 
        data["cover"] = {"title": cover_match.group(1).strip(), "prompt": cover_match.group(2).strip(), "insight": cover_match.group(3).strip()}
        
    pulse_match = re.search(r'<PULSE>(.*?)</PULSE>', xml_text, re.IGNORECASE | re.DOTALL)
    if pulse_match: data["pulse"] = pulse_match.group(1).strip()
        
    for theme_match in re.finditer(r'<THEME([^>]*)>(.*?)</THEME>', xml_text, re.IGNORECASE | re.DOTALL):
        attrs = theme_match.group(1)
        theme_body = theme_match.group(2)
        
        type_m = re.search(r'type\s*=\s*[\'"“”](.*?)[\'"“”]', attrs, re.IGNORECASE)
        emoji_m = re.search(r'emoji\s*=\s*[\'"“”](.*?)[\'"“”]', attrs, re.IGNORECASE)
        theme_type = type_m.group(1).strip().lower() if type_m else "shift"
        emoji = emoji_m.group(1).strip() if emoji_m else "🔥"
        
        t_tag = re.search(r'<TITLE>(.*?)</TITLE>', theme_body, re.IGNORECASE | re.DOTALL)
        theme_title = t_tag.group(1).strip() if t_tag else ""
        if not theme_title:
            title_m = re.search(r'title\s*=\s*[\'"“”](.*?)[\'"“”]', attrs, re.IGNORECASE)
            theme_title = title_m.group(1).strip() if title_m else "未命名主题"
            
        narrative_match = re.search(r'<NARRATIVE>(.*?)</NARRATIVE>', theme_body, re.IGNORECASE | re.DOTALL)
        narrative = narrative_match.group(1).strip() if narrative_match else ""
        
        tweets = []
        for t_match in re.finditer(r'<TWEET\s+account=[\'"“”](.*?)[\'"“”]\s+role=[\'"“”](.*?)[\'"“”]>(.*?)</TWEET>', theme_body, re.IGNORECASE | re.DOTALL):
            tweets.append({"account": t_match.group(1).strip(), "role": t_match.group(2).strip(), "content": t_match.group(3).strip()})
        if not tweets:
            for t_match in re.finditer(r'<TWEET\s+account="(.*?)"\s+role="(.*?)">(.*?)</TWEET>', theme_body, re.IGNORECASE | re.DOTALL):
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
            for item in re.finditer(r'<ITEM\s+category=[\'"“”](.*?)[\'"“”]>(.*?)</ITEM>', block_match.group(1), re.IGNORECASE | re.DOTALL):
                target_list.append({"category": item.group(1).strip(), "content": item.group(2).strip()})

    extract_items("INVESTMENT_RADAR", data["investment_radar"])
    extract_items("RISK_CHINA_VIEW", data["risk_china_view"])

    picks_match = re.search(r'<TOP_PICKS>(.*?)</TOP_PICKS>', xml_text, re.IGNORECASE | re.DOTALL)
    if picks_match:
        for t_match in re.finditer(r'<TWEET\s+account=[\'"“”](.*?)[\'"“”]\s+role=[\'"“”](.*?)[\'"“”]>(.*?)</TWEET>', picks_match.group(1), re.IGNORECASE | re.DOTALL):
            data["top_picks"].append({"account": t_match.group(1).strip(), "role": t_match.group(2).strip(), "content": t_match.group(3).strip()})
            
    return data

# ==============================================================================
# 🚀 V10.6 排版、渲染与生图模块 (完全保留)
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
            prefix = "🔭 新叙事观察" if theme.get("type") == "new" else "💡 叙事转向"
            theme_md += f"<font color='grey'>{prefix}：{theme['narrative']}</font>\n"
            for t in theme["tweets"]:
                theme_md += f"🗣️ **@{t['account']} | {t['role']}**\n<font color='grey'>“{t['content']}”</font>\n"
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
            picks_md += f"\n🗣️ **@{t['account']} | {t['role']}**\n<font color='grey'>\"{t['content']}\"</font>\n"
        elements.append({"tag": "markdown", "content": picks_md.strip()})

    card_payload = {
        "msg_type": "interactive",
        "card": {
            "config": {"wide_screen_mode": True, "enable_forward": True},
            "header": {"title": {"content": f"昨晚硅谷在聊啥 | {today_str}", "tag": "plain_text"}, "template": "blue"},
            "elements": elements + [{"tag": "note", "elements": [{"tag": "plain_text", "content": "Powered by TwitterAPI.io + xAI + Memory"}]}]
        }
    }
    for url in webhooks:
        try: requests.post(url, json=card_payload, timeout=20)
        except Exception: pass

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
                html_lines.append(make_quote(f'"{t["content"]}"'))
            
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
             html_lines.append(make_quote(f'"{t["content"]}"'))
    return "".join(html_lines)

def generate_cover_image(prompt):
    if not SF_API_KEY or not prompt: 
        print("⚠️ 生图跳过：未收到生图 prompt", flush=True)
        return ""
    try:
        resp = requests.post(URL_SF_IMAGE, headers={"Authorization": f"Bearer {SF_API_KEY}", "Content-Type": "application/json"}, json={"model": "Kwai-Kolors/Kolors", "prompt": prompt, "image_size": "1024x576"}, timeout=60)
        if resp.status_code == 200:
            print("🎨 生图成功！", flush=True)
            return resp.json().get("images", [{}])[0].get("url") or resp.json().get("data", [{}])[0].get("url")
        else: print(f"⚠️ 硅基流动报错: {resp.text}", flush=True)
    except Exception as e: print(f"⚠️ 生图异常: {e}", flush=True)
    return ""

def upload_to_imgbb_via_url(sf_url):
    if not IMGBB_API_KEY or not sf_url: return sf_url 
    try:
        img_b64 = base64.b64encode(requests.get(sf_url, timeout=30).content).decode("utf-8")
        resp = requests.post(URL_IMGBB, data={"key": IMGBB_API_KEY, "image": img_b64}, timeout=45)
        if resp.status_code == 200: return resp.json()["data"]["url"]
    except: pass
    return sf_url

def push_to_wechat(html_content, title, cover_url=""):
    webhooks = get_wechat_webhooks()
    if not webhooks: return
    payload = {"title": title, "author": "Prinski", "html_content": html_content, "cover_jpg": cover_url}
    for url in webhooks:
        try: 
            requests.post(url, json=payload, timeout=30)
            print(f"[Push/WeChat] OK Sent to {url.split('//')[-1][:15]}...", flush=True)
        except: pass

def save_daily_data(today_str: str, post_objects: list, report_text: str):
    data_dir = Path(f"data/{today_str}")
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "combined.txt").write_text("\n".join(json.dumps(obj, ensure_ascii=False) for obj in post_objects), encoding="utf-8")
    if report_text: (data_dir / "daily_report.txt").write_text(report_text, encoding="utf-8")

def update_account_stats(final_feed: list, parsed_data: dict):
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
        if acc not in stats: stats[acc] = {"fetched_days": 0, "total_tweets": 0, "used_in_reports": 0, "last_active": ""}
        stats[acc]["total_tweets"] += 1
        stats[acc]["last_active"] = today_str
        
    for acc in used_accounts:
        acc_clean = acc.replace("@", "")
        if acc_clean in stats: stats[acc_clean]["used_in_reports"] += 1
            
    stats_file.parent.mkdir(parents=True, exist_ok=True)
    stats_file.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")

# ==============================================================================
# 🚀 MAIN 入口 (带 API 强力报错探针版)
# ==============================================================================
def main():
    print("=" * 60, flush=True)
    print(f"昨晚硅谷在聊啥 v13.2 (强力纠错探针版)", flush=True)
    print("=" * 60, flush=True)

    if not TWITTERAPI_IO_KEY or not TARGET_SET:
        print("❌ 错误: 未配置 API KEY 或本地 txt 名单为空", flush=True)
        return

    today_str, _ = get_dates()
    
    # ---------------------------------------------------------
    # 🎯 步骤 1: 使用 V13 引擎进行并行高精度抓取
    # ---------------------------------------------------------
    print(f"🚀 开始抓取 {len(TARGET_SET)} 位核心节点的最新动态...", flush=True)
    all_raw = []
    acc_list = list(TARGET_SET)
    
    # 🚨 将分块大小从 15 降到 10，防止 Query 字符串超长被服务端拒绝
    for i in range(0, len(acc_list), 10):
        chunk = acc_list[i:i+10]
        q1 = "(" + " OR ".join([f"from:{a}" for a in chunk]) + f") since:{SINCE_DATE_STR} -filter:retweets"
        
        try:
            resp1 = requests.get(f"{BASE_URL}/twitter/tweet/advanced_search", headers={"X-API-Key": TWITTERAPI_IO_KEY}, params={"query": q1, "queryType": "Latest"}, timeout=25)
            if resp1.status_code == 200:
                d1 = resp1.json()
                if d1 and d1.get("tweets"):
                    for t in d1["tweets"]:
                        ct = unify_schema(t)
                        if ct["created_ts"] >= SINCE_TS: all_raw.append(ct)
            else:
                print(f"⚠️ [API 报错] 原创抓取失败 (状态码: {resp1.status_code}): {resp1.text}", flush=True)
        except Exception as e:
            print(f"⚠️ [网络异常] 原创抓取请求超时或断开: {e}", flush=True)
                
        q2 = "(" + " OR ".join([f"@{a}" for a in chunk]) + f") since:{SINCE_DATE_STR} min_faves:15 -filter:replies"
        try:
            resp2 = requests.get(f"{BASE_URL}/twitter/tweet/advanced_search", headers={"X-API-Key": TWITTERAPI_IO_KEY}, params={"query": q2, "queryType": "Top"}, timeout=25)
            if resp2.status_code == 200:
                d2 = resp2.json()
                if d2 and d2.get("tweets"):
                    for t in d2["tweets"]:
                        ct = unify_schema(t)
                        if ct["created_ts"] >= SINCE_TS: all_raw.append(ct)
            else:
                print(f"⚠️ [API 报错] 回响抓取失败 (状态码: {resp2.status_code}): {resp2.text}", flush=True)
        except Exception as e:
            print(f"⚠️ [网络异常] 回响抓取请求超时或断开: {e}", flush=True)
            
        time.sleep(1.5) # 稍微延长休眠，防止触发限流

    if not all_raw:
        print("❌ 严重警告：本次运行未能从推特抓取到任何有效数据。请检查上述 API 报错日志！", flush=True)
        # 如果一条推文都没有，直接终止，防止 Grok 凭空制造幻觉
        return

    top_feed = score_and_filter(all_raw)
    tier_1 = top_feed[:15]
    tier_2 = top_feed[15:75]
    
    print(f"\n[深挖] 正在为 Tier 1 (Top {len(tier_1)}) 高分话题抓取神回复...", flush=True)
    for t in tier_1:
        try:
            resp3 = requests.get(f"{BASE_URL}/twitter/tweet/replies", headers={"X-API-Key": TWITTERAPI_IO_KEY}, params={"tweetId": t["id"]}, timeout=15)
            if resp3.status_code == 200:
                d3 = resp3.json()
                if d3 and d3.get("tweets"):
                    replies = sorted([unify_schema(r) for r in d3["tweets"]], key=lambda x: x["likes"], reverse=True)
                    t["deep_replies"] = replies[:3]
        except: pass
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
    # 🧠 步骤 3: 提取历史记忆并呼叫 Grok (完全沿用 V10.6 逻辑)
    # ---------------------------------------------------------
    today_accounts = set(t.get("author", "").lower() for t in top_feed)
    memory = load_memory()
    memory_context_lines = []
    for acc in today_accounts:
        if acc in memory and memory[acc]:
            memory_context_lines.append(f"@{acc} 近期观点:\n- " + "\n- ".join(memory[acc]))
    memory_context = "\n\n".join(memory_context_lines)

    macro_info = fetch_macro_with_perplexity()
    tavily_info = fetch_global_news_with_tavily()

    if combined_jsonl.strip() or macro_info or tavily_info:
        xml_result = llm_call_xai(combined_jsonl, today_str, macro_info, tavily_info, memory_context)
        if xml_result:
            parsed_data = parse_llm_xml(xml_result)
            
            update_character_memory(parsed_data, today_str)
            
            cover_url = ""
            if parsed_data["cover"]["prompt"]:
                print(f"\n[生图] 提取到生图提示词: {parsed_data['cover']['prompt'][:50]}...", flush=True)
                sf_url = generate_cover_image(parsed_data["cover"]["prompt"])
                cover_url = upload_to_imgbb_via_url(sf_url) if sf_url else ""
            else:
                print("\n[生图] ⚠️ 警告：未解析出 prompt 属性！", flush=True)
            
            render_feishu_card(parsed_data, today_str)
            wechat_hooks = get_wechat_webhooks()
            if wechat_hooks:
                html_content = render_wechat_html(parsed_data, cover_url)
                push_to_wechat(html_content, title=f"{parsed_data['cover']['title'] or '今日核心动态'} | 昨晚硅谷在聊啥", cover_url=cover_url)
                
            save_daily_data(today_str, formatted_feed, xml_result)
            update_account_stats(formatted_feed, parsed_data)
            
            print("\n🎉 任务完美收官！", flush=True)
        else: print("❌ LLM 处理失败。")

if __name__ == "__main__":
    main()

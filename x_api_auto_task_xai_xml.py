# -*- coding: utf-8 -*-
"""
x_api_auto_task_xai_xml.py  v9.1 (多源融合终极版: 纯净Timeline + 微信极简排版 + ID缓存)
Architecture: Timeline Fetch (TWT241) -> Local Cache -> PPLX/Tavily -> xAI SDK -> UI
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

# ── 环境变量 ──────────────────────────────
JIJYUN_WEBHOOK_URL  = os.getenv("JIJYUN_WEBHOOK_URL", "")
SF_API_KEY          = os.getenv("SF_API_KEY", "")
XAI_API_KEY         = os.getenv("XAI_API_KEY", "")    
IMGBB_API_KEY       = os.getenv("IMGBB_API_KEY", "") 

PPLX_API_KEY        = os.getenv("PPLX_API_KEY", "")

# 🚨 动态密钥池 1：RapidAPI Twitter 密钥池
TWT_KEYS = []
for i in range(1, 10):
    k = os.getenv(f"TWTAPI_KEY_{i}")
    if k and k.strip(): TWT_KEYS.append(k.strip())

legacy_key = os.getenv("TWTAPI_KEY", "")
if legacy_key and legacy_key.strip() and legacy_key not in TWT_KEYS:
    TWT_KEYS.append(legacy_key.strip())

def get_random_twt_key():
    if not TWT_KEYS: return ""
    return random.choice(TWT_KEYS)

# 🚨 动态密钥池 2：Tavily 检索密钥池
TAVILY_KEYS = []
for suffix in ["", "_2", "_3", "_4", "_5"]:
    tk = os.getenv(f"TAVILY_API_KEY{suffix}")
    if tk and tk.strip(): TAVILY_KEYS.append(tk.strip())

def get_random_tavily_key():
    if not TAVILY_KEYS: return ""
    return random.choice(TAVILY_KEYS)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🚨 API 接口配置 (V9.0 升级为纯净 Timeline 架构)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
RAPIDAPI_HOST   = "twitter241.p.rapidapi.com"
URL_USER_INFO   = "https://" + RAPIDAPI_HOST + "/user"
URL_USER_TWEETS = "https://" + RAPIDAPI_HOST + "/user-tweets"
URL_SEARCH      = "https://" + RAPIDAPI_HOST + "/search-v2" 
URL_COMMENTS    = "https://" + RAPIDAPI_HOST + "/comments-v2"

def D(b64_str):
    return base64.b64decode(b64_str).decode("utf-8")

URL_SF_IMAGE   = D("aHR0cHM6Ly9hcGkuc2lsaWNvbmZsb3cuY24vdjEvaW1hZ2VzL2dlbmVyYXRpb25z")
URL_IMGBB      = D("aHR0cHM6Ly9hcGkuaW1nYmIuY29tLzEvdXBsb2Fk")

# ── 单独拎出“巨鲸”账号
WHALE_ACCOUNTS = [
    "elonmusk", "sama", "gregbrockman", "pmarca", "lexfridman"
]

# ── 剩下的硬核专家/开发者/VC/中文AI核心圈
EXPERT_ACCOUNTS = [
    "karpathy", "demishassabis", "darioamodei", "OpenAI", "AnthropicAI", 
    "GoogleDeepMind", "xAI", "AIatMeta", "GoogleAI", "MSFTResearch", 
    "IlyaSutskever", "GaryMarcus", "rowancheung", "clmcleod", "bindureddy",
    "dotey", "oran_ge", "vista8", "imxiaohu", "Sxsyer",
    "K_O_D_A_D_A", "tualatrix", "linyunqiu", "garywong", "web3buidl",
    "AI_Era", "AIGC_News", "jiangjiang", "hw_star", "mranti", "nishuang",
    "a16z", "ycombinator", "lightspeedvp", "sequoia", "foundersfund",
    "eladgil", "bchesky", "chamath", "paulg", "TheInformation", 
    "TechCrunch", "verge", "WIRED", "Scobleizer", "bentossell",
    "HuggingFace", "MistralAI", "Perplexity_AI", "GroqInc", "Cohere",
    "TogetherCompute", "runwayml", "Midjourney", "StabilityAI", "Scale_AI",
    "CerebrasSystems", "tenstorrent", "weights_biases", "langchainai", "llama_index",
    "supabase", "vllm_project", "huggingface_hub", "nvidia", "AMD", 
    "Intel", "SKhynix", "tsmc", "magicleap", "NathieVR", "PalmerLuckey", 
    "ID_AA_Carmack", "boz", "rabovitz", "htcvive", "XREAL_Global", "RayBan", 
    "MetaQuestVR", "PatrickMoorhead", "jeffdean", "chrmanning", "hardmaru", 
    "goodfellow_ian", "feifeili", "_akhaliq", "promptengineer", "AI_News_Tech", 
    "siliconvalley", "aithread", "aibreakdown", "aiexplained", "aipubcast", "hubermanlab", "swyx"
]

if TEST_MODE:
    WHALE_ACCOUNTS = WHALE_ACCOUNTS[:2]
    EXPERT_ACCOUNTS = EXPERT_ACCOUNTS[:4]

def get_feishu_webhooks() -> list:
    urls = []
    for suffix in ["", "_1", "_2", "_3"]:
        url = os.getenv(f"FEISHU_WEBHOOK_URL{suffix}", "")
        if url: urls.append(url)
    return urls

def get_dates() -> tuple:
    tz = timezone(timedelta(hours=8))
    today = datetime.now(tz)
    yesterday = today - timedelta(days=1)
    return today.strftime("%Y-%m-%d"), yesterday.strftime("%Y-%m-%d")

def get_valid_mmdd_list() -> list:
    """获取最近 3 天的合法 MMDD 列表，用于本地过滤 Timeline 数据"""
    tz = timezone(timedelta(hours=8))
    today = datetime.now(tz)
    dates = [today - timedelta(days=i) for i in range(3)]
    return [d.strftime("%m%d") for d in dates]

def parse_twitter_date(date_str):
    try:
        if " " in date_str:
            parts = date_str.split()
            if len(parts) >= 3:
                m_map = {"Jan":"01", "Feb":"02", "Mar":"03", "Apr":"04", "May":"05", "Jun":"06", 
                         "Jul":"07", "Aug":"08", "Sep":"09", "Oct":"10", "Nov":"11", "Dec":"12"}
                mm = m_map.get(parts[1], "01")
                dd = parts[2].zfill(2)
                return f"{mm}{dd}"
    except: pass
    return datetime.now(timezone.utc).strftime("%m%d")

def safe_int(val):
    try:
        if isinstance(val, (int, float)): return int(val)
        v = str(val).lower().replace(',', '')
        if 'k' in v: return int(float(re.search(r'[\d\.]+', v).group()) * 1000)
        if 'm' in v: return int(float(re.search(r'[\d\.]+', v).group()) * 1000000)
        num = re.search(r'\d+', v)
        return int(num.group()) if num else 0
    except:
        return 0

# ==============================================================================
# 🚀 外部情报检索：Perplexity & Tavily
# ==============================================================================
def fetch_macro_with_perplexity() -> str:
    if not PPLX_API_KEY: return ""
    print("\n🕵️ [宏观新闻官] 正在呼叫 Perplexity 扫描全球 AI 头条与全网热点...", flush=True)
    try:
        prompt = """你是顶级 AI 行业分析师。请检索过去 24 小时内全网最重要的 AI 动态。
        重点关注：
        1. 💰 资本与宏观：AI领域的重磅投融资、并购。
        2. 🎁 搞钱新物种：最新开源的 AI 项目、前沿 AI 软硬件产品、热门 AI 众筹产品。
        3. 🌐 全网突发热点：过去24小时内全网热烈讨论的 AI 突发事件、黑马产品、重大争议。
        要求：必须带上具体的媒体来源，绝对禁止将 "Perplexity" 作为信息来源。"""
        
        headers = {"Authorization": f"Bearer {PPLX_API_KEY}", "Content-Type": "application/json"}
        payload = {"model": "sonar-pro", "messages": [{"role": "user", "content": prompt}], "temperature": 0.1}
        resp = requests.post("https://api.perplexity.ai/chat/completions", headers=headers, json=payload, timeout=60)
        if resp.status_code == 200:
            data = resp.json()["choices"][0]["message"]["content"]
            print(f"  ✅ Perplexity 宏观情报收集完毕 ({len(data)} 字)", flush=True)
            return data
    except Exception as e: print(f"  ❌ Perplexity 抛出异常: {e}", flush=True)
    return ""

def fetch_leaders_with_tavily(accounts: list) -> str:
    if not TAVILY_KEYS: return ""
    track_list = accounts[:45]
    print(f"\n🐦 [领袖盯盘员] 正在对 {len(track_list)} 位核心大佬进行 Tavily 无死角扫描...", flush=True)
    chunk_size = 15
    leader_chunks = [",".join(track_list[i:i + chunk_size]) for i in range(0, len(track_list), chunk_size)]
    url = "https://api.tavily.com/search"
    headers = {"Content-Type": "application/json"}
    aggregated_context = ""

    for i, chunk in enumerate(leader_chunks, 1):
        current_tk = get_random_tavily_key()
        try:
            payload = {"api_key": current_tk, "query": f"Today's AI tech tweets/news from: {chunk}", "search_depth": "advanced", "topic": "news", "days": 1, "include_answer": True}
            response = requests.post(url, json=payload, headers=headers, timeout=45)
            if response.status_code == 200:
                data = response.json()
                aggregated_context += f"\n\n### [第 {i} 组大佬外部情报]\n" + data.get("answer", "")
                for result in data.get("results", [])[:3]:
                    aggregated_context += f"\n- [{result['title']}]({result['url']}): {result['content']}"
        except: pass
        time.sleep(1.5) 
    print(f"  ✅ Tavily 领袖矩阵检索完毕。", flush=True)
    return aggregated_context

def fetch_global_news_with_tavily() -> str:
    if not TAVILY_KEYS: return ""
    print(f"\n🌍 [全网雷达] 正在使用 Tavily 扫描全球 AI 突发热点...", flush=True)
    current_tk = get_random_tavily_key()
    url = "https://api.tavily.com/search"
    headers = {"Content-Type": "application/json"}
    payload = {"api_key": current_tk, "query": "Most important AI technology news, LLM breakthroughs, AI startup announcements, and trending AI discussions globally in the last 24 hours", "search_depth": "advanced", "topic": "news", "days": 1, "include_answer": True}
    aggregated_context = ""
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=45)
        if response.status_code == 200:
            data = response.json()
            aggregated_context += f"### [Tavily 全网突发热点]\n" + data.get("answer", "")
            for result in data.get("results", [])[:5]:
                aggregated_context += f"\n- [{result['title']}]({result['url']}): {result['content']}"
            print("  ✅ Tavily 全网热点扫描完毕。", flush=True)
    except: pass
    return aggregated_context

# ==============================================================================
# 🚀 第一阶段：RapidAPI 原生 Twitter 抓取 (数字ID缓存与Timeline接口)
# ==============================================================================
def load_id_cache():
    cache_file = Path("data/twitter_ids_cache.json")
    if cache_file.exists():
        try: return json.loads(cache_file.read_text(encoding="utf-8"))
        except: return {}
    return {}

def save_id_cache(cache_dict):
    cache_file = Path("data/twitter_ids_cache.json")
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps(cache_dict, ensure_ascii=False, indent=2), encoding="utf-8")

def resolve_username_to_id(username: str, cache: dict) -> str:
    """自动将字母账号解析为数字 ID，并持久化缓存 (V9.1: 增加独立重试与防并发机制)"""
    uname_lower = username.lower()
    if uname_lower in cache:
        return cache[uname_lower]
        
    print(f"    🔄 首次解析 @{username} 的底层数字 ID...", flush=True)
    
    for attempt in range(3):
        # 🚨 每次重试随机抽一把新钥匙，分散压力
        current_key = get_random_twt_key()
        headers = {"x-rapidapi-key": current_key, "x-rapidapi-host": RAPIDAPI_HOST}
        
        try:
            resp = requests.get(URL_USER_INFO, headers=headers, params={"username": username}, timeout=15)
            if resp.status_code == 200:
                match = re.search(r'"rest_id"\s*:\s*"(\d+)"', resp.text)
                if match:
                    numeric_id = match.group(1)
                    cache[uname_lower] = numeric_id
                    save_id_cache(cache)
                    time.sleep(1)  # 成功建档后休息 1 秒，温和建库
                    return numeric_id
            elif resp.status_code in [429, 403]:
                print(f"      ⚠️ 解析 ID 遇限流 ({resp.status_code})，切换 Key 重试...", flush=True)
                time.sleep(2)
            elif resp.status_code == 404:
                print(f"      ⚠️ 账号 @{username} 可能已注销或改名 (404)。", flush=True)
                return None  # 404 没必要重试，直接放弃
            else:
                time.sleep(1)
        except Exception as e:
            time.sleep(1)
            
    print(f"    ❌ 解析 @{username} 失败，跳过。", flush=True)
    return None

def parse_rapidapi_tweets(data) -> list:
    all_tweets = []
    def recurse(obj):
        if isinstance(obj, dict):
            text = obj.get("full_text") or obj.get("text")
            if not text and obj.get("legacy"): text = obj["legacy"].get("full_text") or obj["legacy"].get("text")
            if text and isinstance(text, str):
                sn = None
                try: sn = obj.get("core", {}).get("user_results", {}).get("result", {}).get("legacy", {}).get("screen_name")
                except: pass
                if not sn: sn = obj.get("screen_name")
                if not sn:
                    u = obj.get("user") or obj.get("author") or obj.get("user_info") or {}
                    sn = u.get("screen_name") or u.get("userName") or u.get("username")
                if not sn and obj.get("legacy"): sn = obj["legacy"].get("screen_name")
                if not sn:
                    raw_str = json.dumps(obj)
                    sn_match = re.search(r'"screen_name"\s*:\s*"([^"]+)"', raw_str)
                    if sn_match: sn = sn_match.group(1)
                    else:
                        usr_match = re.search(r'"userName"\s*:\s*"([^"]+)"', raw_str)
                        if usr_match: sn = usr_match.group(1)
                if sn:
                    t_id = obj.get("rest_id") or obj.get("id_str") or obj.get("id") or obj.get("tweet_id")
                    if not t_id and obj.get("legacy"): t_id = obj["legacy"].get("id_str")
                    fav = obj.get("favorite_count") or obj.get("favorites") or obj.get("likes") or 0
                    if not fav and obj.get("legacy"): fav = obj["legacy"].get("favorite_count", 0)
                    rep = obj.get("reply_count") or obj.get("replies") or 0
                    if not rep and obj.get("legacy"): rep = obj["legacy"].get("reply_count", 0)
                    created_at = obj.get("created_at")
                    if not created_at and obj.get("legacy"): created_at = obj["legacy"].get("created_at", "")
                    reply_to = obj.get("in_reply_to_screen_name") or obj.get("reply_to") or obj.get("is_reply")
                    if not reply_to and obj.get("legacy"): reply_to = obj["legacy"].get("in_reply_to_screen_name")
                    if str(t_id):
                        all_tweets.append({
                            "tweet_id": str(t_id), "screen_name": sn, "text": text,
                            "favorites": safe_int(fav), "replies": safe_int(rep), 
                            "created_at": created_at, "reply_to": reply_to,
                        })
                        return 
            for v in obj.values(): recurse(v)
        elif isinstance(obj, list):
            for item in obj: recurse(item)
    recurse(data)
    seen, unique = set(), []
    for t in all_tweets:
        if t["tweet_id"] not in seen:
            seen.add(t["tweet_id"])
            unique.append(t)
    return unique

def fetch_user_timeline_tweets(accounts: list, label: str) -> list:
    """🚨 核心：通过数字ID遍历抓取用户主页 Timeline，无视一切屏蔽"""
    if not TWT_KEYS: 
        print(f"⚠️ 未配置 TWTAPI_KEY，跳过{label}抓取", flush=True)
        return []
    
    id_cache = load_id_cache()
    valid_mmdd = get_valid_mmdd_list()
    all_tweets = []
    consecutive_api_errors = 0  
    
    print(f"\n⏳ [{label}扫盘] 启动【主页 Timeline】逐个爆破模式，共 {len(accounts)} 人...", flush=True)
    
    for idx, username in enumerate(accounts, 1):
        # 放宽容错度，避免被封号的人引发全局罢工
        if consecutive_api_errors >= 5: 
            print("  ⚠️ API 连续报错 5 次，额度可能耗尽，提前终止本组抓取。", flush=True)
            break
            
        # V9.1 移除了向内部传递 headers，让它内部自己管理轮换
        numeric_id = resolve_username_to_id(username, id_cache)
        if not numeric_id: continue
            
        current_key = get_random_twt_key()
        headers = {"x-rapidapi-key": current_key, "x-rapidapi-host": RAPIDAPI_HOST}
        print(f"  🔎 挖掘 @{username} (ID:{numeric_id}) 主页动态... (Key尾号: ...{current_key[-4:]})", flush=True)
        params = {"user": numeric_id, "count": "20"} 
        
        success = False
        for attempt in range(3):
            try:
                resp = requests.get(URL_USER_TWEETS, headers=headers, params=params, timeout=25)
                if resp.status_code == 200:
                    tweets = parse_rapidapi_tweets(resp.json())
                    recent_valid_tweets = []
                    for t in tweets:
                        # 确保是本人发的（排除偶尔乱入的）
                        if t["screen_name"].lower() != username.lower(): continue
                        t_mmdd = parse_twitter_date(t["created_at"])
                        if t_mmdd in valid_mmdd:
                            t["t"] = t_mmdd
                            recent_valid_tweets.append(t)
                            
                    all_tweets.extend(recent_valid_tweets)
                    print(f"    ✅ 成功拔取 {len(recent_valid_tweets)} 条近期有效动态。")
                    consecutive_api_errors = 0  # 成功则清零错误计数
                    success = True
                    break
                elif resp.status_code in [403, 429]:
                    print(f"    ⚠️ HTTP {resp.status_code}，切换 Key 重试...", flush=True)
                    current_key = get_random_twt_key() # 动态换钥匙
                    headers["x-rapidapi-key"] = current_key
                    consecutive_api_errors += 1
                    time.sleep(2)
                elif resp.status_code == 404:
                    print(f"    ⚠️ 找不到 @{username} 的推文，可能已被封禁。")
                    break # 404直接跳出重试
                else: 
                    consecutive_api_errors += 1
                    time.sleep(2)
            except Exception as e: 
                time.sleep(2)
                
        if success: time.sleep(0.5)
        else: time.sleep(2)
        
    return all_tweets

def fetch_global_hot_tweets() -> list:
    if not TWT_KEYS: return []
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
    all_tweets = []
    
    print(f"\n📡 [X平台热点] 启动策略扫描 X 平台全球突发热点...", flush=True)
    grok_queries = [
        f'(AI OR "artificial intelligence" OR LLM OR OpenAI OR xAI OR Grok OR Anthropic OR DeepMind OR Claude) since:{yesterday} min_faves:50 -is:retweet',
        f'(AI OR LLM) (release OR launch OR breakthrough OR update) since:{yesterday} min_faves:30 (filter:links OR filter:media) -is:retweet'
    ]
    
    for idx, q in enumerate(grok_queries, 1):
        current_key = get_random_twt_key()
        headers = {"x-rapidapi-key": current_key, "x-rapidapi-host": RAPIDAPI_HOST}
        
        print(f"  🔍 策略 {idx}/2 (密钥尾号: ...{current_key[-4:]})...", flush=True)
        params_discovery = {"query": q, "type": "Top", "count": "20"}
        
        for attempt in range(3):
            try:
                resp = requests.get(URL_SEARCH, headers=headers, params=params_discovery, timeout=25)
                if resp.status_code == 200:
                    tweets = parse_rapidapi_tweets(resp.json())
                    for t in tweets: t["t"] = parse_twitter_date(t["created_at"])
                    all_tweets.extend(tweets)
                    print(f"    ✅ 策略 {idx} 成功捕获 {len(tweets)} 条。")
                    break
                elif resp.status_code in [403, 404, 429]: break 
                else: time.sleep(2)
            except: time.sleep(2)
        time.sleep(1.5)
        
    return all_tweets

def fetch_top_comments(tweet_id: str) -> list:
    if not tweet_id or not TWT_KEYS: return []
    current_key = get_random_twt_key()
    headers = {"x-rapidapi-key": current_key, "x-rapidapi-host": RAPIDAPI_HOST}
    try:
        resp = requests.get(URL_COMMENTS, headers=headers, params={"pid": tweet_id, "rankingMode": "Relevance", "count": "20"}, timeout=25)
        if resp.status_code == 200:
            raw_comments = parse_rapidapi_tweets(resp.json())
            return [f"@{c['screen_name']}: {c['text'][:150]}" for c in raw_comments if len(c.get("text", "")) > 10][:5]
    except: pass
    return []

# ==============================================================================
# 🚀 第二阶段：多源融合 xAI XML 提示词与大模型调用 
# ==============================================================================
def _build_xml_prompt(combined_jsonl: str, today_str: str, macro_info: str, tavily_info: str) -> str:
    return f"""
你是一位顶级的 AI 行业一级市场投资分析师。
请结合提供的【多源情报】（包含X平台一手动态、外媒报道、全网热点），提炼出有投资和实操价值的洞察，用犀利、专业的中文进行总结。

【重要纪律】
1. 禁止输出任何 Markdown 排版符号（如 #, *, >, -）。
2. 只允许输出纯文本内容，并严格按照以下 XML 标签结构填入信息。不要缺漏闭合标签。
3. Title（头衔/身份）绝对不要翻译，保持纯英文。
4. 🚨【翻译铁律】所有的 <TWEET> 标签内容，【必须以中文为主体】！绝对禁止直接复制粘贴纯英文段落！为了保留内行风味，你可以不翻译特定的英文黑话、梗或专有名词，但整体含义必须翻译为流畅的中文！

【输出结构规范】
<REPORT>
  <COVER title="5-10字中文爆款标题" prompt="100字英文图生图提示词，赛博朋克风" insight="30字内核心洞察，中文"/>
  <PULSE>用一句话总结今日最核心的 1-2 个行业动态信号。</PULSE>
  
  <THEMES>
    <THEME type="shift" emoji="⚔️">
      <TITLE>主题标题：副标题 (请挖掘 5-8 个独立话题，不要过度合并)</TITLE>
      <NARRATIVE>一句话核心判断</NARRATIVE>
      <TWEET account="信息源(人名或媒体)" role="身份标签">【严禁纯英文】以中文为主翻译原文或资讯的核心观点</TWEET>
      <TWEET account="..." role="...">...</TWEET>
      <CONSENSUS>核心共识的纯文本描述</CONSENSUS>
      <DIVERGENCE>最大分歧或未解之谜</DIVERGENCE>
    </THEME>

    <THEME type="new" emoji="🌱">
      <TITLE>主题标题：副标题</TITLE>
      <NARRATIVE>一句话新趋势定义</NARRATIVE>
      <TWEET account="信息源" role="身份标签">【严禁纯英文】以中文为主翻译核心观点</TWEET>
      <TWEET account="..." role="...">...</TWEET>
      <OUTLOOK>对该新叙事的深度解读与未来展望</OUTLOOK>
      <OPPORTUNITY>可能带来的机会</OPPORTUNITY>
      <RISK>警惕的陷阱或风险</RISK>
    </THEME>
  </THEMES>

  <INVESTMENT_RADAR>
    <ITEM category="投融资快讯">综合多源情报提取的融资额与机构等。</ITEM>
    <ITEM category="VC views">顶级机构投资风向警示等。</ITEM>
  </INVESTMENT_RADAR>

  <RISK_CHINA_VIEW>
    <ITEM category="中国 AI 评价">对中国大模型的技术评价等。</ITEM>
    <ITEM category="地缘与监管">出口、合规、版权风险等。</ITEM>
  </RISK_CHINA_VIEW>

  <TOP_PICKS>
    <TWEET account="..." role="...">【严禁纯英文】流畅中文精译，保留关键英文梗增强表现力</TWEET>
  </TOP_PICKS>
</REPORT>

# 外部宏观情报与新物种 (Perplexity):
{macro_info if macro_info else "未获取到宏观数据"}

# 外部领袖动态补充与全网热点 (Tavily):
{tavily_info if tavily_info else "未获取到补充数据"}

# X平台一手原始数据输入 (RapidAPI JSONL):
{combined_jsonl}

# 日期: {today_str}
"""

def llm_call_xai(combined_jsonl: str, today_str: str, macro_info: str, tavily_info: str) -> str:
    api_key = XAI_API_KEY.strip()
    if not api_key:
        print("[LLM/xAI] WARNING: XAI_API_KEY not configured!", flush=True)
        return ""

    max_data_chars = 100000 
    data = combined_jsonl[:max_data_chars] if len(combined_jsonl) > max_data_chars else combined_jsonl
    prompt = _build_xml_prompt(data, today_str, macro_info, tavily_info)
    
    model_name = "grok-4.20-beta-latest-non-reasoning" 

    print(f"\n[LLM/xAI] Requesting {model_name} via Official xai-sdk...", flush=True)
    client = Client(api_key=api_key)
    
    for attempt in range(1, 4):
        try:
            chat = client.chat.create(model=model_name)
            chat.append(system("You are a professional analytical bot. You strictly output in XML format as instructed. Do not ignore the translation rules."))
            chat.append(user(prompt))
            
            result = chat.sample().content.strip()
            print(f"[LLM/xAI] OK Response received ({len(result)} chars)", flush=True)
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
# 🚀 第三阶段：结构化渲染引擎 (双模态自适应)
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

    add_list_section("资本与估值雷达 (Investment Radar)", "💰", parsed_data["investment_radar"])
    add_list_section("风险与中国视角 (Risk & China View)", "📊", parsed_data["risk_china_view"])

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
            "elements": elements + [{"tag": "note", "elements": [{"tag": "plain_text", "content": "Powered by RapidAPI + Perplexity + Tavily + xAI"}]}]
        }
    }

    for url in webhooks:
        try:
            requests.post(url, json=card_payload, timeout=20)
            print(f"[Push/Feishu] OK Card sent to {url.split('/')[-1][:8]}...", flush=True)
        except Exception as e:
            print(f"[Push/Feishu] ERROR: {e}", flush=True)

# 🚨 微信极致精简排版：去掉一切多余空行，融合标题 🚨
def render_wechat_html(parsed_data: dict, cover_url: str = "") -> str:
    html_lines = []
    
    if cover_url: 
        html_lines.append(f'<p style="text-align:center;margin:0 0 16px 0;"><img src="{cover_url}" style="max-width:100%;border-radius:8px;" /></p>')
    
    # 融合主标题与 Insight
    if parsed_data["cover"].get("insight"):
        main_title = parsed_data["cover"].get("title", "")
        header_text = f"💡 Insight | {main_title} | 昨晚硅谷在聊啥？" if main_title else "💡 Insight | 昨晚硅谷在聊啥？"
        html_lines.append(f'<div style="border-radius:8px;background:#FFF7E6;padding:12px 14px;margin:0 0 20px 0;color:#d97706;"><div style="font-weight:bold;margin-bottom:6px;">{header_text}</div><div>{parsed_data["cover"]["insight"]}</div></div>')

    def make_h3(title): return f'<h3 style="margin:24px 0 12px 0;font-size:18px;border-left:4px solid #4A90E2;padding-left:10px;color:#2c3e50;font-weight:bold;">{title}</h3>'
    def make_quote(content): return f'<div style="background:#f8f9fa;border-left:4px solid #8c98a4;padding:10px 14px;color:#555;font-size:15px;border-radius:0 4px 4px 0;margin:6px 0 10px 0;line-height:1.6;">{content}</div>'

    html_lines.append(make_h3("⚡️ 今日看板 (The Pulse)"))
    html_lines.append(make_quote(parsed_data.get('pulse', '')))

    if parsed_data["themes"]:
        html_lines.append(make_h3("🧠 深度叙事追踪"))
        for idx, theme in enumerate(parsed_data["themes"]):
            # 🚨 增加视觉隔断：在非第一个小主题之前，加入一条优雅的浅色实线
            if idx > 0:
                html_lines.append('<hr style="border:none;border-top:1px solid #cbd5e1;margin:32px 0 24px 0;"/>')

            html_lines.append(f'<p style="font-weight:bold;font-size:16px;color:#1e293b;margin:16px 0 8px 0;">{theme["emoji"]} {theme["title"]}</p>')
            
            if theme.get("type") == "new":
                html_lines.append(f'<div style="background:#f4f8fb; padding:10px 12px; border-radius:6px; margin:0 0 8px 0; font-size:14px; color:#2c3e50;"><strong>🔭 新叙事观察：</strong>{theme["narrative"]}</div>')
            else:
                html_lines.append(f'<div style="background:#f4f8fb; padding:10px 12px; border-radius:6px; margin:0 0 8px 0; font-size:14px; color:#2c3e50;"><strong>💡 叙事转向：</strong>{theme["narrative"]}</div>')
                
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
        for item in items: 
            html_lines.append(f'<p style="margin:10px 0;font-size:15px;line-height:1.6;">👉 <strong style="color:#2c3e50;">{item["category"]}：</strong><span style="color:#333;">{item["content"]}</span></p>')

    make_list_section("💰 资本与估值雷达 (Investment Radar)", parsed_data["investment_radar"])
    make_list_section("📊 风险与中国视角 (Risk & China View)", parsed_data["risk_china_view"])

    if parsed_data["top_picks"]:
        html_lines.append(make_h3("📣 今日精选推文 (Top 5 Picks)"))
        for t in parsed_data["top_picks"]:
             html_lines.append(f'<p style="margin:12px 0 4px 0;font-size:14px;font-weight:bold;color:#2c3e50;">🗣️ @{t["account"]} <span style="color:#94a3b8;font-weight:normal;">| {t["role"]}</span></p>')
             html_lines.append(make_quote(f'"{t["content"]}"'))

    return "".join(html_lines)


def generate_cover_image(prompt):
    if not SF_API_KEY or not prompt: return ""
    try:
        resp = requests.post(URL_SF_IMAGE, headers={"Authorization": f"Bearer {SF_API_KEY}", "Content-Type": "application/json"}, json={"model": "black-forest-labs/FLUX.1-schnell", "prompt": prompt, "n": 1, "image_size": "1024x576"}, timeout=60)
        if resp.status_code == 200: return resp.json().get("images", [{}])[0].get("url") or resp.json().get("data", [{}])[0].get("url")
    except: pass
    return ""

def upload_to_imgbb_via_url(sf_url):
    if not IMGBB_API_KEY or not sf_url: return sf_url 
    try:
        img_resp = requests.get(sf_url, timeout=30)
        img_b64 = base64.b64encode(img_resp.content).decode("utf-8")
        upload_resp = requests.post(URL_IMGBB, data={"key": IMGBB_API_KEY, "image": img_b64}, timeout=45)
        if upload_resp.status_code == 200: return upload_resp.json()["data"]["url"]
    except: pass
    return sf_url

def push_to_jijyun(html_content, title, cover_url=""):
    if not JIJYUN_WEBHOOK_URL: return
    try: 
        requests.post(JIJYUN_WEBHOOK_URL, json={"title": title, "author": "Prinski", "html_content": html_content, "cover_jpg": cover_url}, timeout=30)
        print(f"[Push/WeChat] OK Sent to Jijyun", flush=True)
    except Exception as e: 
        print(f"  ⚠️ 推送机语警告: {e}", flush=True)

def save_daily_data(today_str: str, post_objects: list, report_text: str):
    data_dir = Path(f"data/{today_str}")
    data_dir.mkdir(parents=True, exist_ok=True)
    combined_txt = "\n".join(json.dumps(obj, ensure_ascii=False) for obj in post_objects)
    (data_dir / "combined.txt").write_text(combined_txt, encoding="utf-8")
    if report_text: (data_dir / "daily_report.txt").write_text(report_text, encoding="utf-8")

def main():
    print("=" * 60, flush=True)
    mode_str = "测试模式" if TEST_MODE else "全量模式"
    print(f"昨晚硅谷在聊啥 v9.1 (纯净Timeline + 冷启动护航版 - {mode_str})", flush=True)
    print("=" * 60, flush=True)
    print(f"🔑 成功装载 {len(TWT_KEYS)} 把 RapidAPI 密钥", flush=True)
    print(f"🔑 成功装载 {len(TAVILY_KEYS)} 把 Tavily 检索密钥", flush=True)

    today_str, _ = get_dates()
    all_raw_tweets = []
    
    # 🚨 1. 抓取巨鲸池与专家池 (原生 Timeline 接口，自动 ID 解析缓存)
    all_raw_tweets.extend(fetch_user_timeline_tweets(WHALE_ACCOUNTS, label="巨鲸"))
    all_raw_tweets.extend(fetch_user_timeline_tweets(EXPERT_ACCOUNTS, label="专家"))
    
    # 🚨 2. 抓取全网突发热点
    all_raw_tweets.extend(fetch_global_hot_tweets())
    
    if not all_raw_tweets:
        print("⚠️ 未能抓取推文，使用测试数据跳过...", flush=True)
        all_raw_tweets = [{"screen_name": "elonmusk", "text": "AI agents are replacing simple workflows everywhere.", "favorites": 10000, "created_at": "0101", "replies": 500, "t": "0101"}]
        
    all_posts_flat = []
    for t in all_raw_tweets:
        likes = t.get("favorites", 0)
        is_reply = bool(t.get("reply_to"))
        # 如果是回复别人的内容，必须达到一定赞数才保留（避免录入垃圾口水话）
        if not is_reply or likes >= 5:
            all_posts_flat.append({
                "a": t.get("screen_name", "Unknown"), 
                "tweet_id": t.get("tweet_id", ""),
                "l": likes, 
                "r": t.get("replies", 0),
                "t": t.get("t", parse_twitter_date(t.get("created_at", ""))), 
                "s": re.sub(r'https?://\S+', '', t.get("text", "")).strip()[:600], 
                "qt": t.get("quote_text", "")[:200]
            })

    all_posts_flat.sort(key=lambda x: x["l"], reverse=True)
    
    lower_whales = set(a.lower() for a in WHALE_ACCOUNTS)
    lower_experts = set(a.lower() for a in EXPERT_ACCOUNTS)
    
    whale_feed, expert_feed, global_feed = [], [], []
    account_counts = {}
    
    for t in all_posts_flat:
        if len(t.get("s", "")) <= 20: continue
        author = t.get("a", "Unknown").lower()
        if account_counts.get(author, 0) >= 3: continue
            
        account_counts[author] = account_counts.get(author, 0) + 1
        
        if author in lower_whales: whale_feed.append(t)
        elif author in lower_experts: expert_feed.append(t)
        else: global_feed.append(t)

    # 强制配额：限制输送给 LLM 的总数据量，防止超时
    final_feed = whale_feed[:10] + expert_feed[:50] + global_feed[:15]

    top_3_tweets = [t for t in final_feed if t.get("tweet_id")][:3]
    print(f"\n[深挖] 锁定今日最具争议的 {len(top_3_tweets)} 大话题，开始抓取评论区...")
    for t in top_3_tweets:
        comments = fetch_top_comments(t["tweet_id"])
        if comments: t["hot_comments"] = comments 

    combined_jsonl = "\n".join(json.dumps(obj, ensure_ascii=False) for obj in final_feed)

    # 🚨 3. 融合 Perplexity 宏观情报与 Tavily 外部动态
    macro_info = fetch_macro_with_perplexity()
    tavily_leaders_info = fetch_leaders_with_tavily(WHALE_ACCOUNTS + EXPERT_ACCOUNTS)
    tavily_global_info = fetch_global_news_with_tavily()
    
    tavily_info = ""
    if tavily_leaders_info: tavily_info += tavily_leaders_info + "\n\n"
    if tavily_global_info: tavily_info += tavily_global_info

    print(f"\n[Data] 三路源汇聚完毕，准备移交 xAI 进行超级排版...")

    if combined_jsonl.strip() or macro_info or tavily_info:
        xml_result = llm_call_xai(combined_jsonl, today_str, macro_info, tavily_info)
        if xml_result:
            print("\n[Parser] Parsing XML to structured data...", flush=True)
            parsed_data = parse_llm_xml(xml_result)
            
            cover_url = ""
            if parsed_data["cover"]["prompt"]:
                sf_url = generate_cover_image(parsed_data["cover"]["prompt"])
                cover_url = upload_to_imgbb_via_url(sf_url) if sf_url else ""
            
            render_feishu_card(parsed_data, today_str)
                
            if JIJYUN_WEBHOOK_URL:
                html_content = render_wechat_html(parsed_data, cover_url)
                wechat_title = parsed_data["cover"]["title"] or f"昨晚硅谷在聊啥 | {today_str}"
                push_to_jijyun(html_content, title=wechat_title, cover_url=cover_url)
                
            save_daily_data(today_str, final_feed, xml_result)
            print("\n🎉 V9.1 运行完毕！", flush=True)
        else:
            print("❌ LLM 处理失败，任务终止。")

if __name__ == "__main__":
    main()

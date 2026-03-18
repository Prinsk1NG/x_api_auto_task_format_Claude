# -*- coding: utf-8 -*-
"""
x_api_auto_task_xai_xml.py  v10.2 (网感标题优化 + 微信极简标头版 + 多端推送支持)
Architecture: TwitterAPI.io -> PPLX/Tavily (Restricted) -> xAI SDK (Isolated Prompt)
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

# 🚨 飞书多通道路由
def get_feishu_webhooks() -> list:
    urls = []
    for suffix in ["", "_1", "_2", "_3"]:
        url = os.getenv(f"FEISHU_WEBHOOK_URL{suffix}", "")
        if url: urls.append(url)
    return urls

# 🚨 微信推送多通道路由配置
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
# 🚀 外部情报检索：思路3落实 (收缩搜索域，成为客观查数机器人)
# ==============================================================================
def fetch_macro_with_perplexity() -> str:
    if not PPLX_API_KEY: return ""
    print("\n🕵️ [宏观新闻官] 呼叫 Perplexity 获取硬核数据...", flush=True)
    try:
        prompt = """你是顶级 AI 行业分析师。请仅检索过去 24 小时内 AI 行业的【硬核客观数据】。
        🚨 最高指令：不要宽泛的行业趋势与专家观点，只抓取以下两类具体事实，必须带具体媒体来源：
        1. 💰 具体的融资金额、领投方、重大收购案（M&A）。
        2. 🎁 GitHub 上刚刚发布或突然爆火的 AI 开源项目（带具体名字和功能），或新发布的 AI 硬件。
        绝对禁止将 "Perplexity" 作为信息来源。"""
        
        headers = {"Authorization": f"Bearer {PPLX_API_KEY}", "Content-Type": "application/json"}
        payload = {"model": "sonar-pro", "messages": [{"role": "user", "content": prompt}], "temperature": 0.1}
        resp = requests.post("https://api.perplexity.ai/chat/completions", headers=headers, json=payload, timeout=60)
        if resp.status_code == 200:
            data = resp.json()["choices"][0]["message"]["content"]
            print(f"  ✅ Perplexity 宏观客观数据收集完毕 ({len(data)} 字)", flush=True)
            return data
    except Exception as e: print(f"  ❌ Perplexity 抛出异常: {e}", flush=True)
    return ""

def fetch_leaders_with_tavily(accounts: list) -> str:
    if not TAVILY_KEYS: return ""
    track_list = accounts[:45]
    print(f"\n🐦 [领袖盯盘员] 扫描 {len(track_list)} 位核心大佬的站外动态...", flush=True)
    chunk_size = 15
    leader_chunks = [",".join(track_list[i:i + chunk_size]) for i in range(0, len(track_list), chunk_size)]
    url = "https://api.tavily.com/search"
    headers = {"Content-Type": "application/json"}
    aggregated_context = ""

    for i, chunk in enumerate(leader_chunks, 1):
        current_tk = get_random_tavily_key()
        try:
            payload = {"api_key": current_tk, "query": f"Today's AI tech news from: {chunk}", "search_depth": "advanced", "topic": "news", "days": 1, "include_answer": True}
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
    print(f"\n🌍 [全网雷达] 扫描全球 AI 硬核项目...", flush=True)
    current_tk = get_random_tavily_key()
    url = "https://api.tavily.com/search"
    headers = {"Content-Type": "application/json"}
    payload = {"api_key": current_tk, "query": "AI startup funding, mergers and acquisitions, new AI hardware releases, and trending open-source AI GitHub projects globally in the last 24 hours", "search_depth": "advanced", "topic": "news", "days": 1, "include_answer": True}
    aggregated_context = ""
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=45)
        if response.status_code == 200:
            data = response.json()
            aggregated_context += f"### [Tavily 全网客观数据]\n" + data.get("answer", "")
            for result in data.get("results", [])[:5]:
                aggregated_context += f"\n- [{result['title']}]({result['url']}): {result['content']}"
            print("  ✅ Tavily 全网客观热点扫描完毕。", flush=True)
    except: pass
    return aggregated_context

# ==============================================================================
# 🚀 第一阶段：TwitterAPI.io 强大且纯净的原生抓取
# ==============================================================================
def parse_tweets_recursive(data) -> list:
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

                t_id = obj.get("rest_id") or obj.get("id_str") or obj.get("id") or obj.get("tweet_id")
                if not t_id and obj.get("legacy"): t_id = obj["legacy"].get("id_str")
                
                fav = obj.get("favorite_count") or obj.get("favorites") or obj.get("likes") or obj.get("like_count") or 0
                if not fav and obj.get("legacy"): fav = obj["legacy"].get("favorite_count", 0)
                
                rep = obj.get("reply_count") or obj.get("replies") or 0
                if not rep and obj.get("legacy"): rep = obj["legacy"].get("reply_count", 0)
                
                created_at = obj.get("created_at")
                if not created_at and obj.get("legacy"): created_at = obj["legacy"].get("created_at", "")
                
                reply_to = obj.get("in_reply_to_screen_name") or obj.get("reply_to") or obj.get("is_reply")
                if not reply_to and obj.get("legacy"): reply_to = obj["legacy"].get("in_reply_to_screen_name")
                
                if str(t_id) and sn:
                    all_tweets.append({
                        "tweet_id": str(t_id), "screen_name": sn, "text": text,
                        "favorites": safe_int(fav), "replies": safe_int(rep), 
                        "created_at": created_at, "reply_to": reply_to,
                    })
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

def fetch_tweets_twitterapi_io(accounts: list, label: str) -> list:
    if not TWITTERAPI_IO_KEY: 
        print(f"⚠️ 未配置 twitterapi_io_KEY，跳过{label}抓取", flush=True)
        return []
    
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
    all_tweets = []
    
    print(f"\n⏳ [{label}扫盘] 启动 TwitterAPI.io 点对点扫描，共 {len(accounts)} 人...", flush=True)
    
    headers = {"X-API-Key": TWITTERAPI_IO_KEY}
    url = "https://api.twitterapi.io/twitter/tweet/advanced_search"
    
    for username in accounts:
        query = f"from:{username} since:{yesterday} -filter:retweets"
        params = {"query": query, "queryType": "Latest"}
        
        try:
            resp = requests.get(url, headers=headers, params=params, timeout=25)
            if resp.status_code == 200:
                tweets = parse_tweets_recursive(resp.json())
                for t in tweets:
                    t["t"] = parse_twitter_date(t.get("created_at", ""))
                all_tweets.extend(tweets)
            else: pass
        except Exception: pass
        time.sleep(1) 
        
    return all_tweets

def fetch_mentions_twitterapi(accounts: list) -> list:
    if not TWITTERAPI_IO_KEY: return []
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
    all_tweets = []
    
    print(f"\n🗣️ [外部互动] 抓取别人对核心大佬的高赞提及 (Mentions)...", flush=True)
    headers = {"X-API-Key": TWITTERAPI_IO_KEY}
    url = "https://api.twitterapi.io/twitter/tweet/advanced_search"
    
    for username in accounts:
        query = f"@{username} since:{yesterday} min_faves:50 -filter:retweets"
        params = {"query": query, "queryType": "Top"}
        try:
            resp = requests.get(url, headers=headers, params=params, timeout=25)
            if resp.status_code == 200:
                tweets = parse_tweets_recursive(resp.json())
                for t in tweets: t["t"] = parse_twitter_date(t.get("created_at", ""))
                all_tweets.extend(tweets)
        except: pass
        time.sleep(1)
    return all_tweets

def fetch_global_hot_tweets_twitterapi() -> list:
    if not TWITTERAPI_IO_KEY: return []
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
    all_tweets = []
    
    print(f"\n📡 [X平台热点] 扫描全球 AI 突发热点...", flush=True)
    queries = [
        f'(AI OR "artificial intelligence" OR LLM OR OpenAI OR xAI OR Grok OR Anthropic) since:{yesterday} min_faves:300 -filter:retweets',
        f'(AI OR LLM) (release OR launch OR breakthrough) since:{yesterday} min_faves:100 -filter:retweets'
    ]
    
    headers = {"X-API-Key": TWITTERAPI_IO_KEY}
    url = "https://api.twitterapi.io/twitter/tweet/advanced_search"
    
    for idx, q in enumerate(queries, 1):
        params = {"query": q, "queryType": "Top"}
        try:
            resp = requests.get(url, headers=headers, params=params, timeout=25)
            if resp.status_code == 200:
                tweets = parse_tweets_recursive(resp.json())
                for t in tweets: t["t"] = parse_twitter_date(t.get("created_at", ""))
                all_tweets.extend(tweets)
                print(f"    ✅ 策略 {idx} 成功捕获 {len(tweets)} 条。")
        except: pass
        time.sleep(1)
        
    return all_tweets


# ==============================================================================
# 🚀 第二阶段：多源融合 xAI XML 提示词与大模型调用 
# ==============================================================================
def _build_xml_prompt(combined_jsonl: str, today_str: str, macro_info: str, tavily_info: str) -> str:
    return f"""
你是一位顶级的 AI 行业一级市场投资分析师及新媒体主编。
请结合提供的【多源情报】，提炼出有投资和实操价值的洞察，用犀利、专业的中文进行总结。

【情报等级与职权隔离铁律】（🚨极其重要）：
1. X平台一手推文（JSONL）是【绝对的主干】。你必须且只能使用推文数据来生成 <THEMES>（深度叙事追踪）和 <TOP_PICKS>（精选推文）。
2. Perplexity 和 Tavily 提供的情报仅作为【客观背景补充】。你只能使用它们来填充 <INVESTMENT_RADAR>（资本雷达）、<RISK_CHINA_VIEW>和客观的新硬件发布。绝对不允许让外部媒体的二手观点冲淡 X 平台上一手大V的探讨！

【输出结构规范】
<REPORT>
  <COVER title="10-20字极具吸引力的中文单主题爆款标题" prompt="100字英文图生图提示词，赛博朋克风" insight="30字内核心洞察，中文"/>
  <PULSE>用一句话总结今日最核心的 1-2 个行业动态信号。</PULSE>
  
  <THEMES>
    <THEME type="shift" emoji="⚔️">
      <TITLE>主题标题：副标题 (请挖掘 5-8 个独立话题)</TITLE>
      <NARRATIVE>一句话核心判断</NARRATIVE>
      <TWEET account="信息源(人名或媒体)" role="身份标签">以中文为主翻译原文的核心观点</TWEET>
      <TWEET account="..." role="...">...</TWEET>
      <CONSENSUS>核心共识的纯文本描述</CONSENSUS>
      <DIVERGENCE>最大分歧或未解之谜</DIVERGENCE>
    </THEME>

    <THEME type="new" emoji="🌱">
      <TITLE>主题标题：副标题</TITLE>
      <NARRATIVE>一句话新趋势定义</NARRATIVE>
      <TWEET account="信息源" role="身份标签">以中文为主翻译核心观点</TWEET>
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
    <TWEET account="..." role="...">...</TWEET>
    <TWEET account="..." role="...">...</TWEET>
  </TOP_PICKS>
</REPORT>

# 外部客观数据背景 (Perplexity):
{macro_info if macro_info else "未获取到宏观数据"}

# 外部客观数据背景 (Tavily):
{tavily_info if tavily_info else "未获取到补充数据"}

# X平台一手原始数据输入 (绝对主干 JSONL):
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

# 🚨 微信多端推送配置
def push_to_wechat(html_content, title, cover_url=""):
    webhooks = get_wechat_webhooks()
    if not webhooks: return
    
    payload = {
        "title": title, 
        "author": "Prinski", 
        "html_content": html_content, 
        "cover_jpg": cover_url
    }
    
    for url in webhooks:
        try: 
            requests.post(url, json=payload, timeout=30)
            print(f"[Push/WeChat] OK Sent to {url.split('//')[-1][:15]}...", flush=True)
        except Exception as e: 
            print(f"  ⚠️ 推送微信警告: {e}", flush=True)

def save_daily_data(today_str: str, post_objects: list, report_text: str):
    data_dir = Path(f"data/{today_str}")
    data_dir.mkdir(parents=True, exist_ok=True)
    combined_txt = "\n".join(json.dumps(obj, ensure_ascii=False) for obj in post_objects)
    (data_dir / "combined.txt").write_text(combined_txt, encoding="utf-8")
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
        for t in theme.get("tweets", []):
            used_accounts.add(t.get("account", "").lower())
    for t in parsed_data.get("top_picks", []):
        used_accounts.add(t.get("account", "").lower())
        
    for t in final_feed:
        acc = t.get("a", "unknown").lower()
        if acc not in stats:
            stats[acc] = {"fetched_days": 0, "total_tweets": 0, "used_in_reports": 0, "last_active": ""}
        stats[acc]["total_tweets"] += 1
        stats[acc]["last_active"] = today_str
        
    for acc in used_accounts:
        acc_clean = acc.replace("@", "")
        if acc_clean in stats:
            stats[acc_clean]["used_in_reports"] += 1
            
    stats_file.parent.mkdir(parents=True, exist_ok=True)
    stats_file.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[Stats] 已更新账号质量数据库 (account_stats.json)，记录 {len(used_accounts)} 位今日之星。")

def main():
    print("=" * 60, flush=True)
    mode_str = "测试模式" if TEST_MODE else "全量模式"
    print(f"昨晚硅谷在聊啥 v10.2 (网感标题优化 + 微信极简标头版 + 多端推送支持 - {mode_str})", flush=True)
    print("=" * 60, flush=True)

    if not TWITTERAPI_IO_KEY:
        print("❌ 致命错误: 未配置 twitterapi_io_KEY，程序无法继续！", flush=True)
        return

    today_str, _ = get_dates()
    all_raw_tweets = []
    
    # 🚨 1. 抓取巨鲸池与专家池 (使用 TwitterAPI.io Advanced Search)
    all_raw_tweets.extend(fetch_tweets_twitterapi_io(WHALE_ACCOUNTS, label="巨鲸"))
    all_raw_tweets.extend(fetch_tweets_twitterapi_io(EXPERT_ACCOUNTS, label="专家"))
    
    # 🚨 2. 抓取外部互动 (Mentions)
    all_raw_tweets.extend(fetch_mentions_twitterapi(WHALE_ACCOUNTS))
    
    if not all_raw_tweets:
        print("⚠️ 未能抓取推文，使用测试数据跳过...", flush=True)
        all_raw_tweets = [{"screen_name": "elonmusk", "text": "AI agents are replacing simple workflows everywhere.", "favorites": 10000, "created_at": "0101", "replies": 500, "t": "0101"}]
        
    all_posts_flat = []
    for t in all_raw_tweets:
        likes = t.get("favorites", 0)
        is_reply = bool(t.get("reply_to"))
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
    final_feed = whale_feed[:15] + expert_feed[:60] + global_feed[:20]

    combined_jsonl = "\n".join(json.dumps(obj, ensure_ascii=False) for obj in final_feed)

    # 🚨 3. 融合 Perplexity 宏观情报与 Tavily 外部动态 (已降权为纯数据补充)
    macro_info = fetch_macro_with_perplexity()
    tavily_info = fetch_global_news_with_tavily()

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
            
            # 🚨 检查是否配置了微信 Webhooks，如果配置了则循环发送
            wechat_hooks = get_wechat_webhooks()
            if wechat_hooks:
                html_content = render_wechat_html(parsed_data, cover_url)
                base_title = parsed_data["cover"]["title"] or "今日硅谷AI核心动态"
                wechat_title = f"{base_title} | 昨晚硅谷在聊啥？"
                push_to_wechat(html_content, title=wechat_title, cover_url=cover_url)
                
            # 🚨 4. 每日存档与账号数据库更新
            save_daily_data(today_str, final_feed, xml_result)
            update_account_stats(final_feed, parsed_data)
            
            print("\n🎉 V10.2 运行完毕！", flush=True)
        else:
            print("❌ LLM 处理失败，任务终止。")

if __name__ == "__main__":
    main()

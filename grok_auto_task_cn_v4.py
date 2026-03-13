# -*- coding: utf-8 -*-
"""
x_api_auto_task_xai_xml.py  v7.0 (RapidAPI抓取 + xAI XML提取 + 完美双轨渲染)
Architecture: Expert & Global Track -> RapidAPI -> xAI XML Synthesis -> Clean UI Rendering
"""

import os
import re
import json
import time
import base64
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests
from requests.exceptions import ConnectionError, Timeout

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🚨 模式切换开关 🚨
# False = 全量运行（扫 100 人 + 2次全球热点搜索，推荐！）
# True  = 测试模式（只扫前 10 人 + 2次全球热点搜索，省配额）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TEST_MODE = False

# ── 环境变量 (严格对齐 Secrets 规范) ──────────────────────────────
JIJYUN_WEBHOOK_URL  = os.getenv("JIJYUN_WEBHOOK_URL", "")
SF_API_KEY          = os.getenv("SF_API_KEY", "")
XAI_API_KEY         = os.getenv("xAI_API_KEY", "")    # 🚨 xAI API Key
TWTAPI_KEY          = os.getenv("TWTAPI_KEY", "")     # RapidAPI Key
IMGBB_API_KEY       = os.getenv("IMGBB_API_KEY", "") 

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🚨 专属你的 RapidAPI (Twttr API) 接口配置 🚨
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
RAPIDAPI_HOST = "twitter241.p.rapidapi.com"
SEARCH_PATH   = "/search-v2" 
URL_TWTAPI    = "https://" + RAPIDAPI_HOST + SEARCH_PATH
COMMENTS_PATH = "/comments-v2"
URL_COMMENTS  = "https://" + RAPIDAPI_HOST + COMMENTS_PATH

# ── Base64 URL 隐身术 ─────────
def D(b64_str):
    return base64.b64decode(b64_str).decode("utf-8")

URL_SF_IMAGE   = D("aHR0cHM6Ly9hcGkuc2lsaWNvbmZsb3cuY24vdjEvaW1hZ2VzL2dlbmVyYXRpb25z")
URL_IMGBB      = D("aHR0cHM6Ly9hcGkuaW1nYmIuY29tLzEvdXBsb2Fk")

# ── 100 核心账号名单 ──────────────────────────────────────────────
ALL_ACCOUNTS = [
    "elonmusk", "sama", "karpathy", "demishassabis", "darioamodei",
    "OpenAI", "AnthropicAI", "GoogleDeepMind", "xAI", "AIatMeta",
    "GoogleAI", "MSFTResearch", "IlyaSutskever", "gregbrockman",
    "GaryMarcus", "rowancheung", "clmcleod", "bindureddy",
    "dotey", "oran_ge", "vista8", "imxiaohu", "Sxsyer",
    "K_O_D_A_D_A", "tualatrix", "linyunqiu", "garywong", "web3buidl",
    "AI_Era", "AIGC_News", "jiangjiang", "hw_star", "mranti", "nishuang",
    "a16z", "ycombinator", "lightspeedvp", "sequoia", "foundersfund",
    "eladgil", "pmarca", "bchesky", "chamath", "paulg",
    "TheInformation", "TechCrunch", "verge", "WIRED", "Scobleizer", "bentossell",
    "HuggingFace", "MistralAI", "Perplexity_AI", "GroqInc", "Cohere",
    "TogetherCompute", "runwayml", "Midjourney", "StabilityAI", "Scale_AI",
    "CerebrasSystems", "tenstorrent", "weights_biases", "langchainai", "llama_index",
    "supabase", "vllm_project", "huggingface_hub",
    "nvidia", "AMD", "Intel", "SKhynix", "tsmc",
    "magicleap", "NathieVR", "PalmerLuckey", "ID_AA_Carmack", "boz",
    "rabovitz", "htcvive", "XREAL_Global", "RayBan", "MetaQuestVR", "PatrickMoorhead",
    "jeffdean", "chrmanning", "hardmaru", "goodfellow_ian", "feifeili",
    "_akhaliq", "promptengineer", "AI_News_Tech", "siliconvalley", "aithread",
    "aibreakdown", "aiexplained", "aipubcast", "lexfridman", "hubermanlab", "swyx",
]

if TEST_MODE:
    ALL_ACCOUNTS = ALL_ACCOUNTS[:10]

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
# 🚀 第一阶段：降维解析与抓取引擎 (保持原样)
# ==============================================================================
def parse_rapidapi_tweets(data) -> list:
    all_tweets = []
    
    def recurse(obj):
        if isinstance(obj, dict):
            text = obj.get("full_text") or obj.get("text")
            if not text and obj.get("legacy"):
                text = obj["legacy"].get("full_text") or obj["legacy"].get("text")
                
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
                    if sn_match:
                        sn = sn_match.group(1)
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
                            "tweet_id": str(t_id),
                            "screen_name": sn,
                            "text": text,
                            "favorites": safe_int(fav),
                            "replies": safe_int(rep), 
                            "created_at": created_at,
                            "reply_to": reply_to,
                        })
                        return 
            
            for v in obj.values(): recurse(v)
        elif isinstance(obj, list):
            for item in obj: recurse(item)

    recurse(data)
    
    seen, unique = set(), []
    for t in all_tweets:
        tid = t["tweet_id"]
        if tid not in seen:
            seen.add(tid)
            unique.append(t)
            
    return unique

def fetch_all_tweets_batched(accounts: list) -> list:
    if not TWTAPI_KEY: return []
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
    chunk_size = 10
    chunks = [accounts[i:i + chunk_size] for i in range(0, len(accounts), chunk_size)]
    
    all_tweets = []
    headers = {"x-rapidapi-key": TWTAPI_KEY, "x-rapidapi-host": RAPIDAPI_HOST}
    consecutive_errors = 0  

    for i, chunk in enumerate(chunks, 1):
        if consecutive_errors >= 2: break
        print(f"\n⏳ [专家扫盘] 第 {i}/{len(chunks)} 批账号...", flush=True)
        query = " OR ".join([f"from:{acc}" for acc in chunk])
        params = {"query": f"({query}) since:{yesterday} -is:retweet", "type": "Latest", "count": "40"}
        
        success = False
        for attempt in range(3):
            try:
                resp = requests.get(URL_TWTAPI, headers=headers, params=params, timeout=25)
                if resp.status_code == 200:
                    tweets = parse_rapidapi_tweets(resp.json())
                    all_tweets.extend(tweets)
                    print(f"  ✅ 提取 {len(tweets)} 条。")
                    consecutive_errors = 0 
                    success = True
                    break
                elif resp.status_code in [403, 404]:
                    consecutive_errors += 1
                    time.sleep(2)
                    if consecutive_errors >= 2: break 
                else: time.sleep(2)
            except Exception as e:
                print(f"  ⚠️ 搜索接口异常: {e}", flush=True)
                time.sleep(2)
                
        if success: time.sleep(1.5)
        else: time.sleep(3)

    print(f"\n📡 [全网探测] 启动策略扫描全球突发热点...", flush=True)
    grok_queries = [
        f'(AI OR "artificial intelligence" OR LLM OR OpenAI OR xAI OR Grok OR Anthropic OR DeepMind OR Claude) since:{yesterday} min_faves:50 -is:retweet',
        f'(AI OR LLM) (release OR launch OR breakthrough OR update) since:{yesterday} min_faves:30 (filter:links OR filter:media) -is:retweet'
    ]

    for idx, q in enumerate(grok_queries, 1):
        print(f"  🔍 执行策略 {idx}/2...", flush=True)
        params_discovery = {"query": q, "type": "Top", "count": "20"}
        for attempt in range(3):
            try:
                resp = requests.get(URL_TWTAPI, headers=headers, params=params_discovery, timeout=25)
                if resp.status_code == 200:
                    tweets = parse_rapidapi_tweets(resp.json())
                    all_tweets.extend(tweets)
                    print(f"    ✅ 策略 {idx} 成功，全网捕获 {len(tweets)} 条高赞情报。")
                    break
                elif resp.status_code in [403, 404]: break 
                else: time.sleep(2)
            except Exception as e:
                print(f"  ⚠️ 全网探测接口异常: {e}", flush=True)
                time.sleep(2)
        time.sleep(1.5)
        
    return all_tweets

def fetch_top_comments(tweet_id: str) -> list:
    if not tweet_id or not TWTAPI_KEY: return []
    print(f"  🎯 [爆破] 正在深挖神评 (Tweet ID: {tweet_id})...", flush=True)
    headers = {"x-rapidapi-key": TWTAPI_KEY, "x-rapidapi-host": RAPIDAPI_HOST}
    try:
        resp = requests.get(URL_COMMENTS, headers=headers, params={"pid": tweet_id, "rankingMode": "Relevance", "count": "20"}, timeout=25)
        if resp.status_code == 200:
            raw_comments = parse_rapidapi_tweets(resp.json())
            return [f"@{c['screen_name']}: {c['text'][:150]}" for c in raw_comments if len(c.get("text", "")) > 10][:5]
    except Exception as e: 
        print(f"  ⚠️ 获取神评警告: {e}", flush=True)
    return []


# ==============================================================================
# 🚀 第二阶段：纯 XML 提示词与大模型调用 (核心替换区域)
# ==============================================================================
def _build_xml_prompt(combined_jsonl: str, today_str: str) -> str:
    return f"""
你是一位顶级的 AI 行业一级市场投资分析师。
分析过去24小时内科技大佬的推文和全球热点，特别是带有 "hot_comments"（代表行业共识或争议）的数据。
请提炼出有投资和实操价值的洞察，用犀利、专业的中文进行总结，推文必须全面、高质量地翻译为中文。

【重要纪律】
1. 禁止输出任何 Markdown 排版符号（如 #, *, >, -）。
2. 只允许输出纯文本内容，并严格按照以下 XML 标签结构填入信息。不要改变标签名称，不要缺漏闭合标签。
3. 语气要直白、干脆。Title（头衔/身份）和名字绝对不要翻译为中文，保持纯英文。

【输出结构规范】
<REPORT>
  <COVER title="5-10字中文爆款标题" prompt="100字英文图生图提示词，赛博朋克风" insight="30字内核心洞察，中文"/>
  
  <PULSE>用一句话总结今日最核心的 1-2 个行业动态信号。</PULSE>
  
  <THEMES>
    <THEME title="主题标题：副标题 (请输出3-5个重要的话题方向)">
      <NARRATIVE>叙事转向：一句话核心判断。</NARRATIVE>
      <TWEET account="X账号名(不带@)" role="英文身份标签">具体行为与观点提炼</TWEET>
      <TWEET account="..." role="...">...</TWEET>
      
      <CONSENSUS>核心共识的纯文本描述</CONSENSUS>
      <DIVERGENCE>最大分歧的纯文本描述</DIVERGENCE>
    </THEME>
  </THEMES>

  <INVESTMENT_RADAR>
    <ITEM category="投融资快讯">具体的融资额与领投机构等。</ITEM>
    <ITEM category="VC views">顶级机构投资风向警示等。</ITEM>
  </INVESTMENT_RADAR>

  <RISK_CHINA_VIEW>
    <ITEM category="中国 AI 评价">对中国大模型的技术评价等。</ITEM>
    <ITEM category="地缘与监管">出口、合规、版权风险等。</ITEM>
  </RISK_CHINA_VIEW>

  <TOP_PICKS>
    <TWEET account="..." role="...">原文必须全面高质量翻译为中文，保持原意</TWEET>
    <TWEET account="..." role="...">...</TWEET>
  </TOP_PICKS>
</REPORT>

# 原始数据输入 (JSONL):
{combined_jsonl}

# 日期: {today_str}
"""

def llm_call_xai(combined_jsonl: str, today_str: str) -> str:
    if not XAI_API_KEY:
        print("[LLM] WARNING: xAI_API_KEY not configured!", flush=True)
        return ""

    api_key = XAI_API_KEY.strip() # 防隐形换行符
    max_data_chars = 100000 
    data = combined_jsonl[:max_data_chars] if len(combined_jsonl) > max_data_chars else combined_jsonl
    prompt = _build_xml_prompt(data, today_str)
    
    model_name = "grok-2-latest" 

    print(f"[LLM/xAI] Requesting {model_name}...", flush=True)
    for attempt in range(1, 4):
        try:
            resp = requests.post(
                "https://api.x.ai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model_name,
                    "messages": [
                        {"role": "system", "content": "You are a professional analytical bot. You strictly output in XML format as instructed, without any markdown backticks."},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.6,
                    "max_tokens": 4096, # 强制给足 Token 上限防拦截
                },
                timeout=180,
            )
            
            resp.raise_for_status() 
            result = resp.json()["choices"][0]["message"]["content"].strip()
            print(f"[LLM/xAI] OK Response received ({len(result)} chars)", flush=True)
            return result
            
        except requests.exceptions.HTTPError as e:
            print(f"[LLM/xAI] Attempt {attempt} failed: {e}", flush=True)
            if e.response is not None:
                print(f"[LLM/xAI] 🚨 ERROR DETAILS: {e.response.text}", flush=True)
            time.sleep(2 ** attempt)
        except Exception as e:
            print(f"[LLM/xAI] Attempt {attempt} failed (Network/Other): {e}", flush=True)
            time.sleep(2 ** attempt)
            
    return ""

def parse_llm_xml(xml_text: str) -> dict:
    data = {
        "cover": {"title": "", "prompt": "", "insight": ""},
        "pulse": "",
        "themes": [],
        "investment_radar": [],
        "risk_china_view": [],
        "top_picks": []
    }
    if not xml_text: return data

    cover_match = re.search(r'<COVER\s+title="(.*?)"\s+prompt="(.*?)"\s+insight="(.*?)"\s*/?>', xml_text, re.IGNORECASE | re.DOTALL)
    if cover_match:
        data["cover"] = {"title": cover_match.group(1).strip(), "prompt": cover_match.group(2).strip(), "insight": cover_match.group(3).strip()}
        
    pulse_match = re.search(r'<PULSE>(.*?)</PULSE>', xml_text, re.IGNORECASE | re.DOTALL)
    if pulse_match: data["pulse"] = pulse_match.group(1).strip()
        
    for theme_match in re.finditer(r'<THEME\s+title="(.*?)">(.*?)</THEME>', xml_text, re.IGNORECASE | re.DOTALL):
        theme_title = theme_match.group(1).strip()
        theme_body = theme_match.group(2)
        
        narrative_match = re.search(r'<NARRATIVE>(.*?)</NARRATIVE>', theme_body, re.IGNORECASE | re.DOTALL)
        narrative = narrative_match.group(1).strip() if narrative_match else ""
        
        tweets = []
        for t_match in re.finditer(r'<TWEET\s+account="(.*?)"\s+role="(.*?)">(.*?)</TWEET>', theme_body, re.IGNORECASE | re.DOTALL):
            tweets.append({"account": t_match.group(1).strip(), "role": t_match.group(2).strip(), "content": t_match.group(3).strip()})
        
        con_match = re.search(r'<CONSENSUS>(.*?)</CONSENSUS>', theme_body, re.IGNORECASE | re.DOTALL)
        consensus = con_match.group(1).strip() if con_match else ""
        
        div_match = re.search(r'<DIVERGENCE>(.*?)</DIVERGENCE>', theme_body, re.IGNORECASE | re.DOTALL)
        divergence = div_match.group(1).strip() if div_match else ""
        
        data["themes"].append({
            "title": theme_title, "narrative": narrative, "tweets": tweets,
            "consensus": consensus, "divergence": divergence
        })
        
    def extract_items(tag_name, target_list):
        block_match = re.search(rf'<{tag_name}>(.*?)</{tag_name}>', xml_text, re.IGNORECASE | re.DOTALL)
        if block_match:
            for item in re.finditer(r'<ITEM\s+category="(.*?)">(.*?)</ITEM>', block_match.group(1), re.IGNORECASE | re.DOTALL):
                target_list.append({"category": item.group(1).strip(), "content": item.group(2).strip()})

    extract_items("INVESTMENT_RADAR", data["investment_radar"])
    extract_items("RISK_CHINA_VIEW", data["risk_china_view"])

    picks_match = re.search(r'<TOP_PICKS>(.*?)</TOP_PICKS>', xml_text, re.IGNORECASE | re.DOTALL)
    if picks_match:
        for t_match in re.finditer(r'<TWEET\s+account="(.*?)"\s+role="(.*?)">(.*?)</TWEET>', picks_match.group(1), re.IGNORECASE | re.DOTALL):
            data["top_picks"].append({"account": t_match.group(1).strip(), "role": t_match.group(2).strip(), "content": t_match.group(3).strip()})
            
    return data


# ==============================================================================
# 🚀 第三阶段：结构化渲染引擎 (杜绝排版断裂)
# ==============================================================================
def render_feishu_card(parsed_data: dict, today_str: str):
    webhooks = get_feishu_webhooks()
    if not webhooks or not parsed_data.get("pulse"): return

    elements = []

    # 1. Pulse
    elements.append({"tag": "markdown", "content": f"**▌ ⚡️ 今日看板 (The Pulse)**\n<font color='grey'>{parsed_data['pulse']}</font>"})
    elements.append({"tag": "hr"})

    # 2. Themes
    if parsed_data["themes"]:
        elements.append({"tag": "markdown", "content": "**▌ 🧠 深度叙事追踪**"})
        for theme in parsed_data["themes"]:
            theme_md = f"**🔥 {theme['title']}**\n<font color='grey'>💡 叙事转向：{theme['narrative']}</font>\n"
            for t in theme["tweets"]:
                theme_md += f"\n🗣️ **@{t['account']} | {t['role']}**\n<font color='grey'>{t['content']}</font>\n"
            if theme.get("consensus"):
                theme_md += f"\n<font color='red'>**🔥 核心共识：**</font> {theme['consensus']}"
            if theme.get("divergence"):
                theme_md += f"\n<font color='red'>**⚔️ 最大分歧：**</font> {theme['divergence']}"
            elements.append({"tag": "markdown", "content": theme_md.strip()})
        elements.append({"tag": "hr"})

    # 3. Radar & View
    def add_list_section(title, icon, items):
        if not items: return
        content = f"**▌ {icon} {title}**\n\n"
        for item in items:
            content += f"👉 **{item['category']}**：<font color='grey'>{item['content']}</font>\n"
        elements.append({"tag": "markdown", "content": content.strip()})
        elements.append({"tag": "hr"})

    add_list_section("资本与估值雷达 (Investment Radar)", "💰", parsed_data["investment_radar"])
    add_list_section("风险与中国视角 (Risk & China View)", "📊", parsed_data["risk_china_view"])

    # 4. Top Picks
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
            "elements": elements + [{"tag": "note", "elements": [{"tag": "plain_text", "content": "Powered by RapidAPI + xAI (Grok) Pipeline"}]}]
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
    if parsed_data["cover"].get("insight"):
        html_lines.append(f'<div style="border-radius:8px;background:#FFF7E6;padding:12px 14px;margin:0 0 20px 0;color:#d97706;"><div style="font-weight:bold;margin-bottom:6px;">💡 Insight | 昨晚硅谷在聊啥？</div><div>{parsed_data["cover"]["insight"]}</div></div>')

    def make_h3(title): return f'<h3 style="margin:24px 0 12px 0;font-size:18px;border-left:4px solid #4A90E2;padding-left:10px;color:#2c3e50;font-weight:bold;">{title}</h3>'
    def make_quote(content): return f'<div style="background:#f8f9fa;border-left:4px solid #8c98a4;padding:10px 14px;color:#555;font-size:15px;border-radius:0 4px 4px 0;margin:6px 0 16px 0;line-height:1.6;">{content}</div>'

    html_lines.append(make_h3("⚡️ 今日看板 (The Pulse)"))
    html_lines.append(make_quote(parsed_data.get('pulse', '')))

    if parsed_data["themes"]:
        html_lines.append(make_h3("🧠 深度叙事追踪"))
        for theme in parsed_data["themes"]:
            html_lines.append(f'<p style="font-weight:bold;font-size:16px;color:#1e293b;margin-top:24px;">🔥 {theme["title"]}</p>')
            html_lines.append(f'<div style="background:#f4f8fb; padding:12px; border-radius:6px; margin:12px 0; font-size:14px; color:#2c3e50;"><strong>💡 叙事转向：</strong>{theme["narrative"]}</div>')
            for t in theme["tweets"]:
                html_lines.append(f'<p style="margin:12px 0 4px 0;font-size:14px;font-weight:bold;color:#2c3e50;">🗣️ @{t["account"]} <span style="color:#94a3b8;font-weight:normal;">| {t["role"]}</span></p>')
                html_lines.append(make_quote(t["content"]))
            
            if theme.get("consensus"):
                html_lines.append(f'<p style="margin:8px 0; font-size:15px; line-height:1.6; background:#fff5f5; padding: 8px 12px; border-radius: 4px;"><strong style="color:#d35400;">🔥 核心共识：</strong>{theme["consensus"]}</p>')
            if theme.get("divergence"):
                 html_lines.append(f'<p style="margin:8px 0; font-size:15px; line-height:1.6; background:#fff5f5; padding: 8px 12px; border-radius: 4px;"><strong style="color:#d35400;">⚔️ 最大分歧：</strong>{theme["divergence"]}</p>')

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

    return "<br/>".join(html_lines)


# ==============================================================================
# 附加工具 (图床上传与推送逻辑保持不变)
# ==============================================================================
def generate_cover_image(prompt):
    if not SF_API_KEY or not prompt: return ""
    try:
        resp = requests.post(URL_SF_IMAGE, headers={"Authorization": f"Bearer {SF_API_KEY}", "Content-Type": "application/json"}, json={"model": "black-forest-labs/FLUX.1-schnell", "prompt": prompt, "n": 1, "image_size": "1024x576"}, timeout=60)
        if resp.status_code == 200: return resp.json().get("images", [{}])[0].get("url") or resp.json().get("data", [{}])[0].get("url")
    except Exception as e: 
        print(f"  ⚠️ 生成封面警告: {e}", flush=True)
    return ""

def upload_to_imgbb_via_url(sf_url):
    if not IMGBB_API_KEY or not sf_url: return sf_url 
    try:
        img_resp = requests.get(sf_url, timeout=30)
        img_b64 = base64.b64encode(img_resp.content).decode("utf-8")
        upload_resp = requests.post(URL_IMGBB, data={"key": IMGBB_API_KEY, "image": img_b64}, timeout=45)
        if upload_resp.status_code == 200: return upload_resp.json()["data"]["url"]
    except Exception as e: 
        print(f"  ⚠️ 图床上传警告: {e}", flush=True)
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


# ==============================================================================
# Main Execution 🚀
# ==============================================================================
def main():
    print("=" * 60, flush=True)
    mode_str = "测试模式(10人)" if TEST_MODE else "全量模式(100人)"
    print(f"昨晚硅谷在聊啥 v7.0 (RapidAPI + xAI XML解析防断裂版 - {mode_str})", flush=True)
    print("=" * 60, flush=True)

    today_str, _ = get_dates()
    
    # 🚨 第一级与发现级：同时拉取专家数据与全网爆发热点
    all_raw_tweets = fetch_all_tweets_batched(ALL_ACCOUNTS)
    
    if not all_raw_tweets:
        print("⚠️ 未能抓取推文，使用测试数据跳过...", flush=True)
        all_raw_tweets = [{"screen_name": "elonmusk", "text": "Grok 2 is amazing!", "favorites": 10000, "created_at": "0101", "replies": 500}]
        
    all_posts_flat = []
    
    for t in all_raw_tweets:
        likes = t.get("favorites", 0)
        is_reply = bool(t.get("reply_to"))
        
        if not is_reply or likes >= 0:
            tweet_id = t.get("tweet_id", "")
            text = t.get("text", "")
            replies = t.get("replies", 0)
            
            all_posts_flat.append({
                "a": t.get("screen_name", "Unknown"), 
                "tweet_id": tweet_id,
                "l": likes, 
                "r": replies,
                "t": parse_twitter_date(t.get("created_at", "")), 
                "s": re.sub(r'https?://\S+', '', text).strip()[:600], 
                "qt": t.get("quote_text", "")[:200]
            })

    # 【第二级：高热提纯、去重与定点爆破】
    all_posts_flat.sort(key=lambda x: x["l"], reverse=True)
    
    final_feed = []
    account_counts = {}
    
    for t in all_posts_flat:
        if len(t.get("s", "")) <= 20: continue
        author = t.get("a", "Unknown")
        if account_counts.get(author, 0) >= 3: continue
            
        final_feed.append(t)
        account_counts[author] = account_counts.get(author, 0) + 1
        if len(final_feed) >= 40: break

    top_3_tweets = [t for t in final_feed if t.get("tweet_id")][:3]
    
    print(f"\n[深挖] 锁定今日最具争议的 {len(top_3_tweets)} 大话题，开始抓取评论区...")
    for t in top_3_tweets:
        comments = fetch_top_comments(t["tweet_id"])
        if comments: t["hot_comments"] = comments 

    combined_jsonl = "\n".join(json.dumps(obj, ensure_ascii=False) for obj in final_feed)
    print(f"\n[Data] 组装完成：{len(final_feed)} 条推文 (含共识提纯数据) ready for LLM.")

    # 🚨 核心更换点：调用 xAI 提取 XML 数据
    if combined_jsonl.strip():
        xml_result = llm_call_xai(combined_jsonl, today_str)
        
        if xml_result:
            print("\n[Parser] Parsing XML to structured data...", flush=True)
            parsed_data = parse_llm_xml(xml_result)
            
            # 生成封面图
            cover_url = ""
            if parsed_data["cover"]["prompt"]:
                sf_url = generate_cover_image(parsed_data["cover"]["prompt"])
                cover_url = upload_to_imgbb_via_url(sf_url) if sf_url else ""
            
            # 飞书推送
            render_feishu_card(parsed_data, today_str)
                
            # 微信推送
            if JIJYUN_WEBHOOK_URL:
                html_content = render_wechat_html(parsed_data, cover_url)
                wechat_title = parsed_data["cover"]["title"] or f"昨晚硅谷在聊啥 | {today_str}"
                push_to_jijyun(html_content, title=wechat_title, cover_url=cover_url)
                
            # 保存数据 (为了兼容原逻辑，我们把 xml_result 作为 report_text 保存下来)
            save_daily_data(today_str, final_feed, xml_result)
            print("\n🎉 V7.0 运行完毕！", flush=True)
        else:
            print("❌ LLM 处理失败，任务终止。")

if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""
x_api_auto_task_xai_xml.py v10.14 (三阶段阶梯抓取版)
1. Stage 1: Twitter List - 24h全量原创捕获
2. Stage 2: Advanced Search - 全网提及与外部回响
3. Stage 3: Deep Replies - 爆款推文下的共识挖掘
"""

import os, re, json, time, requests
from datetime import datetime, timezone, timedelta
from pathlib import Path
from xai_sdk import Client
from xai_sdk.chat import user, system

# ─── 1. 配置与环境变量 ──────────────────────────────────────────
TWITTERAPI_IO_KEY = os.getenv("twitterapi_io_KEY")
XAI_API_KEY = os.getenv("XAI_API_KEY")
PPLX_API_KEY = os.getenv("PPLX_API_KEY")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
FEISHU_WEBHOOK_URL = os.getenv("FEISHU_WEBHOOK_URL")
FEISHU_WEBHOOK_URL_1 = os.getenv("FEISHU_WEBHOOK_URL_1")

# 🚨 新增：你需要把你的 Twitter List ID 存入 GitHub Secrets
TWITTER_LIST_ID = os.getenv("TWITTER_LIST_ID") 

TEST_MODE = str(os.getenv("TEST_MODE_ENV", "false")).lower() == "true"
BJT = timezone(timedelta(hours=8))

def log_diag(step, status="INFO", msg=""):
    ts = datetime.now(BJT).strftime("%H:%M:%S")
    icon = "✅" if status == "OK" else ("❌" if status == "FAIL" else "⏳")
    print(f"[{ts}] {icon} [{step}] {msg}", flush=True)

# ─── 2. 三阶段抓取引擎 ──────────────────────────────────────────

def fetch_intelligence_3_stages(accounts):
    all_intelligence = []
    headers = {"X-API-Key": TWITTERAPI_IO_KEY}
    now_utc = datetime.now(timezone.utc)
    since_unix = int((now_utc - timedelta(hours=24)).timestamp())
    since_date = (now_utc - timedelta(hours=24)).strftime("%Y-%m-%d")

    # --- STAGE 1: List Tweets (原创与核心动态) ---
    if TWITTER_LIST_ID:
        log_diag("Stage 1", "BUSY", f"扫描列表 {TWITTER_LIST_ID} 过去24h动态...")
        list_url = f"https://api.twitterapi.io/twitter/list/tweets?listId={TWITTER_LIST_ID}&sinceTime={since_unix}"
        try:
            r = requests.get(list_url, headers=headers, timeout=30)
            if r.status_code == 200:
                list_tweets = r.json().get("tweets", [])
                # 过滤掉非原创的纯转发
                valid = [t for t in list_tweets if not t.get("isRetweet")]
                all_intelligence.extend(valid)
                log_diag("Stage 1", "OK", f"列表抓取完成，获得 {len(valid)} 条原创/回复")
        except Exception as e: log_diag("Stage 1", "FAIL", str(e))

    # --- STAGE 2: Mentions & Echoes (外部争议与回响) ---
    log_diag("Stage 2", "BUSY", "扫描全网对大佬的高赞提及...")
    # 将100人分成5组，每组20人进行批量搜索，节省调用次数
    chunks = [accounts[i:i + 20] for i in range(0, len(accounts), 20)]
    for chunk in chunks:
        query = "(" + " OR ".join([f"@{a.strip()}" for a in chunk]) + f") since:{since_date} min_faves:15 -filter:replies"
        search_url = f"https://api.twitterapi.io/twitter/tweet/advanced_search?query={query}&count=20"
        try:
            r = requests.get(search_url, headers=headers, timeout=30)
            if r.status_code == 200:
                mentions = r.json().get("tweets", [])
                all_intelligence.extend(mentions)
        except: pass
    log_diag("Stage 2", "OK", f"外部回响收集完毕，累计 {len(all_intelligence)} 条数据")

    # --- STAGE 3: Deep Dive (挖掘爆款推文下的共识) ---
    log_diag("Stage 3", "BUSY", "对 Top 10 话题进行评论区钻取...")
    # 按照点赞数选出前 10
    top_10 = sorted(all_intelligence, key=lambda x: int(x.get("favouriteCount", 0)), reverse=True)[:10]
    for t in top_10:
        tid = t.get("id")
        if not tid: continue
        replies_url = f"https://api.twitterapi.io/twitter/tweet/replies?tweetId={tid}"
        try:
            r = requests.get(replies_url, headers=headers, timeout=15)
            if r.status_code == 200:
                replies = r.json().get("tweets", [])
                # 选 2 条最高赞回复存入该推文的 context 中
                best_replies = sorted(replies, key=lambda x: int(x.get("favouriteCount", 0)), reverse=True)[:2]
                t["_deep_replies"] = [f"[@{br.get('userName')}]: {br.get('text')}" for br in best_replies]
        except: pass
    
    return all_intelligence

# ─── 3. 渲染与决策逻辑 (Grok) ───────────────────────────────────

def run_analysis_and_push(raw_data):
    if not raw_data: return
    log_diag("Grok AI", "BUSY", "正在提炼共识、分歧与机遇...")
    
    # 结构化推文流，包含 Stage 3 的回复数据
    clean_feed = ""
    for t in raw_data:
        clean_feed += f"@{t.get('userName')}: {t.get('text')}\n"
        if t.get("_deep_replies"):
            clean_feed += "  └─ [关键回响]: " + " | ".join(t["_deep_replies"]) + "\n"

    # 调用 Grok 生成 XML (逻辑同 V10.12)
    # ... 此处省略具体 API 调用 ...
    
    # 解析并推送到飞书 (逻辑同 V10.12)
    # ... 此处省略渲染代码 ...

# ─── 4. 主流程 ──────────────────────────────────────────────────

def main():
    print(f"\n{'='*20} V10.14 三阶段情报局启动 {'='*20}")
    
    # 名单
    whales = open("whales.txt").read().splitlines() if os.path.exists("whales.txt") else ["elonmusk", "sama"]
    
    # 执行三阶段抓取
    all_raw = fetch_intelligence_3_stages(whales)
    
    # 存档
    date_str = datetime.now(BJT).strftime("%Y-%m-%d")
    os.makedirs(f"data/{date_str}", exist_ok=True)
    with open(f"data/{date_str}/combined.txt", "w", encoding="utf-8") as f:
        f.write(json.dumps(all_raw, indent=2, ensure_ascii=False))

    # 后续：Grok 分析与分发
    run_analysis_and_push(all_raw)
    
    log_diag("任务状态", "OK", "三阶段情报收割完毕")

if __name__ == "__main__":
    main()

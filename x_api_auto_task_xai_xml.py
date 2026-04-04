import os
import re
import json
import requests
from datetime import datetime, timezone, timedelta
from xai_sdk import Client
from xai_sdk.chat import user, system

# ─── 1. 环境配置 ──────────────────────────────────────────────────
TWITTERAPI_IO_KEY = os.getenv("twitterapi_io_KEY")
XAI_API_KEY = os.getenv("XAI_API_KEY")
PPLX_API_KEY = os.getenv("PPLX_API_KEY")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
FEISHU_WEBHOOK_URL = os.getenv("FEISHU_WEBHOOK_URL")     # 个人调试/测试
FEISHU_WEBHOOK_URL_1 = os.getenv("FEISHU_WEBHOOK_URL_1") # 核心主群
# 严格识别测试模式
TEST_MODE = str(os.getenv("TEST_MODE_ENV", "true")).lower() == "true"

def log_diag(step, status="INFO", msg=""):
    ts = datetime.now().strftime("%H:%M:%S")
    icon = "✅" if status == "OK" else ("❌" if status == "FAIL" else "⏳")
    print(f"[{ts}] {icon} [{step}] {msg}", flush=True)

# ─── 2. 增强抓取逻辑：多接口备份方案 ───────────────────────────────
def fetch_tweets_with_fallback(accounts, label):
    if not TWITTERAPI_IO_KEY or not accounts:
        return []

    all_tweets = []
    log_diag(f"{label}扫盘", "BUSY", f"准备扫描 {len(accounts)} 位大佬...")

    for account in accounts:
        account = account.strip()
        # 方案 A: 尝试 last_tweets
        url = f"https://api.twitterapi.io/twitter/user/last_tweets?userName={account}"
        try:
            r = requests.get(url, headers={"X-API-Key": TWITTERAPI_IO_KEY}, timeout=20)
            data = r.json() if r.status_code == 200 else {}
            tweets = data.get("tweets", [])
            
            # 💡 调试：如果抓到数据，打印出第一个数据包的键名，帮我们分析时间戳格式
            if tweets and account == accounts[0]:
                print(f"\n--- [DEBUG] 原始数据键名: {list(tweets[0].keys())} ---", flush=True)
                print(f"--- [DEBUG] 推文创建时间原文: {tweets[0].get('createdAt') or tweets[0].get('created_at')} ---", flush=True)

            # 方案 B: Fallback (如果 A 抓不到，尝试高级搜索)
            if not tweets:
                log_diag(f"回退搜索", "BUSY", f"@{account} A方案无结果，尝试 B 方案...")
                search_url = f"https://api.twitterapi.io/twitter/tweet/advanced_search?query=(from:{account}) -filter:replies&count=10"
                r_s = requests.get(search_url, headers={"X-API-Key": TWITTERAPI_IO_KEY}, timeout=20)
                if r_s.status_code == 200:
                    tweets = r_s.json().get("tweets", [])

            # 统一过滤：只过滤回复，不再强杀 24h（因为 API 默认给的就是最新的）
            valid = [t for t in tweets if not t.get("isReply", False)]
            all_tweets.extend(valid)
            
            if valid: print(f"   - @{account}: 成功抓取 {len(valid)} 条推文", flush=True)
            
        except Exception as e:
            log_diag("接口报错", "FAIL", f"@{account} 通讯中断: {str(e)}")
            
    log_diag(f"{label}汇总", "OK", f"共获得 {len(all_tweets)} 条深度动态")
    return all_tweets

# ─── 3. 持久化与文件保护 ─────────────────────────────────────────────
def ensure_and_save(tweets, date_str):
    """确保 data 文件夹存在并保存 combined.txt"""
    folder = f"data/{date_str}"
    os.makedirs(folder, exist_ok=True)
    # 创建初始化文件防止 Git 报错
    for f in ["character_memory.json", "account_stats.json"]:
        if not os.path.exists(f):
            with open(f, "w") as j: j.write("{}")
            
    path = f"{folder}/combined.txt"
    with open(path, "w", encoding="utf-8") as f:
        f.write(json.dumps(tweets, indent=2, ensure_ascii=False))
    log_diag("本地存档", "OK", f"数据已写入 {path}")

# ─── 4. 模拟其他核心函数逻辑 (保持 10.6/10.9 的核心处理) ────────────
# ... (此处包含 Perplexity, Tavily 和 Grok 的调用) ...

def main():
    print(f"\n{'='*20} V10.10 诊断系统启动 {'='*20}")
    print(f"DEBUG: API Key 前缀: {str(TWITTERAPI_IO_KEY)[:4]}***")
    print(f"DEBUG: 当前模式: {'测试(屏蔽主群)' if TEST_MODE else '生产(全量推送)'}")

    # 获取名单
    whales = open("whales.txt").read().splitlines() if os.path.exists("whales.txt") else ["elonmusk", "sama"]
    
    # 执行抓取
    raw_tweets = fetch_tweets_with_fallback(whales, "核心大佬")
    
    # 无论是否抓到，都要保存
    date_str = datetime.now().strftime("%Y-%m-%d")
    ensure_and_save(raw_tweets, date_str)
    
    # 执行后续情报链路 (即便推文为0，宏观情报也能生成报告)
    # run_rest_of_pipeline(raw_tweets)
    
    log_diag("系统", "OK", "任务链条运行完毕")
    print(f"{'='*20} 诊断结束 {'='*20}\n")

if __name__ == "__main__":
    main()

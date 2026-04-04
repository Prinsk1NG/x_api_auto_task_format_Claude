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
FEISHU_WEBHOOK_URL = os.getenv("FEISHU_WEBHOOK_URL")     # 个人调试
FEISHU_WEBHOOK_URL_1 = os.getenv("FEISHU_WEBHOOK_URL_1") # 主群
TEST_MODE = os.getenv("TEST_MODE_ENV", "true").lower() == "true"

def log_diag(step, status="INFO", msg=""):
    ts = datetime.now().strftime("%H:%M:%S")
    icon = "✅" if status == "OK" else ("❌" if status == "FAIL" else "⏳")
    print(f"[{ts}] {icon} [{step}] {msg}", flush=True)

# ─── 2. 强化抓取逻辑：解决 0 抓取问题 ───────────────────────────────
def fetch_tweets(accounts, label):
    if not TWITTERAPI_IO_KEY or not accounts:
        return []

    all_tweets = []
    log_diag(f"{label}扫盘", "BUSY", f"开始扫描 {len(accounts)} 人...")

    for account in accounts:
        url = f"https://api.twitterapi.io/twitter/user/last_tweets?userName={account.strip()}"
        try:
            r = requests.get(url, headers={"X-API-Key": TWITTERAPI_IO_KEY}, timeout=20)
            if r.status_code == 200:
                raw_data = r.json().get("tweets", [])
                
                # 💡 深度诊断：如果是第一个人且抓到了数据，打印出前 200 个字符看看结构
                if raw_data and account == accounts[0]:
                    print(f"--- [DEBUG] 原始数据样本预览 (来自 @{account}) ---")
                    print(json.dumps(raw_data[0], indent=2)[:500])
                    print("------------------------------------------")

                # 🚀 宽松策略：先不进行复杂的时间戳字符串比对，直接抓取 API 返回的所有推文
                # 因为该 API 默认返回的就是最近推文，我们在 Python 端仅做简单的非回复过滤
                valid = [t for t in raw_data if not t.get("isReply", False)]
                all_tweets.extend(valid)
                
                if valid: print(f"   - @{account}: 发现 {len(valid)} 条动态", flush=True)
            else:
                log_diag("TwitterAPI", "FAIL", f"@{account} 状态码: {r.status_code}")
        except Exception as e:
            log_diag("TwitterAPI", "FAIL", f"@{account} 错误: {str(e)}")
            
    log_diag(f"{label}结果", "OK", f"共抓取 {len(all_tweets)} 条推文")
    return all_tweets

# ─── 3. 补齐 Git 缺失文件防止报错 ─────────────────────────────────────
def ensure_files():
    """如果文件不存在，先创建一个空的，防止 Git 报错"""
    files = ["character_memory.json", "account_stats.json"]
    for f in files:
        if not os.path.exists(f):
            with open(f, "w") as j: j.write("{}")

def main():
    print(f"\n{'='*20} V10.9 深度透视系统启动 {'='*20}")
    ensure_files()
    
    # 获取名单
    whales = open("whales.txt").read().splitlines() if os.path.exists("whales.txt") else ["elonmusk", "sama"]
    
    # A. 抓取
    raw_tweets = fetch_tweets(whales, "核心大佬")
    
    # B. 持久化（无论是否抓到都生成文件夹）
    date_str = datetime.now().strftime("%Y-%m-%d")
    os.makedirs(f"data/{date_str}", exist_ok=True)
    with open(f"data/{date_str}/combined.txt", "w") as f:
        f.write(json.dumps(raw_tweets, indent=2))
    
    # C. 调用后续逻辑 (保持原本逻辑...)
    # 如果 raw_tweets 为空，Grok 依然可以根据 Perplexity 的宏观背景生成一份简报
    log_diag("任务", "OK", "主流程运行完毕")

if __name__ == "__main__":
    main()

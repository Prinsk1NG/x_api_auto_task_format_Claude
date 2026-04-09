import os
import json
import requests
from datetime import datetime, timezone, timedelta
from collections import defaultdict
from pathlib import Path

"""
hr_manager.py v2.0 — 适配 v15.0 架构
- 不再依赖回响查询产生的外部账号
- 基于 account_stats.json（干净数据）做淘汰/晋升
- 淘汰标准：连续 15 天 total_tweets=0 或 used_in_reports=0
- 晋升来源：从 daily_report 里被 LLM 引用但不在名单内的账号
"""

# ==========================================
# 1. 渠道配置
# ==========================================
FEISHU_MAIN_URL = os.getenv("FEISHU_WEBHOOK_URL_1")
FEISHU_TEST_URL = os.getenv("FEISHU_WEBHOOK_URL")
JIJYUN_URL = os.getenv("JIJYUN_WEBHOOK_URL")
TEST_MODE = os.getenv("TEST_MODE_ENV", "false").lower() == "true"

def normalize(name):
    return name.replace("@", "").strip().lower()

def push_to_channels(content):
    if not content.strip(): return
    webhook_url = FEISHU_TEST_URL if TEST_MODE else FEISHU_MAIN_URL
    if webhook_url:
        payload = {"msg_type": "post", "content": {"post": {"zh_cn": {
            "title": "⚖️ 硅谷情报局：半月度名单自动换血报告",
            "content": [[{"tag": "text", "text": content}]]
        }}}}
        requests.post(webhook_url, json=payload)
    if JIJYUN_URL:
        requests.post(JIJYUN_URL, json={"content": content})

# ==========================================
# 2. 核心换血算法
# ==========================================
def main():
    print("🔍 启动半月度名单自动洗牌程序 v2.0...")

    # 1. 读取当前名单
    whales = set()
    experts = set()

    if os.path.exists("whales.txt"):
        with open("whales.txt", "r") as f:
            whales = {normalize(line) for line in f if line.strip() and not line.startswith("#")}

    if os.path.exists("experts.txt"):
        with open("experts.txt", "r") as f:
            experts = {normalize(line) for line in f if line.strip() and not line.startswith("#")}

    current_all = whales | experts
    if not experts:
        print("❌ 未找到 experts.txt，跳过维护。")
        return

    # 2. 读取 account_stats.json（干净数据源）
    stats_file = Path("data/account_stats.json")
    if not stats_file.exists():
        print("❌ 未找到 account_stats.json，跳过维护。")
        return

    stats = json.loads(stats_file.read_text(encoding="utf-8"))

    # 3. 评选末位淘汰名单（仅淘汰 experts，不动 whales）
    today = datetime.now(timezone.utc)
    bottom_candidates = []

    for exp in experts:
        s = stats.get(exp, {})
        total_tweets = s.get("total_tweets", 0)
        used_in_reports = s.get("used_in_reports", 0)
        last_active = s.get("last_active", "")

        # 淘汰条件：15天内零推文，或有推文但从未被引用
        if total_tweets == 0:
            bottom_candidates.append((exp, 0, "零数据"))
        elif used_in_reports == 0 and total_tweets >= 5:
            # 高产但从未被引用 = 内容与 AI 叙事不相关
            bottom_candidates.append((exp, total_tweets, "高产无引用"))

    # 按严重程度排序：零数据优先淘汰
    bottom_candidates.sort(key=lambda x: (x[2] != "零数据", x[1]))
    # 每次最多淘汰 3 人
    to_drop = bottom_candidates[:3]

    # 4. 评选晋升名单：扫描近15天报告中被引用但不在名单内的账号
    external_mentions = defaultdict(int)
    data_dir = Path("data")
    cutoff = today - timedelta(days=15)

    for day_dir in data_dir.iterdir():
        if not day_dir.is_dir(): continue
        try:
            dir_date = datetime.strptime(day_dir.name, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            if dir_date < cutoff: continue
        except ValueError:
            continue

        report_file = day_dir / "daily_report.txt"
        if not report_file.exists(): continue

        report_text = report_file.read_text(encoding="utf-8")
        # 从 XML 中提取 account 属性
        import re
        for match in re.finditer(r'account=[\'"""](.*?)[\'"""]', report_text, re.IGNORECASE):
            acc = normalize(match.group(1))
            if acc and acc not in current_all:
                external_mentions[acc] += 1

    # 被引用 >= 2 次的外部账号才有资格晋升
    promotion_candidates = sorted(
        [(acc, cnt) for acc, cnt in external_mentions.items() if cnt >= 2],
        key=lambda x: x[1], reverse=True
    )
    to_promote = promotion_candidates[:len(to_drop)]

    # 5. 执行换血
    dropped_names = [x[0] for x in to_drop[:len(to_promote)]]
    promoted_names = [x[0] for x in to_promote]

    new_experts = (experts - set(dropped_names)) | set(promoted_names)

    if dropped_names or promoted_names:
        with open("experts.txt", "w", encoding="utf-8") as f:
            f.write("# 硅谷情报局动态专家名单 (15日自动更新)\n")
            for exp in sorted(new_experts):
                f.write(f"{exp}\n")

        report = f"🔄 15日周期名单自动洗牌已完成！\n\n"
        report += "📉 【末位淘汰】\n"
        for name, tweets, reason in to_drop[:len(to_promote)]:
            report += f"  ❌ @{name} ({reason}，推文数 {tweets}，已移除)\n"

        report += "\n📈 【新贵晋升】\n"
        for name, cnt in to_promote:
            report += f"  ✨ @{name} (近15天被报告引用 {cnt} 次，已收编)\n"

        report += f"\n🎯 当前监控底座总人数: {len(whales) + len(new_experts)} 人。"
    else:
        report = "🔄 15日周期核查完毕。本周期内现有专家表现稳定，无符合淘汰与晋升标准的账号，名单保持不变。"

    print(report)
    push_to_channels(report)

if __name__ == "__main__":
    main()

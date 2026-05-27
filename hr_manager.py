import os
import json
import math
import requests
from datetime import datetime, timezone, timedelta
from collections import defaultdict
from pathlib import Path

"""
hr_manager.py v3.0 — 适配 v16.0 架构（加权评分换血）
v3.0 变更:
- 引入"信号 ROI 评分"：综合引用密度 + 绝对贡献 + 衰减惩罚，连续值而非二元判定
- 末位淘汰扩大到 score < 5 的 experts（不再卡 total_tweets==0 二元条件）
- score 5-15 的"观察名单"在报告里单独列出，给运营手动决策的空间
- 晋升仍保留"被引用 ≥2 次"门槛
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
            "title": "⚖️ 硅谷情报局：半月度名单自动换血报告 v3",
            "content": [[{"tag": "text", "text": content}]]
        }}}}
        requests.post(webhook_url, json=payload)
    if JIJYUN_URL:
        requests.post(JIJYUN_URL, json={"content": content})

# ==========================================
# 2. v3 核心：信号 ROI 评分
# ==========================================
def compute_roi_score(stats_entry: dict, today: datetime) -> tuple:
    """
    score = 引用密度(0-100) + log(被引用次数)*20 - days_since_last_used 衰减
    返回 (score, 说明)
    """
    total = stats_entry.get("total_tweets", 0)
    used = stats_entry.get("used_in_reports", 0)
    last_active = stats_entry.get("last_active", "")

    # 引用密度（避免除 0）
    density = (used / max(1, total)) * 100 if total > 0 else 0
    # 绝对贡献
    abs_contrib = math.log1p(used) * 20

    # 衰减惩罚：≥14 天未活跃开始扣分，每多 1 天 -3
    decay = 0
    if last_active:
        try:
            la = datetime.strptime(last_active, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            gap = (today - la).days
            decay = max(0, gap - 14) * 3
        except ValueError:
            decay = 30

    score = round(density + abs_contrib - decay, 1)
    note = f"density={density:.0f} contrib={abs_contrib:.1f} decay={decay} | tweets={total} used={used}"
    return score, note


def main():
    print("🔍 启动半月度名单自动洗牌程序 v3.0（加权评分版）...")

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

    # 2. 读取 account_stats.json
    stats_file = Path("data/account_stats.json")
    if not stats_file.exists():
        print("❌ 未找到 account_stats.json，跳过维护。")
        return

    stats = json.loads(stats_file.read_text(encoding="utf-8"))
    today = datetime.now(timezone.utc)

    # 3. v3 核心：给每个 expert 计算 ROI 分数
    scored_experts = []
    for exp in experts:
        s = stats.get(exp, {})
        score, note = compute_roi_score(s, today)
        scored_experts.append((exp, score, note))

    # 按 score 升序，最低分最先淘汰
    scored_experts.sort(key=lambda x: x[1])

    # 末位淘汰：score < 5（基本说明既不被引用、也长期失活）
    to_drop = [(name, s, n) for name, s, n in scored_experts if s < 5][:5]   # 一次最多淘 5 人
    # 观察名单：5 <= score < 15（暂不动，但运营要注意）
    watchlist = [(name, s, n) for name, s, n in scored_experts if 5 <= s < 15][:8]

    # 4. 晋升名单：扫描近 15 天报告中被引用但不在名单内的账号
    external_mentions = defaultdict(int)
    data_dir = Path("data")
    cutoff = today - timedelta(days=15)

    import re
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
        for match in re.finditer(r'account=[\'"]([^\'"]+)[\'"]', report_text, re.IGNORECASE):
            acc = normalize(match.group(1))
            if acc and acc not in current_all:
                external_mentions[acc] += 1

    promotion_candidates = sorted(
        [(acc, cnt) for acc, cnt in external_mentions.items() if cnt >= 2],
        key=lambda x: x[1], reverse=True
    )
    # 一次最多晋升 min(淘汰数, 5)
    to_promote = promotion_candidates[:min(len(to_drop), 5)]

    # 5. 执行换血
    dropped_names = [x[0] for x in to_drop[:len(to_promote)]]
    promoted_names = [x[0] for x in to_promote]

    new_experts = (experts - set(dropped_names)) | set(promoted_names)

    if dropped_names or promoted_names:
        with open("experts.txt", "w", encoding="utf-8") as f:
            f.write("# 硅谷情报局动态专家名单 (15日自动更新 v3 加权评分)\n")
            for exp in sorted(new_experts):
                f.write(f"{exp}\n")

        report = f"🔄 15日周期名单自动洗牌已完成 (v3 加权评分)！\n\n"
        report += "📉 【末位淘汰 - score < 5】\n"
        for name, sc, note in to_drop[:len(to_promote)]:
            report += f"  ❌ @{name}  score={sc}  ({note})\n"

        report += "\n📈 【新贵晋升 - 近 15 天被报告引用 >=2 次】\n"
        for name, cnt in to_promote:
            report += f"  ✨ @{name}  ({cnt} 次引用，已收编)\n"
    else:
        report = "🔄 15日周期核查完毕（v3）。本期专家名单评分都达标，名单保持不变。\n"

    # v3 新增：观察名单
    if watchlist:
        report += f"\n👀 【观察名单 - 5 <= score < 15】（连续两期上榜需手动评估）\n"
        for name, sc, note in watchlist:
            report += f"  ⚠️ @{name}  score={sc}  ({note})\n"

    report += f"\n🎯 当前监控底座总人数: {len(whales) + len(new_experts)} 人。"
    print(report)
    push_to_channels(report)

if __name__ == "__main__":
    main()

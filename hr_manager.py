import os
import re
import json
import math
import requests
from datetime import datetime, timezone, timedelta
from collections import defaultdict
from pathlib import Path

"""
hr_manager.py v4.0 — 适配 v17.0 架构（拆解淘汰-晋升 + 45 天僵尸清理）

v4.0 变更（基于 v16 两个月 60 天回测发现的死锁）:
- 修复 v3 逻辑漏洞：`dropped_names = to_drop[:len(to_promote)]` 导致淘汰绑晋升
  → 60 天内 0 次执行，8 位 experts 该淘不淘
- 【拆解】to_drop 和 to_promote 完全独立：淘汰按 score < 5 无条件执行
- 【新规则】45 天僵尸清理：last_active 超过 45 天 → 无条件淘汰
  （给 palmerluckey / scobleizer 这种彻底不发推的账号一条清退通道）
- 单次最多减 5 人（防雪崩）
- 晋升门槛 >=2 → >=1（现实是每半月被引用 1 次就已不错）
- score 5-15 的"观察名单"保留（连续 2 期上榜需手动评估）
"""

# ==========================================
# 1. 渠道配置
# ==========================================
FEISHU_MAIN_URL = os.getenv("FEISHU_WEBHOOK_URL_1")
FEISHU_TEST_URL = os.getenv("FEISHU_WEBHOOK_URL")
JIJYUN_URL = os.getenv("JIJYUN_WEBHOOK_URL")
TEST_MODE = os.getenv("TEST_MODE_ENV", "false").lower() == "true"

# v4 参数
MAX_DROP_PER_RUN = 5           # 单次最多淘汰人数（雪崩保护）
ZOMBIE_DAYS = 45               # 超过 N 天未活跃 → 僵尸账号
SCORE_DROP_THRESHOLD = 5       # score < 该值即淘汰
SCORE_WATCH_UPPER = 15         # 5 <= score < 15 进入观察名单
PROMO_MIN_MENTIONS = 1         # v4：晋升门槛从 2 降到 1


def normalize(name):
    return name.replace("@", "").strip().lower()


def push_to_channels(content):
    if not content.strip(): return
    webhook_url = FEISHU_TEST_URL if TEST_MODE else FEISHU_MAIN_URL
    if webhook_url:
        payload = {"msg_type": "post", "content": {"post": {"zh_cn": {
            "title": "⚖️ 硅谷情报局：半月度名单自动换血报告 v4",
            "content": [[{"tag": "text", "text": content}]]
        }}}}
        try:
            requests.post(webhook_url, json=payload, timeout=15)
        except Exception as e:
            print(f"⚠️ 飞书推送失败: {e}")
    if JIJYUN_URL:
        try: requests.post(JIJYUN_URL, json={"content": content}, timeout=15)
        except: pass


# ==========================================
# 2. 核心：ROI 评分
# ==========================================
def compute_roi_score(stats_entry: dict, today: datetime) -> tuple:
    """
    score = 引用密度(0-100) + log(被引用次数)*20 - days_since_last_used 衰减
    返回 (score, 说明)
    """
    total = stats_entry.get("total_tweets", 0)
    used = stats_entry.get("used_in_reports", 0)
    last_active = stats_entry.get("last_active", "")

    density = (used / max(1, total)) * 100 if total > 0 else 0
    abs_contrib = math.log1p(used) * 20

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


def days_since_active(last_active: str, today: datetime) -> int:
    """返回距今天多少天没活跃。空/无效返回 999。"""
    if not last_active: return 999
    try:
        la = datetime.strptime(last_active, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        return (today - la).days
    except ValueError:
        return 999


# ==========================================
# 3. 主流程
# ==========================================
def main():
    print("🔍 启动半月度名单自动洗牌程序 v4.0（拆解 + 45 天僵尸）...")

    whales, experts = set(), set()
    if os.path.exists("whales.txt"):
        with open("whales.txt", "r") as f:
            whales = {normalize(l) for l in f if l.strip() and not l.startswith("#")}
    if os.path.exists("experts.txt"):
        with open("experts.txt", "r") as f:
            experts = {normalize(l) for l in f if l.strip() and not l.startswith("#")}

    current_all = whales | experts
    if not experts:
        print("❌ 未找到 experts.txt，跳过维护。")
        return

    stats_file = Path("data/account_stats.json")
    if not stats_file.exists():
        print("❌ 未找到 account_stats.json，跳过维护。")
        return

    stats = json.loads(stats_file.read_text(encoding="utf-8"))
    today = datetime.now(timezone.utc)

    # ─────────── ① 45 天僵尸清理（无条件，不占淘汰配额）──────────
    zombies = []
    for exp in experts:
        s = stats.get(exp, {})
        idle_days = days_since_active(s.get("last_active", ""), today)
        if idle_days >= ZOMBIE_DAYS:
            zombies.append((exp, idle_days, s.get("last_active", "?")))

    # ─────────── ② 低分淘汰（score < 5, 排除已被僵尸清理的）──────────
    zombie_set = {z[0] for z in zombies}
    scored_experts = []
    for exp in experts:
        if exp in zombie_set: continue   # 已被僵尸清理，不重复
        s = stats.get(exp, {})
        score, note = compute_roi_score(s, today)
        scored_experts.append((exp, score, note))
    scored_experts.sort(key=lambda x: x[1])

    to_drop_low = [(n, s, note) for n, s, note in scored_experts if s < SCORE_DROP_THRESHOLD][:MAX_DROP_PER_RUN]
    watchlist   = [(n, s, note) for n, s, note in scored_experts if SCORE_DROP_THRESHOLD <= s < SCORE_WATCH_UPPER][:8]

    # ─────────── ③ 晋升候选：近 15 天报告外部账号 ──────────
    external_mentions = defaultdict(int)
    data_dir = Path("data")
    cutoff = today - timedelta(days=15)
    for day_dir in data_dir.iterdir():
        if not day_dir.is_dir(): continue
        try:
            dt = datetime.strptime(day_dir.name, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            if dt < cutoff: continue
        except ValueError:
            continue
        rf = day_dir / "daily_report.txt"
        if not rf.exists(): continue
        for m in re.finditer(r'account=[\'"]([^\'"]+)[\'"]', rf.read_text(encoding="utf-8")):
            acc = normalize(m.group(1))
            if acc and acc not in current_all:
                external_mentions[acc] += 1

    to_promote = sorted(
        [(a, c) for a, c in external_mentions.items() if c >= PROMO_MIN_MENTIONS],
        key=lambda x: -x[1]
    )[:MAX_DROP_PER_RUN]  # 晋升上限同淘汰上限

    # ─────────── ④ 执行（v4 关键：淘汰、晋升、僵尸完全独立）──────────
    dropped_names   = [z[0] for z in zombies] + [x[0] for x in to_drop_low]
    promoted_names  = [x[0] for x in to_promote]
    new_experts     = (experts - set(dropped_names)) | set(promoted_names)

    if dropped_names or promoted_names:
        with open("experts.txt", "w", encoding="utf-8") as f:
            f.write("# 硅谷情报局动态专家名单 (v4 加权评分 + 45 天僵尸清理)\n")
            for e in sorted(new_experts):
                f.write(f"{e}\n")

    # ─────────── ⑤ 生成报告 ──────────
    report = f"🔄 15 日周期名单自动洗牌 v4.0（{today.strftime('%Y-%m-%d')}）\n\n"

    if zombies:
        report += f"🧟 【45 天僵尸自动清理】 共 {len(zombies)} 人\n"
        for n, idle, la in zombies:
            report += f"  ☠️ @{n}  (最后活跃 {la}, 已 {idle} 天未发推)\n"
        report += "\n"

    if to_drop_low:
        report += f"📉 【低分淘汰 score < {SCORE_DROP_THRESHOLD}】 共 {len(to_drop_low)} 人\n"
        for n, sc, note in to_drop_low:
            report += f"  ❌ @{n}  score={sc}  ({note})\n"
        report += "\n"

    if to_promote:
        report += f"📈 【新贵晋升 · 近 15 天引用 >= {PROMO_MIN_MENTIONS}】 共 {len(to_promote)} 人\n"
        for a, c in to_promote:
            report += f"  ✨ @{a}  ({c} 次引用，已收编)\n"
        report += "\n"

    if watchlist:
        report += f"👀 【观察名单 · {SCORE_DROP_THRESHOLD} <= score < {SCORE_WATCH_UPPER}】 共 {len(watchlist)} 人（连续两期上榜需手动评估）\n"
        for n, sc, note in watchlist:
            report += f"  ⚠️ @{n}  score={sc}  ({note})\n"
        report += "\n"

    if not (zombies or to_drop_low or to_promote):
        report += "✅ 本期无淘汰无晋升，名单保持不变。\n\n"

    report += f"🎯 当前监控底座总人数: {len(whales) + len(new_experts)} 人"
    report += f"  (whales={len(whales)}, experts={len(new_experts)})"
    if len(new_experts) != len(experts):
        delta = len(new_experts) - len(experts)
        report += f"  (Δ experts {delta:+d})"

    print(report)
    push_to_channels(report)


if __name__ == "__main__":
    main()

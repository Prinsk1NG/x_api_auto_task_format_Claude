# -*- coding: utf-8 -*-
"""
weekly_quality.py v1.0 — 周质量自检（v16 配套）
每周跑一次，统计过去 7 天报告的 3 个核心指标，超阈值飞书告警：
  ① 主题关键词重复率（Codex 等单一关键词出现 ≥ 4/7 天 → 警报）
  ② 账号集中度（前 5 大佬占 THEME 引用 > 40%）
  ③ 输入用率（每日抓取作者被引用率 < 30%）

用法：python weekly_quality.py
建议 cron：每周一早上 9 点跑一次
  0 1 * * 1 cd /your/path && python weekly_quality.py >> logs/weekly.log 2>&1
"""

import os
import re
import json
import requests
from pathlib import Path
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta

FEISHU_URL = os.getenv("FEISHU_WEBHOOK_URL_1") or os.getenv("FEISHU_WEBHOOK_URL", "")
DATA_DIR = Path("data")

# 关键词警戒清单（任一关键词出现 >= THRESHOLD 天数触发告警）
HOT_KEYWORDS = ["Codex", "Agent", "Agentic", "持久", "中国", "开源", "Token", "算力", "Anthropic"]
KW_THRESHOLD = 4   # 7 天内出现 4 天即偏高


def collect_days(n: int = 7):
    """返回最近 n 天可用的日期列表（倒序，最新在前）"""
    tz = timezone(timedelta(hours=8))
    base = datetime.now(tz).date()
    out = []
    for i in range(1, n + 1):
        d = (base - timedelta(days=i)).strftime("%Y-%m-%d")
        if (DATA_DIR / d / "daily_report.txt").exists():
            out.append(d)
    return out


def analyze(days):
    if not days:
        return None, "近 7 日无报告数据，无法生成质量周报"

    # 1. 标题关键词频率
    kw_days = defaultdict(set)
    title_counter = Counter()
    theme_author = Counter()
    pick_author = Counter()
    per_day_use_rate = []

    for d in days:
        rfp = DATA_DIR / d / "daily_report.txt"
        cfp = DATA_DIR / d / "combined.txt"
        txt = rfp.read_text(encoding="utf-8")

        for m in re.finditer(r'<TITLE>(.*?)</TITLE>', txt):
            title = m.group(1).strip()
            title_counter[title] += 1
            for kw in HOT_KEYWORDS:
                if kw.lower() in title.lower():
                    kw_days[kw].add(d)

        # 账号集中度
        themes_block = re.search(r'<THEMES>(.*?)</THEMES>', txt, re.DOTALL)
        if themes_block:
            for am in re.finditer(r'account=[\'"]([^\'"]+)[\'"]', themes_block.group(1)):
                theme_author[am.group(1).lower().replace("@", "")] += 1
        picks_block = re.search(r'<TOP_PICKS>(.*?)</TOP_PICKS>', txt, re.DOTALL)
        if picks_block:
            for am in re.finditer(r'account=[\'"]([^\'"]+)[\'"]', picks_block.group(1)):
                pick_author[am.group(1).lower().replace("@", "")] += 1

        # 输入用率
        if cfp.exists():
            all_authors = set()
            for line in cfp.read_text(encoding="utf-8").splitlines():
                try:
                    all_authors.add(json.loads(line).get("a", ""))
                except Exception:
                    pass
            cited_authors = set(m.group(1).lower().replace("@", "")
                                for m in re.finditer(r'account=[\'"]([^\'"]+)[\'"]', txt))
            rate = len(cited_authors & all_authors) / len(all_authors) * 100 if all_authors else 0
            per_day_use_rate.append((d, len(all_authors), len(cited_authors & all_authors), rate))

    # 计算指标
    total_theme_refs = sum(theme_author.values()) or 1
    top5_share = sum(c for _, c in theme_author.most_common(5)) / total_theme_refs * 100
    avg_use_rate = sum(r[3] for r in per_day_use_rate) / len(per_day_use_rate) if per_day_use_rate else 0

    warnings = []

    # ① 关键词重复
    for kw, ds in kw_days.items():
        if len(ds) >= KW_THRESHOLD:
            warnings.append(f"❗ 关键词 '{kw}' 在 {len(ds)}/{len(days)} 天标题中出现，叙事可能僵化")

    # ② 账号集中度
    if top5_share > 40:
        top5_str = ", ".join(f"@{a}({c})" for a, c in theme_author.most_common(5))
        warnings.append(f"❗ THEME 引用前 5 大佬占 {top5_share:.1f}% > 40%（{top5_str}）")

    # ③ 输入用率
    if avg_use_rate < 30:
        warnings.append(f"❗ 7 日平均输入用率 {avg_use_rate:.1f}% < 30%，抓取浪费严重")

    # 报告文本
    lines = [f"📊 周质量报告 · {days[-1]} ~ {days[0]} ({len(days)} 天)"]
    lines.append("")
    lines.append(f"【关键指标】")
    lines.append(f"  · THEME 前 5 大佬占比: {top5_share:.1f}% (阈值 ≤40%)")
    lines.append(f"  · 7 日平均输入用率: {avg_use_rate:.1f}% (阈值 ≥30%)")
    lines.append("")
    lines.append(f"【热门关键词出现频次】")
    for kw in HOT_KEYWORDS:
        n = len(kw_days.get(kw, []))
        mark = " ⚠️" if n >= KW_THRESHOLD else ""
        lines.append(f"  · {kw}: {n}/{len(days)} 天{mark}")
    lines.append("")
    lines.append(f"【THEME 引用 TOP 5 大佬】")
    for a, c in theme_author.most_common(5):
        lines.append(f"  · @{a}: {c} 次")
    lines.append("")
    if warnings:
        lines.append("🚨 警告:")
        for w in warnings:
            lines.append(f"  {w}")
    else:
        lines.append("✅ 本周所有指标在阈值内")

    return "\n".join(lines), warnings


def push_to_feishu(text):
    if not FEISHU_URL: return
    try:
        payload = {"msg_type": "post", "content": {"post": {"zh_cn": {
            "title": "📊 硅谷情报局：周质量自检报告",
            "content": [[{"tag": "text", "text": text}]]
        }}}}
        r = requests.post(FEISHU_URL, json=payload, timeout=20)
        if r.status_code == 200:
            print("✅ 已推送飞书")
    except Exception as e:
        print(f"⚠️ 飞书推送失败: {e}")


if __name__ == "__main__":
    days = collect_days(7)
    text, warns = analyze(days) if days else ("近 7 日无报告数据", [])
    print(text)
    push_to_feishu(text)

import json
import os
from pathlib import Path

def load_accounts(filename):
    if not os.path.exists(filename): return []
    with open(filename, 'r', encoding='utf-8') as f:
        return [line.strip() for line in f if line.strip()]

def save_accounts(filename, accounts):
    with open(filename, 'w', encoding='utf-8') as f:
        for acc in sorted(set(accounts), key=str.casefold):
            f.write(f"{acc}\n")

def main():
    stats_file = Path("data/account_stats.json")
    if not stats_file.exists():
        print("未找到 account_stats.json，暂无数据可复盘。")
        return

    with open(stats_file, 'r', encoding='utf-8') as f:
        stats = json.load(f)

    whales = set(load_accounts("whales.txt"))
    experts = set(load_accounts("experts.txt"))

    pruned = []
    promoted = []
    wild_additions = []

    # 将集合统一转小写进行匹配比对
    whales_lower = {a.lower(): a for a in whales}
    experts_lower = {a.lower(): a for a in experts}

    for acc_lower, data in stats.items():
        total = data.get("total_tweets", 0)
        hits = data.get("used_in_reports", 0)
        hit_rate = (hits / total * 100) if total > 0 else 0
        
        original_name = experts_lower.get(acc_lower) or whales_lower.get(acc_lower) or acc_lower

        # 1. 淘汰水军：两周发推大于20条，但一次都没被选中
        if acc_lower in experts_lower and total > 20 and hits == 0:
            experts.remove(original_name)
            pruned.append(original_name)

        # 2. 提拔大佬：被选中大于等于3次，且命中率高于15%
        if acc_lower in experts_lower and hits >= 3 and hit_rate > 15:
            if original_name in experts: experts.remove(original_name)
            whales.add(original_name)
            promoted.append(original_name)
            
        # 3. 收编野生黑马：不在名单内，但通过全网雷达抓取进来了，并且被大模型选用过！
        if acc_lower not in experts_lower and acc_lower not in whales_lower and hits >= 1:
            experts.add(original_name)
            wild_additions.append(original_name)

    # 覆写最新的名单
    save_accounts("whales.txt", list(whales))
    save_accounts("experts.txt", list(experts))

    # 清空统计文件，开启下一个两周周期
    stats_file.write_text("{}", encoding="utf-8")

    print("\n" + "="*50)
    print("👔 人事总监 (HR Manager) 两周考核报告")
    print("="*50)
    print(f"🗑️ 淘汰水军 (高噪音, 0产出) 共 {len(pruned)} 人: {pruned}")
    print(f"🚀 提拔至巨鲸池 (高命中率) 共 {len(promoted)} 人: {promoted}")
    print(f"🌱 新收编野生黑马 (全网雷达捕获) 共 {len(wild_additions)} 人: {wild_additions}")
    print(f"\n📊 目前在库总人数：巨鲸 {len(whales)} 人 | 专家 {len(experts)} 人")

if __name__ == "__main__":
    main()

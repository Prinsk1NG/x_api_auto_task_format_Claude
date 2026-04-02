# 🌃 昨晚硅谷在聊啥

> 全自动 AI 行业情报日报 — 每天早上 8:00，把硅谷 AI 圈的核心动态送到你的飞书和微信

[![Python](https://img.shields.io/badge/Python-3.9+-blue?logo=python&logoColor=white)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

---

## 📖 这个项目是干什么的？

这个脚本每天自动完成以下事情：

1. **抓取** — 监控约 120 个硅谷 AI 圈核心 Twitter 账号过去 24 小时的发言、互动和争论
2. **分析** — 用大模型（xAI Grok）从海量推文中提炼 3~5 个重大叙事
3. **推送** — 把结构化的中文日报自动发到你的飞书群 & 微信群

最终你会收到一份这样的报告：

```
📰 报告结构
├── ⚡ 今日看板 (The Pulse)        — 一句话总结当日最核心信号
├── 🧠 深度叙事追踪 (3~5 个主题)
│   ├── 叙事转向型：共识 + 分歧
│   └── 新叙事型：展望 + 机会 + 风险
├── 💰 资本与估值雷达              — 融资、并购、VC 动向
├── 📊 风险与中国视角              — 海外对中国 AI 的评价 + 地缘监管
└── 📣 今日精选推文 (Top 5)        — 最有信息密度的原声
```

---

## 🏗️ 系统架构

```
┌──────────────────────────── 数据采集层 ────────────────────────────┐
│                                                                    │
│  TwitterAPI.io ──→ 巨鲸池 (5人) + 专家池 (~115人) 的推文          │
│                 ──→ 巨鲸被提及的高赞互动 (Mentions)               │
│                 ──→ Top 10 热帖的精选评论 (Replies)               │
│                                                                    │
│  Perplexity ────→ 融资/并购/开源项目等硬核事实                    │
│  Tavily ────────→ 核心人物站外动态 + 全球 AI 热点                 │
│                                                                    │
└───────────────────────────── ↓ ↓ ↓ ─────────────────────────────────┘
                                │
┌──────────────────────────── 分析层 ─────────────────────────────────┐
│                                                                    │
│  本地多维打分 ──→ 按点赞/巨鲸加权/关键词/文本质量 排序过滤        │
│  xAI Grok ──────→ XML 结构化提示词 → 生成完整中文日报             │
│                                                                    │
└───────────────────────────── ↓ ↓ ↓ ─────────────────────────────────┘
                                │
┌──────────────────────────── 分发层 ─────────────────────────────────┐
│                                                                    │
│  飞书 ──→ 交互式卡片消息 (Webhook)                                │
│  微信 ──→ HTML 长图文 (Webhook)                                   │
│  封面 ──→ SiliconFlow AI 生图 → ImgBB 图床                       │
│  归档 ──→ 本地 data/ 目录按日期存储原始数据 + 报告                │
│                                                                    │
└────────────────────────────────────────────────────────────────────┘
```

---

## 🚀 快速开始（5 步跑起来）

### 第 1 步：克隆项目

```bash
git clone https://github.com/你的用户名/silicon-valley-daily.git
cd silicon-valley-daily
```

### 第 2 步：安装依赖

> 需要 Python 3.9 或更高版本。不确定的话先跑 `python3 --version` 看看。

```bash
pip install requests xai-sdk
```

### 第 3 步：申请 API Key

你需要准备以下 API Key。下面是每个 Key 的获取方式和用途：

| API Key | 用途 | 是否必须 | 去哪申请 |
|---------|------|----------|----------|
| `twitterapi_io_KEY` | 抓取 Twitter 推文（核心数据源） | ✅ 必须 | [twitterapi.io](https://twitterapi.io/) |
| `XAI_API_KEY` | 调用 xAI Grok 大模型生成报告 | ✅ 必须 | [x.ai](https://x.ai/) |
| `PPLX_API_KEY` | Perplexity 搜索宏观行业数据 | 推荐 | [perplexity.ai](https://docs.perplexity.ai/) |
| `TAVILY_API_KEY` | Tavily 搜索补充情报 | 推荐 | [tavily.com](https://tavily.com/) |
| `SF_API_KEY` | SiliconFlow 生成 AI 封面图 | 可选 | [siliconflow.cn](https://siliconflow.cn/) |
| `IMGBB_API_KEY` | ImgBB 图床（托管封面图） | 可选 | [api.imgbb.com](https://api.imgbb.com/) |

> 💡 **最低成本方案**：只需要 `twitterapi_io_KEY` + `XAI_API_KEY` 两个 Key 就能跑起来。Perplexity 和 Tavily 能让报告内容更丰富，但不配也不会报错。

### 第 4 步：配置环境变量

在项目根目录创建一个 `.env` 文件（或直接 `export`）：

```bash
# === 必须配置 ===
export twitterapi_io_KEY="你的TwitterAPI密钥"
export XAI_API_KEY="你的xAI密钥"

# === 推荐配置（让报告更丰富）===
export PPLX_API_KEY="你的Perplexity密钥"
export TAVILY_API_KEY="你的Tavily密钥"
# 如果有多个 Tavily Key 可以轮换（防限流）：
# export TAVILY_API_KEY_2="第二个Key"
# export TAVILY_API_KEY_3="第三个Key"

# === 推送渠道（至少配一个，否则报告没地方发）===
# 飞书机器人 Webhook（群设置 → 群机器人 → 添加自定义机器人 → 复制地址）
export FEISHU_WEBHOOK_URL="https://open.feishu.cn/open-apis/bot/v2/hook/xxx"
# 如需多群推送：
# export FEISHU_WEBHOOK_URL_1="第二个飞书群地址"

# 微信推送 Webhook（可选）
# export JIJYUN_WEBHOOK_URL="你的微信推送地址"

# === 可选（封面图）===
# export SF_API_KEY="你的SiliconFlow密钥"
# export IMGBB_API_KEY="你的ImgBB密钥"
```

### 第 5 步：运行！

```bash
# 先用测试模式试跑（只抓少量账号，省 API 额度）
TEST_MODE_ENV=true python x_api_auto_task_xai_xml.py

# 确认没问题后，全量运行
python x_api_auto_task_xai_xml.py
```

看到 `🎉 V10.4 运行完毕！` 就说明成功了。去你的飞书/微信群看看报告吧。

---

## ⏰ 设置每天自动运行

### 方案 A：用 cron（Linux / Mac 服务器）

```bash
# 打开 crontab 编辑器
crontab -e

# 添加这一行：每天早上 7:55 (UTC+8) 运行，留 5 分钟给脚本处理
55 23 * * * cd /你的项目路径 && source .env && python x_api_auto_task_xai_xml.py >> logs/daily.log 2>&1
```

> ⚠️ 服务器时区如果是 UTC，7:55 AM 北京时间 = 23:55 UTC（前一天）

### 方案 B：用 GitHub Actions（免费，推荐）

在项目中创建 `.github/workflows/daily.yml`：

```yaml
name: 昨晚硅谷在聊啥 - 每日自动推送

on:
  schedule:
    - cron: '55 23 * * *'  # UTC 23:55 = 北京时间 07:55
  workflow_dispatch:        # 允许手动触发

jobs:
  run:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: pip install requests xai-sdk

      - name: Run daily report
        env:
          twitterapi_io_KEY: ${{ secrets.TWITTERAPI_IO_KEY }}
          XAI_API_KEY: ${{ secrets.XAI_API_KEY }}
          PPLX_API_KEY: ${{ secrets.PPLX_API_KEY }}
          TAVILY_API_KEY: ${{ secrets.TAVILY_API_KEY }}
          FEISHU_WEBHOOK_URL: ${{ secrets.FEISHU_WEBHOOK_URL }}
        run: python x_api_auto_task_xai_xml.py
```

然后去 GitHub 仓库的 **Settings → Secrets and variables → Actions** 里把你的 Key 都加进去。

---

## 🎛️ 自定义你的监控列表

打开 `x_api_auto_task_xai_xml.py`，找到开头的两个列表：

```python
# "巨鲸池" — 权重最高的 5 人，他们的每条发言都会被重点关注
WHALE_ACCOUNTS = [
    "elonmusk", "sama", "gregbrockman", "pmarca", "lexfridman"
]

# "专家池" — 约 115 人，涵盖 AI 研究、开源、VC、媒体、中文圈
EXPERT_ACCOUNTS = [
    "karpathy", "demishassabis", "darioamodei", ...
]
```

**想加人？** 直接把 Twitter 用户名（@ 后面的部分）加到对应列表里就行。

**想减人？** 删掉对应用户名即可。

**想调整权重？** 搜索 `score` 相关代码段，修改加分/减分逻辑：

```python
if is_whale: score += 500        # 巨鲸加分
if any(k in clean_text...):      # AI 关键词加分
    score += 300
if len(clean_text) < 30:         # 太短的扣分
    score -= 1000
if is_reply:                     # 回复帖扣分
    score -= 800
```

---

## 📁 项目文件说明

```
silicon-valley-daily/
├── x_api_auto_task_xai_xml.py   # 主脚本（唯一需要运行的文件）
├── .env                          # 你的 API Key（不要提交到 Git！）
├── .gitignore                    # 建议添加，排除 .env 和 data/
├── README.md                     # 就是你正在读的这个文件
└── data/                         # 自动生成，按日期存储历史数据
    ├── 2025-07-01/
    │   ├── combined.txt          # 当日抓取的原始推文
    │   └── daily_report.txt      # 当日生成的报告全文
    ├── 2025-07-02/
    │   └── ...
    └── account_stats.json        # 账号质量追踪数据库
```

> ⚠️ **安全提醒**：务必在 `.gitignore` 中加入 `.env`，防止 API Key 泄露。

```gitignore
# .gitignore
.env
data/
__pycache__/
*.pyc
logs/
```

---

## 💰 成本估算

| 服务 | 免费额度 | 日均消耗 | 月成本预估 |
|------|----------|----------|------------|
| TwitterAPI.io | 按计划定价 | ~20-30 次搜索请求 | 视套餐而定 |
| xAI Grok | 按 token 计费 | 1 次大模型调用 (~100K tokens) | ~$1-3/月 |
| Perplexity | 有免费额度 | 1 次调用 | 免费额度通常够用 |
| Tavily | 1000 次/月免费 | 4-5 次调用 | 免费额度通常够用 |
| SiliconFlow | 有免费额度 | 1 张图 | 免费额度通常够用 |
| GitHub Actions | 2000 分钟/月免费 | ~3-5 分钟 | 免费 |

> 💡 **最精简方案**（TwitterAPI.io + xAI）月成本可控制在 **$5 以内**。

---

## ❓ 常见问题

<details>
<summary><b>Q: 运行后没有收到飞书/微信消息？</b></summary>

检查清单：
1. 确认环境变量 `FEISHU_WEBHOOK_URL` 已正确设置
2. 确认飞书机器人 Webhook 地址没有过期（飞书群设置 → 群机器人 查看）
3. 查看终端输出中是否有 `[Push/Feishu] OK` 字样
4. 如果看到 `[Push/Feishu] ERROR`，检查网络连接和 Webhook 地址
</details>

<details>
<summary><b>Q: 报错 "未配置 twitterapi_io_KEY"？</b></summary>

环境变量没有生效。确认你已经 `source .env` 或用 `export` 设置了变量。可以用以下命令验证：

```bash
echo $twitterapi_io_KEY
```

如果输出为空，说明变量没设成功。
</details>

<details>
<summary><b>Q: 如何只测试不消耗太多 API 额度？</b></summary>

使用测试模式，只会抓取少量账号：

```bash
TEST_MODE_ENV=true python x_api_auto_task_xai_xml.py
```
</details>

<details>
<summary><b>Q: 想换成其他大模型（比如 GPT-4 / Claude）？</b></summary>

找到 `llm_call_xai()` 函数，替换为你目标模型的 API 调用即可。提示词模板在 `_build_xml_prompt()` 函数中，XML 结构可以复用，基本不用改。
</details>

<details>
<summary><b>Q: 可以推送到 Slack / Telegram / 邮件吗？</b></summary>

可以。参照 `render_feishu_card()` 和 `push_to_wechat()` 的模式，新增一个推送函数，在 `main()` 最后调用即可。
</details>

---

## 🤝 贡献

欢迎 PR！以下是一些可以改进的方向：

- [ ] 支持更多推送渠道（Slack / Telegram / Email）
- [ ] 添加 Web Dashboard 查看历史报告
- [ ] 支持自定义报告模板
- [ ] 账号质量自动优化（根据 `account_stats.json` 自动淘汰低质量信源）
- [ ] 多语言报告输出

---

## 📜 License

MIT — 随便用，记得给个 ⭐ 就好。

# 🌃 昨晚硅谷在聊啥

> 全自动 AI 行业情报日报 — 每天早上 8:00，把硅谷 AI 圈的核心动态送到你的飞书和微信

[![Python](https://img.shields.io/badge/Python-3.9+-blue?logo=python&logoColor=white)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

---

## 📖 这个项目是干什么的？

这个脚本每天自动完成以下事情：

1. **抓取** — 监控约 55 个硅谷 AI 圈核心 Twitter 账号过去 24 小时的原创推文（带翻页）
2. **分析** — 用大模型（xAI Grok）从推文中提炼 4~6 个重大叙事
3. **推送** — 把结构化的中文日报自动发到你的飞书群 & 微信群

最终你会收到一份这样的报告：

```
📰 报告结构
├── ⚡ 今日看板 (The Pulse)        — 一句话总结当日最核心信号
├── 🧠 深度叙事追踪 (4~6 个主题)
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
│  TwitterAPI.io ──→ T1 核心 (~13人) 逐人翻页抓取                   │
│                 ──→ T2 专家 (~42人) 批量搜索                       │
│                 ──→ Top 5 热帖的精选评论 (Replies)                 │
│                                                                    │
│  Perplexity ────→ 融资/并购/开源项目等硬核事实                    │
│  Tavily ────────→ 全球 AI 热点                                    │
│                                                                    │
└───────────────────────────── ↓ ↓ ↓ ─────────────────────────────────┘
                                │
┌──────────────────────────── 分析层 ─────────────────────────────────┐
│                                                                    │
│  对数打分引擎 ──→ log(互动量) + 身份加权 + AI关键词               │
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

| API Key | 用途 | 是否必须 | 去哪申请 |
|---------|------|----------|----------|
| `twitterapi_io_KEY` | 抓取 Twitter 推文（核心数据源） | ✅ 必须 | [twitterapi.io](https://twitterapi.io/) |
| `XAI_API_KEY` | 调用 xAI Grok 大模型生成报告 | ✅ 必须 | [x.ai](https://x.ai/) |
| `PPLX_API_KEY` | Perplexity 搜索宏观行业数据 | 推荐 | [perplexity.ai](https://docs.perplexity.ai/) |
| `TAVILY_API_KEY` | Tavily 搜索补充情报 | 推荐 | [tavily.com](https://tavily.com/) |
| `SF_API_KEY` | SiliconFlow 生成 AI 封面图 | 可选 | [siliconflow.cn](https://siliconflow.cn/) |
| `IMGBB_API_KEY` | ImgBB 图床（托管封面图） | 可选 | [api.imgbb.com](https://api.imgbb.com/) |

> 💡 **最低成本方案**：只需要 `twitterapi_io_KEY` + `XAI_API_KEY` 两个 Key 就能跑起来。

### 第 4 步：配置环境变量

在项目根目录创建一个 `.env` 文件（或直接 `export`）：

```bash
# === 必须配置 ===
export twitterapi_io_KEY="你的TwitterAPI密钥"
export XAI_API_KEY="你的xAI密钥"

# === 推荐配置（让报告更丰富）===
export PPLX_API_KEY="你的Perplexity密钥"
export TAVILY_API_KEY="你的Tavily密钥"

# === 推送渠道（至少配一个，否则报告没地方发）===
export FEISHU_WEBHOOK_URL="https://open.feishu.cn/open-apis/bot/v2/hook/xxx"

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

看到 `🎉 V15.0 全链路执行完毕！` 就说明成功了。

---

## ⏰ 设置每天自动运行

### 方案 A：用 cron（Linux / Mac 服务器）

```bash
crontab -e
# 每天早上 7:55 (UTC+8) 运行
55 23 * * * cd /你的项目路径 && source .env && python x_api_auto_task_xai_xml.py >> logs/daily.log 2>&1
```

### 方案 B：用 GitHub Actions（免费，推荐）

在项目中创建 `.github/workflows/daily.yml`：

```yaml
name: 昨晚硅谷在聊啥 - 每日自动推送

on:
  schedule:
    - cron: '55 23 * * *'  # UTC 23:55 = 北京时间 07:55
  workflow_dispatch:

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

---

## 🎛️ 自定义你的监控列表

项目使用两个 txt 文件管理监控名单：

- `whales.txt` — T1 核心信号源（~13人），CEO/创始人级 + 公司官号。每人单独搜索并翻页。
- `experts.txt` — T2 专家池（~42人），研究者、VC、媒体等。批量搜索。

想加人？直接把 Twitter 用户名加到对应文件里。想减人？删掉即可。

**半月度自动换血**：`hr_manager.py` 每 15 天自动扫描 `account_stats.json`，淘汰零产出账号、晋升被报告多次引用的外部账号。

---

## 📁 项目文件说明

```
silicon-valley-daily/
├── x_api_auto_task_xai_xml.py   # 主脚本 v15.0
├── hr_manager.py                 # 半月度名单换血脚本
├── whales.txt                    # T1 核心名单 (~13人)
├── experts.txt                   # T2 专家名单 (~42人)
├── .env                          # 你的 API Key（不要提交到 Git！）
├── README.md                     # 就是你正在读的这个文件
└── data/                         # 自动生成
    ├── 2026-04-10/
    │   ├── combined.txt          # 当日抓取的原始推文
    │   └── daily_report.txt      # 当日生成的报告全文
    ├── account_stats.json        # 账号质量追踪（仅名单内账号）
    └── character_memory.json     # 大佬历史观点记忆库
```

> ⚠️ **安全提醒**：务必在 `.gitignore` 中加入 `.env`，防止 API Key 泄露。

---

## 💰 成本估算

| 服务 | 日均调用 | 月成本预估 |
|------|----------|------------|
| TwitterAPI.io | ~10-15 次搜索 | 视套餐而定 |
| xAI Grok | 1 次 (~100K tokens) | ~$1-3/月 |
| Perplexity | 1 次 | 免费额度够用 |
| Tavily | 1 次 | 免费额度够用 |
| GitHub Actions | ~3-5 分钟 | 免费 |

> 💡 v15.0 相比 v14.1 **API 调用量减少约 50%**（砍掉回响查询 + 回复抓取从 15 缩到 5）。

---

## ❓ 常见问题

<details>
<summary><b>Q: 运行后没有收到飞书/微信消息？</b></summary>

检查清单：
1. 确认环境变量 `FEISHU_WEBHOOK_URL` 已正确设置
2. 确认飞书机器人 Webhook 地址没有过期
3. 查看终端输出中是否有 `[飞书 Webhook 报错]` 字样
</details>

<details>
<summary><b>Q: 某个大佬的推文一直抓不到？</b></summary>

先确认 handle 是否正确（去 X 上搜一下），再确认该账号近期是否有发推。v15.0 会在日志中打印每批抓到的推文数，据此排查。
</details>

<details>
<summary><b>Q: 想换成其他大模型？</b></summary>

找到 `llm_call_xai()` 函数，替换为你目标模型的 API 调用即可。提示词模板在 `_build_xml_prompt()` 中，XML 结构可以复用。
</details>

---

## 📜 License

MIT — 随便用，记得给个 ⭐ 就好。

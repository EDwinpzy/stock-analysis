# data/ — 运行时数据文件目录

运行中的读写路径由 `scripts/runtime_paths.py` 统一解析，默认在
`~/.codex/daily-briefing-pro/data/`，也可用 `DAILY_BRIEFING_DATA_DIR` 指定。
首次运行按“已有持久数据优先”的规则，从旧 Skill 数据目录和当前安装包补齐缺失文件；
插件升级后，采集快照、历史面板、Cookie 和缓存继续留在同一持久目录。本文中的 `data/`
文件名均指这个运行数据目录中的相对路径。

## 采集脚本写出的当日快照

每次 `scripts/run_all.py` 会覆盖这些文件。每个文件都带 `date`（目标日）、
`data_date`（实际数据日）、`status`（ok / empty / error）和 `note`（原因），
`build_briefing.py` 只按这些字段决定是否渲染条目。

| 文件 | 说明 | 产出脚本 |
|------|------|---------|
| `panic_today.json` | 市场温度 S、Δ1、Δ2、周期标签与 11 个因子 | `panic_greed_index_enhanced.py` |
| `sentiment_history.json` | 市场温度历史序列（近 14 日用于折线图） | `panic_greed_index_enhanced.py` |
| `news_today.json` | 财经科技新闻 | `fetch_news.py` |
| `lhb_today.json` | 龙虎榜（净买卖、机构、游资席位） | `fetch_longhubang.py` |
| `yanbao_latest.json` | 机构研报（目标日前 3 天窗口） | `fetch_yanbao.py` |
| `sentiment_survey_today.json` | 博主多空统计（淘股吧 + 雪球，note 中写明覆盖人数） | `fetch_sentiment_survey.py` |
| `xueqiu_today.json` | 雪球博主当日帖子（浏览器内请求上下文采集；失败时 note 说明原因） | `fetch_xueqiu.py` / `fetch_sentiment_survey.py` |
| `tgb_today.json` | 淘股吧博主主帖/跟帖 | `tgb_crawl.py` |
| `douyin_today.json` | 抖音博主当日视频与转录 | `fetch_douyin.py` |
| `events_today.json` | 未来 14 日财经日历事件 | `fetch_future_events.py` |
| `lianban_today.json` | 连板网公开概况/当日主线/资金流/次日观察（补充用，非替代） | `fetch_lianban.py` |
| `rotation_today.json` | 板块轮动：行业轮动模型 v2.0.0 的横截面前 15 排行与变动 | `fetch_rotation.py` |
| `rotation_history.json` | 板块轮动历史快照（用于算新进/跌出，保留最近 60 期） | `fetch_rotation.py` |
| `quote_today.html` | 每日金句横幅片段 | `pick_quote.py --html` |
| `used_quotes.json` | 金句去重记录 | `pick_quote.py` |

自选股新闻抓取器 `fetch_selfstock_news.py` 保留给专项新闻筛选使用，不再由 `run_all.py` 执行，也不再写入完整简报。

## 长期配置与静态数据

| 文件 | 说明 |
|------|------|
| `tgb_cookies.json` | 淘股吧登录 Cookie（也可放 `~/.codex/tgb_cookies.json`） |
| `douyin_cookies.json` / `douyin_state.json` | 抖音登录态 |
| `_stock_names.csv` | 代码→名称映射 |
| `investment_quotes.json` | 每日金句库 |
| `xueqiu_hot_users.json` | 雪球头部博主名单 |
| `ai_summary_override.json` | 人工校正过的摘要覆盖项 |

## 淘股吧AI摘要缓存

`tgb_ai_summaries.json` 只接受 `schema_version: 1` 的格式，按目标日期、来源平台、
博主名及原文 SHA-256 保存摘要。原文变更、目标日变化或来源不同都会重新请求AI；旧版
没有日期和原文校验的缓存会被忽略。`无明确观点` 是有效摘要，可以按原样复用。缓存最多
保留最近 60 个目标日。

## 市场温度口径（A股超短情绪温度模型 3.2）

`sentiment_history.json` 与顶部卡片同源，都由模型 3.2 计算，**不是** CNN 式恐贪指数，
也不是旧的 11 参数线性公式：

```
牛熊分组(上证 vs MA250) → 同景历史分位
→ F(34%) L(24%) R(18%) A(15%) B(6%) V(3%)
→ Q = Σw·f → 接缝 J → 非线性修正
→ S = clip(18 + 0.87Q + C_hot + C_J − P_breadth − P_down − P_bomb − P_cool − P_inertia, 0, 100)
→ Δ1 / Δ2 → 六阶段（修复/升温/高潮/降温/退潮/冰点）
```

| 文件 | 说明 |
|---|---|
| `sentiment_panel_v32.csv` | 模型输入面板，逐日增量维护，当前 400 行（2025-01-21 起） |
| `sentiment_history.json` | 近 14 个交易日的 S 与阶段标签，供折线图 |
| `panic_today.json` | 当日输出：S、Δ1、Δ2、六阶段、牛熊环境、F/L/R/A/B/V/Q/J/M 与各修正项 |

关键口径：

- 同景分位只用 **t 之前** 的样本，最多 250 个同景交易日；同景样本不足 60 个时
  按样本量比例与近 250 个全历史样本混合（模型内置规则，未改动）。
- 百分比字段用小数值参与（55% → 0.55）；`yday_*_ret` 用百分点（+4.53 填 4.53）。
- 晋级率由板位数按定义推算，分母 <3 家时沿用前值。
- 开盘啦对当日数据的聚合通常在收盘后较晚才发布；未发布时脚本按交易日向前
  回退，并在 `note` 中标注“使用 X 数据（已回退）”。

## 连板网补充数据（lianban_today.json）

`fetch_lianban.py` 采集 lianban.net **公开无需登录**的数据，只做补充展示：

| 字段 | 内容 | 展示位置 |
|---|---|---|
| `overview` | 涨停/跌停（含昨日）、连板家数、最高板、封板率、炸板率、涨跌家数、63日新高新低、两市成交、融资余额 | 顶部温度卡「盘面补充（连板网）」 |
| `main_sectors` / `top_leader` | 当日主线板块 + 涨停家数 + 板块龙头 + 驱动逻辑；总龙头 | 策略卡「做多」 |
| `watch_next` | 次日观察名单及理由 | 策略卡「观察等待」 |
| `fund_flow` | 板块/概念/个股主力净额 | 原始数据备用 |
| `ai_review` | 连板网自己的 AI 复盘正文 | 原始数据备用 |

**口径纪律（用户明确要求）**：市场温度只有一个来源，即用户自己的「A股超短情绪
温度模型 3.2」。连板网自带的“情绪温度/情绪周期”（如 `温度 5°`）**不参与计算、
也不在简报中展示**——`overview` 里的 `phase` / `temperature` 字段仅留在原始
JSON 中备查，渲染层已屏蔽，避免一个页面出现两个“温度”。页面日期与目标日不一致
时整块停用，不会混入其它交易日的盘面。

## 板块轮动数据（rotation_today.json）

来自用户的**行业轮动模型 v2.0.0**（目录由 `ROTATION_MODEL_DIR` 指定，默认在
`D:\Codex\2026-09-15\referenced-chatgpt-conversation-this-is-an\outputs\sw_rotation_model`）：

| 字段 | 内容 |
|---|---|
| `asof` | 模型实际打分日（模型落在最近交易日，可能晚于目标日时以它为准） |
| `top_k` / `primary_horizon` | 前 K（同花顺池默认 15）与主周期（默认 T+5） |
| `entries` | 前 K 排行：`rank_t5`、`name`、`score_t5`、`rank_t3`、`aligned`（T+3 与 T+5 共振）、`change` |
| `new_entries` / `dropped` | 与 `rotation_history.json` 上一期快照对比得出；首次运行留空 |
| `train_last` / `train_rows` | 模型的训练截止日与样本数（来自 `predict_manifest`） |

调用方式：`python scripts/fetch_rotation.py [--date YYYY-MM-DD] [--refresh]`。
脚本只调 `run.py predict` 并读 `outputs/`，**不改模型代码与参数，也不会覆盖模型目录
里的历史产物**。模型目录缺失时该板块如实显示“数据获取失败”。

口径提醒（与模型 README 一致，已写进简报）：模型只提供**排序**，分数不是上涨
概率；T+1 换手成本过高不可用，有效周期在 T+3 / T+5。

## 淘股吧 Cookie 获取方法

1. Chrome 登录 https://www.tgb.cn
2. F12 → Application → Cookies → tgb.cn
3. 导出所有 Cookie 为 JSON 数组
4. 保存为 `data/tgb_cookies.json`（或 `~/.codex/tgb_cookies.json`）

格式示例：
```json
[
  {"name": "PHPSESSID", "value": "xxx", "domain": ".tgb.cn", "path": "/"},
  {"name": "token", "value": "xxx", "domain": ".tgb.cn", "path": "/"}
]
```

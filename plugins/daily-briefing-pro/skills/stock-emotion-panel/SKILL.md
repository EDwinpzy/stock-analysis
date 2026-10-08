---
name: stock-emotion-panel
description: '用于生成或回填 A 股超短情绪温度模型 v3.2 的日频面板行：涨停/跌停/炸板池、连板梯队与空间高度、晋级率、昨涨停今表现、上证收盘与 MA250、成交额、涨跌家数。数据来自同花顺官方金融数据服务（hithink-finance CLI），可输出 JSON/CSV 或直接写入 panel_history.csv。触发词：情绪温度、面板、panel_history、涨停池、连板、炸板、晋级率、连板梯队。需要 K 线看图转 stock-market-board，个股深度分析转 stock-analysis。'
metadata:
  version: 1.0.0
  author: Codex
  dependencies:
    external_tools:
    - node
    - python
    python: '>=3.10'
    runtime:
    - hithink-finance CLI（同花顺官方数据服务）
  data_sources:
  - 同花顺官方 hithink-finance（涨停/跌停/炸板池、指数历史、全市场快照）
---

# 情绪温度面板取数（同花顺官方源）

把同花顺官方 A 股金融数据接成情绪温度模型 v3.2 的日频输入。原来这条链路是「开盘啦爬虫 + AkShare 东财池 + lianban.net 无头浏览器」三源拼装，本 Skill 用一套带鉴权的官方接口覆盖其中可替代的部分。

模型本体在 `D:\MyProjects\股票分析`（`emotion/` 包 + `tools/run_model.py`），本 Skill 只负责产出入参，不改模型口径。

## 前置条件

| 条件 | 操作 |
| --- | --- |
| 首次使用 | `npm install -g @hithink-tech/hithink-finance-cli`，再 `hithink-finance auth login`（API Key 只进系统凭据库，禁止写入仓库或日志） |
| 想确认命令或参数是否变化 | `hithink-finance capabilities --format json`、`hithink-finance schema <id> --format json` |
| 想核对字段口径与已验证数字 | 读 `references/panel-fields.md` |
| 取不到数据 | 先跑 `hithink-finance doctor --format json` 与 `hithink-finance auth status --format json` |

## 主流程

```bash
# 当日：收盘后跑，19 个字段齐全
python {skill_dir}/scripts/fetch_panel.py

# 历史交易日回填：18 个字段齐全，涨跌家数留空
python {skill_dir}/scripts/fetch_panel.py --date 2026-09-14 --format csv

# 直接写进面板：按日期去重后按日期重排，先加 --preview 更稳
python {skill_dir}/scripts/fetch_panel.py --date 2026-09-14 --append "D:\MyProjects\股票分析\data\panel_history.csv" --preview
```

脚本输出的列序与 `data/panel_history.csv`、`scripts/market_temperature_v32.py` 的 `PANEL_COLUMNS` 完全一致，写盘前会校验表头，不一致就报错而不是写坏文件。

## 快速决策

| 需求 | 做法 |
| --- | --- |
| 补一个交易日 | `--date YYYY-MM-DD`，加 `--append` 落盘 |
| 只要连板结构，不想等 | `--lite`：约 5 秒，跳过全市场快照与逐股历史 |
| 要封单额、涨停原因、炸板次数等池内细节 | 直接用 `hithink-finance special limit-up-pool` / `limit-break-pool` 原生命令 |
| 要看当天炸板/涨停梯队全貌 | `hithink-finance special limit-up-ladder --format json` |
| 要跑模型出温度 | 到 `D:\MyProjects\股票分析` 执行 `python tools/run_model.py` |
| 看图 / 出报告 | 转 `stock-market-board`（行情看板）或 `stock-analysis`（个股深度） |

## 字段来源速查

| 面板字段 | 来源 |
| --- | --- |
| `sh_close`、`turnover` | `index history --thscode 000001.SH`（成交额是**沪市口径**，不是两市合计） |
| `sh_ma250` | 同上前复 250 根日线的收盘均值 |
| `limit_up`、`first_board`、`consecutive`、`space`、`next_space`、`board2/3/4p` | `special limit-up-pool` 的 `continue_day_cnt` 分桶 |
| `limit_down` | `special limit-down-pool` |
| `bomb_rate` | `special limit-break-pool` / (`limit_up` + 炸板数) |
| `yday_limitup_ret`、`yday_lianban_ret` | 上一交易日涨停池成分的今日涨跌幅均值 |
| `p12`、`p23`、`p3p` | 今日二/三/四板家数 ÷ 昨日对应梯队家数 |
| `tradable_count`、`advance_count` | 实时全市场快照（仅最近交易日可用） |

完整对照、口径差异与验证数字见 `references/panel-fields.md`。

## 已知边界

- 涨停/跌停/炸板/连板/晋级率/昨涨停表现支持任意历史交易日回填；`tradable_count`、`advance_count` 只有实时口径，历史行留空，需要时用 `market-dumps` 全市场日线或本地库补齐。
- 涨停/跌停/炸板池实测不含 ST、新股与北交所（2026-09-14 涨停池 55 只中 `is_st`、`is_new`、北交所标记全为 0），字段里也带 `is_st` / `is_new` 标记，需要严格过滤时可自行判断。
- 同花顺成交额按万元取整，与逐笔加总存在百万分之几的差异，不影响模型分位。
- 同花顺公开能力不含分钟 K、tick、海外行情、宏观数据、新闻公告原文与研报原文；这些仍走原技能链路。
- 本 Skill 只产数据，不给投资建议、不做买卖判断。

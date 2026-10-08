# 面板字段口径与对账

基准口径来自两处，二者一致：

- `D:\MyProjects\股票分析\README.md` 第 2.1 节字段表
- `daily-briefing-pro/scripts/market_temperature_v32.py` 的实际计算

## 逐字段来源

| 字段 | 口径 | 采集方式 | 历史可回填 |
| --- | --- | --- | --- |
| `date` | YYYY-MM-DD | 交易日历 | 是 |
| `sh_close` | 上证指数收盘 | `index history 000001.SH` 的 `close_price` | 是 |
| `sh_ma250` | 上证收盘 MA250 | 同上前 250 根日线均值 | 是 |
| `tradable_count` | 正常交易股票数 | 全市场快照剔除停牌后的条数 | 否，仅最近交易日 |
| `advance_count` | 上涨家数 | 上述样本中 `price_change > 0` 计数 | 否，仅最近交易日 |
| `turnover` | 全市场成交额 | `index history 000001.SH` 的 `turnover`（**沪市口径**） | 是 |
| `limit_up` | 收盘涨停家数 | `special limit-up-pool` 条数 | 是 |
| `limit_down` | 收盘跌停家数 | `special limit-down-pool` 条数 | 是 |
| `first_board` | 首板家数 | 涨停池 `continue_day_cnt == 1` | 是 |
| `consecutive` | 严格连续连板家数 | 涨停池 `continue_day_cnt >= 2` | 是 |
| `space` | 最高连续板高度 | 涨停池 `continue_day_cnt` 最大值 | 是 |
| `next_space` | 次高连续板高度 | 去重降序取第二个，无则 0 | 是 |
| `bomb_rate` | 炸板率 | 炸板数 / (涨停数 + 炸板数) | 是 |
| `yday_limitup_ret` | 昨日涨停股今日反馈（百分点） | 昨日涨停池成分今日涨跌幅均值 | 是 |
| `yday_lianban_ret` | 昨日连板股今日反馈（百分点） | 其中 `continue_day_cnt >= 2` 子集均值 | 是 |
| `p12` | 1 进 2 晋级率 | 今日二板 ÷ 昨日首板 | 是 |
| `p23` | 2 进 3 晋级率 | 今日三板 ÷ 昨日二板 | 是 |
| `p3p` | 3 板以上晋级率 | 今日四板及以上 ÷ 昨日三板及以上 | 是 |
| `board2` | 二板家数 | 涨停池 `continue_day_cnt == 2` | 是 |
| `board3` | 三板家数 | 涨停池 `continue_day_cnt == 3` | 是 |
| `board4p` | 四板及以上家数 | 涨停池 `continue_day_cnt >= 4` | 是 |

晋级率分母小于 3 时置空（与 `with_promotion_rates` 的 `MIN_DENOM = 3` 一致）。

## 2026-09-14 逐字段对账

面板取自 `D:\MyProjects\股票分析\data\panel_history.csv`（该行由开盘啦口径产出），右侧为本 Skill 用同花顺官方接口重算的结果。

| 字段 | panel_history.csv | 同花顺官方源 | 结论 |
| --- | --- | --- | --- |
| `sh_close` | 3885.33 | 3885.33 | 一致 |
| `sh_ma250` | 3988.554696 | 3988.55464 | 差 5.6e-5，日线收盘取两位小数的累积舍入 |
| `turnover` | 779281246497 | 779281250000 | 差 0.0000004%，接口按万元取整 |
| `limit_up` | 55 | 55 | 一致 |
| `limit_down` | 16 | 16 | 一致 |
| `first_board` | 44 | 44 | 一致 |
| `consecutive` | 11 | 11 | 一致 |
| `space` | 4 | 4 | 一致 |
| `next_space` | 3 | 3 | 一致 |
| `bomb_rate` | 0.3529 | 0.3529 | 一致 |
| `yday_limitup_ret` | 3.21 | 3.2131 | 一致（开盘啦给两位小数） |
| `yday_lianban_ret` | 3.53 | 3.532 | 一致 |
| `p12` | 0.21212121212121213 | 0.21212121212121213 | 逐位一致 |
| `p23` | 0.75 | 0.75 | 一致 |
| `p3p` | 0.3333333333333333 | 0.3333333333333333 | 一致 |
| `board2` | 7.0 | 7 | 一致 |
| `board3` | 3.0 | 3 | 一致 |
| `board4p` | 1.0 | 1 | 一致 |
| `tradable_count` | 5550.0 | 5550（5573 条剔除 23 只停牌） | 口径一致 |
| `advance_count` | 3126.0 | 留空 | 全市场快照无历史口径，未回溯 |

19 个字段中 18 个可直接复用；`advance_count` 的历史值需要另行补齐。

## 口径差异与处理

1. **涨跌家数**：同花顺全市场快照覆盖沪市 + 深市 + 北交所共 5573 只，其中停牌 23 只（`volume` 与 `last_price` 为 0）。剔除停牌后 5550 只，与面板既有 `tradable_count` 完全一致。判定停牌用 `last_price > 0`，不要用 `price_change != 0`（平盘股会被误伤，当日平盘 191 只）。
2. **成交额**：接口返回按万元取整。模型的成交额是对数分位，这个量级差异可忽略。
3. **昨涨停今表现**：同花顺侧是等权均值，开盘啦是自算指标，两者相差约 0.1~0.2 个百分点，方向一致。
4. **ST 与新股**：2026-09-14 实测涨停池 55 只中 `is_st`、`is_new`、北交所标记均为 0，池子本身干净；字段仍带 `is_st` / `is_new` 标记，严格复现时可按需过滤。

## 历史涨跌家数怎么补

同花顺提供全市场数据导出（A 股全市场 10 年日 K、最近 10 交易日日 K、复权因子 Parquet），可用它离线重算历史 `advance_count` 与 `tradable_count`：

```bash
hithink-finance schema market.dump   # 先看当前命令名与参数
hithink-finance capabilities --format json | findstr /i dump
```

或用 CLI 的本地库一次性建面再跑 SQL：

```bash
hithink-finance data init --format json
hithink-finance data sync --format json
hithink-finance db query --sql "SELECT ..." --format json
```

## 原始命令清单

```bash
hithink-finance market calendar --format json
hithink-finance index history --thscode 000001.SH --start-ms <ms> --end-ms <ms> --format json
hithink-finance special limit-up-pool   --date-ms <ms> --page 1 --size 200 --format json
hithink-finance special limit-down-pool --date-ms <ms> --page 1 --size 200 --format json
hithink-finance special limit-break-pool --date-ms <ms> --page 1 --size 200 --format json
hithink-finance special limit-up-ladder --format json
hithink-finance market snapshot --limit 5000 --offset 0 --format json
hithink-finance market history --thscode <code> --start-ms <ms> --end-ms <ms> --format json
```

`--date-ms` 是交易日 Asia/Shanghai 零点的毫秒时间戳；省略即为当日。

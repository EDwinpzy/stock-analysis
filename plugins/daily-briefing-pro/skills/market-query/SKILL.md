---
name: market-query
description: 'A股行情 API 查询：通过同花顺行情 SDK 或扶摇 REST 获取实时报价、日/周/月/分钟 K 线、分时、逐笔、排行、板块、自选股与自选分组，并检索 118 个 DataHub 接口、20 个 DataAccessor 请求、6 个订阅、276 个字段和 120 个扶摇公网 GET 端点。'
metadata:
  legacy:
    trigger_words:
    - 行情查询
    - 查行情
    - 实时报价
    - K线
    - 分时
    - 逐笔
    - 排行榜
    - 自选股
    - 自选分组
    - DataHub
    - 扶摇
    - 同花顺金融数据
    - 冗余接口
    version: 2.0.0
    author: Codex
    dependencies:
      external_tools:
      - python
---

# 行情查询

本项目只保留跨平台 Python 入口。所有行情请求由同花顺行情 SDK 或扶摇 REST API 完成，
不要求 Windows、同花顺远航版、Lumi、PowerShell 或任何桌面登录态。统一输出 UTF-8 JSON。

## 入口

```bash
python scripts/market_query.py status --probe
python scripts/market_query.py search 贵州茅台
python scripts/market_query.py realtime 600519
python scripts/market_query.py candle 600519 --period 5 --count 60
python scripts/market_query.py trend 600519
python scripts/market_query.py tick 600519 --count 20
python scripts/market_query.py blocks 白酒
python scripts/market_query.py sector --target 白酒
python scripts/market_query.py sort --block 14 --sort-field 199112 --sort-order 1 --count 20
python scripts/market_query.py watchlist
python scripts/market_query.py sectors
python scripts/market_query.py subscribe --api SubscribeRealtime --target 600519
python scripts/market_query.py call --tool sort_query --arguments-json '{"block":14,"sortField":199112,"sortOrder":1,"count":20}'
python scripts/market_query.py call --tool wencai_query --arguments-json '{"skillId":"hithink-market-query","query":"今日涨幅前20","page":1,"limit":20}'
python scripts/market_query.py news 600519
python scripts/market_query.py capital-flow 600519
python scripts/market_query.py fields --data-type tick --query 最新价
python scripts/market_query.py catalog --source cloud --query 行情
python scripts/market_query.py cloud-get '/api/a-share/prices/snapshot?thscodes=600519.SH'
python scripts/market_query.py realtime 600519 --mode cloud
python scripts/market_query.py candle 600519 --mode cloud --count 20
python scripts/market_query.py sector --target 白酒 --mode cloud
```

## 通道

| 模式 | 数据源 | 依赖 |
| --- | --- | --- |
| `auto`（默认） | 先走 `thsdk` 行情 SDK，失败后回退扶摇 REST | Python 包与云端 API |
| `ths` | `thsdk` 行情 SDK | `thsdk`；可选固定账号环境变量 |
| `cloud` | 扶摇 REST | `FUYAO_API_KEY` / `HITHINK_API_KEY` / `HITHINK_FINANCE_API_KEY` |

两种模式都是服务端 API 通道，不读取桌面客户端或本机登录态。显式 `FUYAO_API_KEY`
优先用于 REST；问财查询使用独立的 `IWENCAI_API_KEY` / `WENCAI_API_KEY`，不能拿扶摇
Key 冒充。所有命令加 `--include-meta` 可查看实际来源和尝试链。

`status --probe` 会实际请求行情通道；只有至少一条通道返回证券记录时退出码才为 0。
仅“已安装依赖”或“已配置 Key”不算连通成功。盘口/分时的供应商哨兵值
`2147483648` 会转换为 `null`，不能展示成真实价格。

生产环境可为 `thsdk` 配置 `THS_USERNAME`、`THS_PASSWORD`、`THS_MAC`；未配置时使用
临时游客账号，只适合验证。纯 REST 只需 API Key，不读取其他账号状态。

## 能力边界

- `search`、`blocks`、`realtime`、日 K、排行、板块和已登记云 GET 接口可走扶摇 REST。
- `trend` 和 `tick` 依赖 `thsdk` 行情接口；扶摇公开 REST 没有对应端点。
- 周/月/分钟 K 的云 REST 能力取决于已登记接口；失败时明确报告缺口，不伪造周期。
- 个股新闻在 `ths` 模式读取公告/研报/社区接口，在 `cloud` 模式读取
  `/api/news/stock/timeline-list`。
- 扶摇公开 API 的逐笔资金流端点标记为 `client-only`；`capital-flow --mode cloud`
  应明确报错，不能拿其他指标冒充大单数据。
- `subscribe` 是收到首帧后退订的一次性快照，不是长连接推送。
- 个人自选股和分组从 `THS_SELFSTOCK_PATH`（云端为 `/run/secrets/ths_selfstock.json`）
  读取；未提供时返回 `unavailable`，不伪造空分组。

完整云接口目录以 `references/cloud-apis.md` 和 `references/cloud-apis.csv` 为准。
共 120 个 GET 端点，其中 11 个标记为 `client-only`，外部 API Key 可能没有权限。

## 只读与安全

1. `cloud-get` 只允许 `https://fuyao.aicubes.cn/api/...`（测试时允许 loopback），
   拒绝 URL 凭据、fragment 和短时签名下载链接。
2. `read_doc`、`client_script_execute`、`pine_script_execute`、任意 HTTP 和脚本执行
   不属于云端白名单；不得为了移植而放开本地文件读取或代码执行。
3. 查询默认只读。`manageSector` 只允许 `operation=query`；除非用户明确要求并有单独
   写操作流程，不创建、删除或重命名自选分组。
4. 不读取、打印、保存或转发 Cookie、Bearer Token、账号密码、API Key 或会话文件。
5. Key 只通过环境变量或平台 Secret 注入，不写进命令参数、源码、日志或报告。

## 口径

- K 线周期：`5=日`、`11=周`、`12=月`、`15=1分`、`16=5分`、`17=15分`、
  `18=30分`、`19=60分`。复权：`0=不复权`、`1=前复权`、`2=后复权`。
- 跨通道代号自动转换：`thsdk` 使用 `USHA600519` 一类代号，扶摇 REST 使用
  `600519.SH`。输出 `thscode` 统一为内部代号，`vendor_thscode` 保留源值。
- DataHub 与扶摇统一信封为 `{code,message,data,request_id}`；HTTP 200 仍可能业务失败。
  `2001/2003` 是认证或权限问题，`4001` 是限流，`5003` 是上游暂不可用。
- 网络错误、HTTP 429 和 5xx 可有限重试；业务错误不盲目重试。遇到 429 应降低并发。
- 输出行情时说明来源、口径和取数时间；盘中、收盘后和历史数据不能混用。

## 故障排查

| 现象 | 处理 |
| --- | --- |
| 云端提示 API Key 未配置 | 设置 `FUYAO_API_KEY` 或 `HITHINK_API_KEY` |
| 云端 `2001/2003` | Key 无效、已撤销或无 capability 权限；不要重试 |
| 云端 `4001` / HTTP 429 | 降低并发和频率，稍后重试 |
| 云端 `5002/5003` | 上游超时或暂不可用；允许有限重试，不改写结果 |
| `candle --mode cloud --period 16` 失败 | 该云通道没有分钟线；改用 `ths`，或明确报告缺口 |
| 盘前 `sort --mode cloud` 返回 `total=0` | 快照尚无涨跌值；保留 `missing_count` 与取数时间 |
| 盘前实时/分时出现 `2147483648` | 供应商空值哨兵；应输出 `null` |
| `status --probe` 失败 | 两条真实通道都未返回证券；检查网络、`thsdk` 账号或扶摇 Key |
| `watchlist` 返回空 | 设置 `THS_SELFSTOCK_PATH` 或挂载容器 Secret |
| `capital-flow --mode cloud` 失败 | 公开云接口没有该能力；改用 `ths` 或报告缺口 |

完整接口契约：

- `references/cloud-apis.md` / `.csv` / `.json`
- `references/datahub-apis.md` / `.csv`
- `references/dataaccessor-apis.md` / `.csv`
- `references/dataaccessor-subscribe-apis.csv`
- `references/dataaccessor-fields.csv`
- 在线文档：<https://fuyao.aicubes.cn/docs/>

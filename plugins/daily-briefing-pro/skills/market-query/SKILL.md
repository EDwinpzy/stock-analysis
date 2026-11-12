---
name: market-query
description: 'A股行情双通道查询：优先复用本机同花顺远航版/Lumi MCP，失败时自动回退到同花顺扶摇 REST API；也可完全脱离客户端使用云端模式。覆盖实时报价、日/周/月/分钟K线、分时、逐笔、排行、板块、自选股与自选分组，以及 118 个 DataHub 接口、20 个 DataAccessor 请求、6 个订阅、276 个字段和 120 个扶摇公网 GET 端点。'
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
    version: 1.1.0
    author: Codex
    dependencies:
      external_tools:
      - python
      - pwsh
---

# 行情查询

提供两条可切换、可回退的行情链路，统一输出 UTF-8 JSON：

| 模式 | 数据源 | 是否需要桌面客户端 | 适用场景 |
|---|---|---|---|
| `auto`（默认） | 本机 MCP 优先，云端兜底 | 本地通道需要 | 日常使用，客户端在线时保持原口径 |
| `local` | 同花顺远航版/Lumi MCP | 是 | 分时、逐笔、排行、订阅、个人自选 |
| `cloud` | 同花顺金融数据（扶摇）REST API | 否 | 服务器、其他设备、客户端未启动 |

`auto` 不是“无条件双写”：它先执行本地查询；只有本地不可用、返回错误或不支持该口径时，才尝试已配置的云端通道。需要确认最终用了哪条链路时加 `-IncludeMeta`。

## Python 跨平台入口（推荐）

不依赖 Lumi、PowerShell 或任何桌面客户端，Windows/Linux/macOS 均可运行：

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
python scripts/market_query.py realtime 600519 --mode cloud
python scripts/market_query.py candle 600519 --mode cloud --count 20
python scripts/market_query.py sector --target 白酒 --mode cloud
```

默认 `--mode auto`：先用 `thsdk` 直连同花顺行情服务，失败且已配置 `FUYAO_API_KEY` / `HITHINK_API_KEY` / `HITHINK_FINANCE_API_KEY` 时回退扶摇 REST；显式 `FUYAO_API_KEY` 优先。`--mode ths` 强制直连，`--mode cloud` 强制 REST。问财查询使用独立的 `IWENCAI_API_KEY` / `WENCAI_API_KEY`，不能拿扶摇 Key 冒充。所有命令输出 UTF-8 JSON；加 `--include-meta` 可看到实际来源和尝试链。`cloud-get` 可调用 `references/cloud-apis.csv` 中任一路径，`datahub-get` 是兼容别名。

`status --probe` 会分别实际请求 `thsdk` 和扶摇通道；只有至少一条真实行情链路返回证券记录时退出码才为 0。仅“已安装依赖”或“已配置 Key”不算连通成功。盘口/分时的供应商哨兵值 `2147483648` 会统一输出为 `null`，不会当作真实价格。

`thsdk` 自带 Windows/Linux/macOS 动态库，生产环境建议通过 `THS_USERNAME`、`THS_PASSWORD`、`THS_MAC` 注入固定账号；未配置时使用临时游客账号，只适合验证。REST 模式只需要 API Key，不读取本机客户端。

Python 入口的 `trend` 和 `tick` 使用 `thsdk` 直连，字段口径与桌面端一致：分时为 `1/10/13/19`，逐笔为 `1/10/12/18/49`。扶摇公开 REST 没有分时/逐笔端点，因此这两项只支持 `--mode ths` 或 `auto` 的本地直连回退；`fields` 则直接检索随插件发布的字段目录，不需要任何客户端。

`call --tool wencai_query` 优先调用官方问财 OpenAPI `https://openapi.iwencai.com/v1/query2data`，支持原生 21 个 `skillId`，返回 `datas/columns/row_count/status_code` 契约。配置 `IWENCAI_API_KEY`（或兼容的 `WENCAI_API_KEY`）即可在云端使用；未配置时只有 `hithink-market-query` 会降级到 `thsdk` 的 `wencai_nlp`，并按 `page/limit` 分页。游客账号可能被问财服务拒绝，生产环境建议配置固定的 `THS_USERNAME`、`THS_PASSWORD` 和 `THS_MAC`。这条通道不依赖 Windows 或 Lumi 客户端。

`read_doc`、`client_script_execute`、`pine_script_execute`、`level_query`、`pattern_query`、`http_get` / `http_post` 等原生 MCP 扩展不在云端白名单内：`read_doc` 只服务于桌面端脚本/工具文档，云端不能按本地路径任意读取；任意 HTTP 和脚本执行也不应因为“移植”而放开。云端可替代的固定能力是 `cloud-get` / `datahub-get`（仅已登记 GET 接口）、`subscribe`（一次性首帧）和 `indicator_query`（标准指标）。需要新增原生扩展时，必须先在 `references/` 登记契约并补测试，不能静默伪造结果。

跨通道代号由 CLI 自动转换：`thsdk` 使用 `USHA600519`，扶摇 REST 使用 `600519.SH`。输出中的 `thscode` 统一为内部代号，`vendor_thscode` 保留数据源原值。个股新闻在 `ths` 模式读取 `0x3805` 公告、`0x3806` 研报、`0x3808` 社区；`cloud` 模式读取 `/api/news/stock/timeline-list`。扶摇公开 API 的逐笔资金流端点标记为 `client-only`，因此 `capital-flow --mode cloud` 会明确报错，不会用其他指标冒充大单数据。

## 前置条件

### 本地通道

以下条件只适用于 PowerShell 客户端的 Lumi `local` 模式；Python 入口的 `ths` 模式通过 `thsdk` 直连，不需要 Lumi。

- Windows 电脑上的同花顺远航版/Lumi 已启动并登录。
- Lumi MCP 桥可用，本机存在 `%USERPROFILE%\lumi\users\*\agent-sdk\opencode\config\opencode.jsonc`。
- 多账号可追加 `-User <用户名>`。

### 云端通道

1. 在 <https://fuyao.aicubes.cn/admin/> 申请 API Key。
2. 任选一种保存方式：
   - 设置进程或系统环境变量 `HITHINK_API_KEY`；
   - 运行 `pwsh -File scripts/cloud_key.ps1 -Action set`，按隐藏提示粘贴 Key，使用 Windows DPAPI 加密保存到当前用户目录。
3. 用 `status` 查看配置状态；它不会打印 Key。

```powershell
pwsh -NoProfile -File scripts/cloud_key.ps1 -Action set
pwsh -NoProfile -File scripts/cloud_key.ps1 -Action status
pwsh -NoProfile -File scripts/cloud_key.ps1 -Action clear
pwsh -NoProfile -File scripts/market_query.ps1 status
```

云端请求使用 `X-api-key`，Base URL 为 `https://fuyao.aicubes.cn`。不要把 Key 写在命令行参数、聊天消息、插件文件、日志或源码中。服务端部署时应使用平台的 Secret Manager 或环境变量注入。

## 能力范围

| 能力 | 命令 | 本地 MCP | 扶摇云 API |
|---|---|---:|---:|
| DataHub 全量目录 | `catalog -Source datahub` | 118 个 GET | 按路径兼容 |
| DataAccessor 请求目录 | `catalog -Source dataaccessor` | 20 个 | - |
| 实时订阅目录 | `catalog -Source subscribe` | 6 个 | - |
| 字段目录 | `catalog -Source fields` / `fields` | 276 个 FieldID | - |
| 扶摇接口目录 | `catalog -Source cloud` | - | 120 个 GET |
| 证券解析 | `search` | 是 | 是 |
| 板块解析 | `blocks` | 是 | 是 |
| 实时报价 | `realtime` | 是 | 是 |
| 日 K | `candle -Period 5` | 是 | 是 |
| 周/月/分钟 K | `candle -Period 11/12/15/16/17/18/19` | 是 | 否 |
| 分时/盘前/盘后/集合竞价 | `trend` | 是 | 否 |
| 逐笔 | `tick` | 是 | 否 |
| 排行榜 | `sort` | 是 | 是（同花顺板块成员优先，扶摇市场范围回退） |
| 首次推送订阅 | `subscribe` | 是 | 一次性快照（实时和日 K）；分时/逐笔需 `thsdk` |
| 自选股/分组 | `watchlist` / `sectors` / `sector` | 是 | 读取 `THS_SELFSTOCK_PATH` 或 Secret 文件 |
| 按指数代码取成分 | `sector -Target 886042.TI -Mode cloud` | 是 | 是 |
| DataHub 指定接口 | `datahub-get` | 登录态代理 | 同名 `/api/...` |
| 任意已登记云接口 | `cloud-get` | - | 是 |
| 其他只读原生查询 | `call` | 白名单 | 白名单中的可移植工具 |

云端公开能力以 `references/cloud-apis.md` 和 `references/cloud-apis.csv` 为准。共 120 个 GET 端点，其中 11 个标记为 `client-only`；这些接口即使出现在官方文档里，也不应假定外部 API Key 有权限。

个人自选股和自选分组属于登录用户数据，扶摇公网 API 不提供读取。跨平台入口直接读取 `THS_SELFSTOCK_PATH`（云端为 `/run/secrets/ths_selfstock.json`），因此不会把本机登录态带入云端，也不会伪造空分组。`sort` 在 `auto` 模式优先使用 `thsdk` 的板块成员计算排行；没有 `thsdk` 时，纯扶摇 REST 支持 14/21/27/50854 市场范围和 `.TI` 指数成员。`subscribe` 的输出是收到首帧后退订的一次性快照，不是长连接推送。

## 常用调用

### 默认自动回退

```powershell
pwsh -NoProfile -File scripts/market_query.ps1 search 贵州茅台
pwsh -NoProfile -File scripts/market_query.ps1 realtime 600519 -Fields 10,55,199112
pwsh -NoProfile -File scripts/market_query.ps1 candle 600519 -Period 5 -Count 60 -AdjustType 1
pwsh -NoProfile -File scripts/market_query.ps1 datahub-get '/api/a-share/prices/snapshot?thscodes=600519.SH'
pwsh -NoProfile -File scripts/market_query.ps1 watchlist
pwsh -NoProfile -File scripts/market_query.ps1 sort -Block 14 -SortField 199112 -SortOrder 1 -Count 20
pwsh -NoProfile -File scripts/market_query.ps1 subscribe -SubscribeApi SubscribeRealtime -Target 600519 -TimeoutMs 10000
```

检查实际来源：

```powershell
pwsh -NoProfile -File scripts/market_query.ps1 realtime 600519 -IncludeMeta
```

返回外层会包含 `_meta.source`（`local` 或 `cloud`）和每次尝试的脱敏结果。

### 完全脱离客户端

```powershell
pwsh -NoProfile -File scripts/market_query.ps1 search 贵州茅台 -Mode cloud
pwsh -NoProfile -File scripts/market_query.ps1 realtime 600519 -Mode cloud
pwsh -NoProfile -File scripts/market_query.ps1 candle 600519 -Mode cloud -Period 5 -Count 60 -AdjustType 1
pwsh -NoProfile -File scripts/market_query.ps1 blocks 光伏 -Mode cloud
pwsh -NoProfile -File scripts/market_query.ps1 sector -Target 886042.TI -Mode cloud
```

云端日 K 只支持 `Period=5`。请求周/月/分钟线时必须使用 `-Mode local`，或用 `auto` 让本地通道处理。

### 强制本地

```powershell
pwsh -NoProfile -File scripts/market_query.ps1 trend 600519 -Mode local
pwsh -NoProfile -File scripts/market_query.ps1 tick 600519 -Count 20 -Mode local
pwsh -NoProfile -File scripts/market_query.ps1 sort -Block 14 -SortField 199112 -SortOrder 1 -Count 20 -Mode local
pwsh -NoProfile -File scripts/market_query.ps1 sectors -Mode local
```

### 任意扶摇 REST 端点

`cloud-get` 只允许 `https://fuyao.aicubes.cn/api/...`（测试时允许 loopback），拒绝 URL 凭据、fragment 和短时签名下载链接。

```powershell
# 路径内直接带查询串
pwsh -NoProfile -File scripts/market_query.ps1 cloud-get '/api/a-share/prices/snapshot?thscodes=600519.SH' -Mode cloud

# 用 ArgumentsJson 传参数，脚本负责 URL 编码
pwsh -NoProfile -File scripts/market_query.ps1 cloud-get '/api/a-share/auction/snapshot' -ArgumentsJson '{"thscodes":"600519.SH,000001.SZ"}' -Mode cloud

# 先查目录和必需参数
pwsh -NoProfile -File scripts/market_query.ps1 catalog -Source cloud -Query 龙虎榜 -All
pwsh -NoProfile -File scripts/market_query.ps1 catalog -Source cloud -Query financials -All
```

其余高频用法：

```powershell
pwsh -NoProfile -File scripts/market_query.ps1 candle 600519 -Period 11 -Count 20
pwsh -NoProfile -File scripts/market_query.ps1 candle 600519 -Period 16 -Count 20
pwsh -NoProfile -File scripts/market_query.ps1 trend 600519
pwsh -NoProfile -File scripts/market_query.ps1 tick 600519 -Count 20
pwsh -NoProfile -File scripts/market_query.ps1 sort -Block 14 -SortField 199112 -SortOrder 1 -Count 20
pwsh -NoProfile -File scripts/market_query.ps1 sector -Target 234
```

多个证券用逗号分隔：

```powershell
pwsh -NoProfile -File scripts/market_query.ps1 realtime '600519,000001,300750' -Fields 10,55,199112
```

目录检索与字段检索：

```powershell
pwsh -NoProfile -File scripts/market_query.ps1 catalog -Source datahub -Query 北向 -All
pwsh -NoProfile -File scripts/market_query.ps1 fields -DataType realtime -Query 市值 -All
pwsh -NoProfile -File scripts/market_query.ps1 fields -Query 市值 -All
```

订阅与只读原生查询：

```powershell
pwsh -NoProfile -File scripts/market_query.ps1 subscribe -SubscribeApi SubscribeRealtime -Target 600519 -Fields 6,7,8,9,10,13,55,199112,264648 -TimeoutMs 10000
pwsh -NoProfile -File scripts/market_query.ps1 call -Tool wencai_query -ArgumentsJson '{"skillId":"hithink-market-query","query":"今日涨幅前20","limit":20}'
pwsh -NoProfile -File scripts/market_query.ps1 call -Tool indicator_query -ArgumentsJson '{"securities":[{"market":"USHA","code":"600519"}],"period":"day","indicators":["MA5","MA20","MACD","RSI14"],"mode":"latest"}'
```

## 输出与口径

- 本地输出保持原有结构；云端实时行情会同时给出官方字段名和常用 FieldID 别名（`5/6/7/8/9/10/13/19/55/199112/264648`）。
- 云端日 K 会映射为本地常见 FieldID（`1/7/8/9/11/13/19`）并保留 `time`、`date_ms`。
- 云端证券解析返回 `thscode`、`ticker`、`exchange`；本地 `securities[]` 使用 `market + code`，不要混用。
- 加 `-IncludeMeta` 时，最外层为 `{_meta, data}`；不加时保持命令原有返回结构。
- 输出行情时同时说明数据来源、口径和取数时间；盘中、收盘后和历史数据不要混用。结果是行情事实，不是投资建议。

## 执行规则

1. 除排行、板块搜索和已知 market/code 外，先解析证券。本地用 `search` 返回的 `market + code`，云端用 `thscode`。
2. K 线周期：`5=日`、`11=周`、`12=月`、`15=1分`、`16=5分`、`17=15分`、`18=30分`、`19=60分`。复权：`0=不复权`、`1=前复权`、`2=后复权`。
3. 分时变体：`RequestIntradayTrendDataAsync`、`RequestTrendDataAsync`、`RequestPreMarketTrendDataAsync`、`RequestPostMarketTrendDataAsync`、`RequestCallAuctionDataAsync`。
4. 逐笔变体：`RequestIntradayTickDataAsync`、`RequestTickDataAsync`、`RequestPreMarketTickDataAsync`、`RequestPostMarketTickDataAsync`。
5. DataHub 与扶摇统一信封为 `{code,message,data,request_id}`；HTTP 200 仍可能业务失败，必须检查 `code`。`2001/2003` 是认证或权限问题，`4001` 是限流，`5003` 是上游暂不可用。
6. 云端自动重试只针对网络错误、HTTP 429 和 5xx；业务错误不会盲目重试。遇到 429 应降低并发并稍后再试。
7. 三个 `/api/dump/market-dumps/*/download-url` 会返回短时签名链接，CLI 主动拒绝。不得改用其他方式抓取并落盘这些链接。
8. 查询默认只读。`manageSector` 只允许 `operation=query`；不创建、删除、重命名或修改用户自选分组，除非用户后续明确要求并采用单独的写操作流程。
9. 不读取、打印、保存或转发 Cookie、Bearer Token、账号密码、API Key、`artifacts/session-messages.json` 等敏感材料。

## 已知口径与故障排查

| 现象 | 处理 |
|---|---|
| 找不到本机 Lumi MCP 配置 | 启动并登录 Lumi；多账号时显式传 `-User`；或改用 `-Mode cloud`。 |
| 云端提示 API Key 未配置 | 设置 `HITHINK_API_KEY`，或运行 `cloud_key.ps1 -Action set`。 |
| 云端 `2001/2003` | Key 无效、已撤销或当前 Key 无该 capability 权限；不要重试。 |
| 云端 `4001` / HTTP 429 | 降低并发和频率，稍后重试。 |
| 云端 `5002/5003` | 上游超时或暂不可用；允许有限重试，不要改写结果。 |
| `candle -Mode cloud -Period 16` 失败 | 云端只支持日线，改用 `-Mode local` 或 `auto`。 |
| 盘前 `sort --mode cloud` 返回 `total=0` | 快照尚未有实时涨跌值；保留 `missing_count` 和取数时间，不伪造排行，也不把空结果解释为接口故障。 |
| 盘前实时/分时出现 `2147483648` | 这是供应商的空值哨兵；Python 入口会转成 `null`，不要展示为价格或涨跌幅。 |
| `status --probe` 失败 | 两条通道的真实证券查询都未返回结果；检查网络、`thsdk` 账号或扶摇 Key，不能只看依赖是否安装。 |
| `watchlist` 返回空 | 设置 `THS_SELFSTOCK_PATH`，或把同花顺自选文件挂到容器 Secret；未提供时明确返回 `unavailable`。 |
| `capital-flow -Mode cloud` 失败 | 扶摇公开 API 的资金流端点标记为 `client-only`；改用 `ths` 模式，或明确报告该缺口。 |
| `sector -Target 白酒 -Mode cloud` 返回空 | 板块名称必须能解析为 `.TI` 指数；可先运行 `blocks 白酒 -Mode cloud` 核对代码。 |
| 自选分组与本地不一致 | 云端只读取显式挂载的自选文件，不同步登录态；用同一份文件时分组口径一致。 |

本地细节：

- 实时外层键是 `market + code`，内层键是字符串 FieldID；部分字段可能返回字符串 `"NaN"`。
- 日 K 的字段 `1` 可能是整数日期，展示时优先用 `time`。
- 分钟 K 的字段 `1` 可能是对象；分时字段 `1` 与 `time` 可能相差 8 小时。展示时间统一优先 `time`。
- 逐笔字段 `1` 可能是毫秒时间戳，而 `time` 是秒；`count` 是近似上限，可能多返一条。
- 订阅只等待首帧并自动退订，不是持续推送通道。
- DataAccessor 的 `GetCookie` 不提供调用；`HttpPostAsync` 不在只读查询白名单内。

完整本地契约：

- `references/datahub-apis.md` / `.csv`
- `references/dataaccessor-apis.md` / `.csv`
- `references/dataaccessor-subscribe-apis.csv`
- `references/dataaccessor-fields.csv`
- `references/datahub-runtime-failures.md`

完整云端契约：

- `references/cloud-apis.md` / `.csv` / `.json`
- 在线文档：<https://fuyao.aicubes.cn/docs/>

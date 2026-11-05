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

## 前置条件

### 本地通道

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
| 排行榜 | `sort` | 是 | 否 |
| 首次推送订阅 | `subscribe` | 是 | 否 |
| 自选股/分组 | `watchlist` / `sectors` / `sector` | 是 | 个人数据不支持 |
| 按指数代码取成分 | `sector -Target 886042.TI -Mode cloud` | 是 | 是 |
| DataHub 指定接口 | `datahub-get` | 登录态代理 | 同名 `/api/...` |
| 任意已登记云接口 | `cloud-get` | - | 是 |
| 其他只读原生查询 | `call` | 白名单 | - |

云端公开能力以 `references/cloud-apis.md` 和 `references/cloud-apis.csv` 为准。共 120 个 GET 端点，其中 11 个标记为 `client-only`；这些接口即使出现在官方文档里，也不应假定外部 API Key 有权限。

个人自选股和自选分组属于登录用户数据，扶摇公网 API 不提供读取。需要脱离客户端时，应自建自选表和分组表；可从本地 `watchlist` / `sectors` 一次性导出后导入自己的存储。

## 常用调用

### 默认自动回退

```powershell
pwsh -NoProfile -File scripts/market_query.ps1 search 贵州茅台
pwsh -NoProfile -File scripts/market_query.ps1 realtime 600519 -Fields 10,55,199112
pwsh -NoProfile -File scripts/market_query.ps1 candle 600519 -Period 5 -Count 60 -AdjustType 1
pwsh -NoProfile -File scripts/market_query.ps1 datahub-get '/api/a-share/prices/snapshot?thscodes=600519.SH'
pwsh -NoProfile -File scripts/market_query.ps1 watchlist
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
| `watchlist -Mode cloud` 失败 | 个人自选属于客户端登录数据；云端模式没有等价接口。 |
| 自选分组与本地不一致 | 云端不读取个人分组；如需独立部署，自建分组表并从本地一次性导入。 |

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

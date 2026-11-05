# Lumi DataAccessor 行情接口清单

数据链路：`window.dataAccessor` / MCP `tool_execute` → IPC → Windows 命名管道 → 同花顺客户端 `PipeServer`。

## 请求类 API

| API | MCP 工具 | 用途 |
|---|---|---|
| `RequestRealtimeDataAsync` | realtime_query | 通用实时行情；盘中默认入口。 |
| `RequestIntradayRealtimeDataAsync` | realtime_query（MCP 目录工具未暴露 api 变体参数） | 盘中实时行情。 |
| `RequestPreMarketRealtimeDataAsync` | realtime_query（MCP 目录工具未暴露 api 变体参数） | 盘前实时行情。 |
| `RequestPostMarketRealtimeDataAsync` | realtime_query（MCP 目录工具未暴露 api 变体参数） | 盘后实时行情。 |
| `RequestCandleDataAsync` | candle_query | K 线查询，支持日/周/月和分钟周期。 |
| `RequestTrendDataAsync` | trend_query | 通用分时，可指定交易时段和历史交易日。 |
| `RequestIntradayTrendDataAsync` | trend_query（api 默认值） | 盘中分时快捷入口。 |
| `RequestPreMarketTrendDataAsync` | trend_query | 盘前分时快捷入口。 |
| `RequestPostMarketTrendDataAsync` | trend_query | 盘后分时快捷入口。 |
| `RequestCallAuctionDataAsync` | trend_query | 集合竞价分时。 |
| `RequestTickDataAsync` | tick_query | 通用逐笔，可指定交易时段。 |
| `RequestIntradayTickDataAsync` | tick_query（api 默认值） | 盘中逐笔快捷入口。 |
| `RequestPreMarketTickDataAsync` | tick_query | 盘前逐笔快捷入口。 |
| `RequestPostMarketTickDataAsync` | tick_query | 盘后逐笔快捷入口。 |
| `RequestSortDataAsync` | sort_query | 按板块返回排序后的证券代码列表。 |
| `SearchSecuritiesAsync` | search_securities | 把代码、中文名或拼音解析成 market+code。 |
| `SearchBlocksAsync` | search_blocks | 按名称模糊搜索客户端市场/行业/概念板块。 |
| `HttpGetAsync` | http_get | 经客户端管道代理的 GET。DataHub 接口依赖此通道复用登录态。 |
| `HttpPostAsync` | http_post | 经客户端管道代理的 POST。 |
| `GetCookie` |  | 内部登录态辅助接口；仅出现在接口目录，当前 MCP 不提供，也不应提取或输出 Cookie。 |

### RequestRealtimeDataAsync

通用实时行情；盘中默认入口。

| 参数 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| `securities` | Array<{market:string, code:string}> | True | 证券列表；market/code 必须来自 SearchSecuritiesAsync 或可信配置。 |
| `fields` | number[] | True | 数字 FieldID 数组；不接受字符串字段名。 |

返回：`{ [market+code]: { [fieldId:string]: number|string|null } }`

### RequestIntradayRealtimeDataAsync

盘中实时行情。

| 参数 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| `securities` | Array<{market:string, code:string}> | True | 证券列表；market/code 必须来自 SearchSecuritiesAsync 或可信配置。 |
| `fields` | number[] | True | 数字 FieldID 数组；不接受字符串字段名。 |

返回：`同 RequestRealtimeDataAsync`

### RequestPreMarketRealtimeDataAsync

盘前实时行情。

| 参数 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| `securities` | Array<{market:string, code:string}> | True | 证券列表；market/code 必须来自 SearchSecuritiesAsync 或可信配置。 |
| `fields` | number[] | True | 数字 FieldID 数组；不接受字符串字段名。 |

返回：`同 RequestRealtimeDataAsync`

### RequestPostMarketRealtimeDataAsync

盘后实时行情。

| 参数 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| `securities` | Array<{market:string, code:string}> | True | 证券列表；market/code 必须来自 SearchSecuritiesAsync 或可信配置。 |
| `fields` | number[] | True | 数字 FieldID 数组；不接受字符串字段名。 |

返回：`同 RequestRealtimeDataAsync`

### RequestCandleDataAsync

K 线查询，支持日/周/月和分钟周期。

| 参数 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| `securities` | Array<{market,code}> | True | 仅允许一只证券。 |
| `fields` | number[] | True | 数字 FieldID 数组；不接受字符串字段名。 |
| `period` | number | True | 5=日、11=周、12=月、15=1分、16=5分、17=15分、18=30分、19=60分。 |
| `adjustType` | number | False | 0=不复权、1=前复权、2=后复权，默认 0。 |
| `timeRange` | object | False | 支持 offset + toLatest、beginTime/endTime、tradeDate。 |

返回：`{ [market+code]: Array<{ time:number, [fieldId:string]: value }> }`

### RequestTrendDataAsync

通用分时，可指定交易时段和历史交易日。

| 参数 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| `securities` | Array<{market:string, code:string}> | True | 证券列表；market/code 必须来自 SearchSecuritiesAsync 或可信配置。 |
| `fields` | number[] | True | 数字 FieldID 数组；不接受字符串字段名。 |
| `tradeClass` | number | True | 2=盘前、1=盘中、3=盘后。 |
| `timeRange` | object | False | 支持 offset + toLatest、beginTime/endTime、tradeDate。 |

返回：`{ [market+code]: Array<{ time:number, [fieldId:string]: number }> }`

### RequestIntradayTrendDataAsync

盘中分时快捷入口。

| 参数 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| `securities` | Array<{market:string, code:string}> | True | 证券列表；market/code 必须来自 SearchSecuritiesAsync 或可信配置。 |
| `fields` | number[] | True | 数字 FieldID 数组；不接受字符串字段名。 |

返回：`{ [market+code]: Array<{ time:number, [fieldId:string]: number }> }`

### RequestPreMarketTrendDataAsync

盘前分时快捷入口。

| 参数 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| `securities` | Array<{market:string, code:string}> | True | 证券列表；market/code 必须来自 SearchSecuritiesAsync 或可信配置。 |
| `fields` | number[] | True | 数字 FieldID 数组；不接受字符串字段名。 |

返回：`同 RequestIntradayTrendDataAsync`

### RequestPostMarketTrendDataAsync

盘后分时快捷入口。

| 参数 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| `securities` | Array<{market:string, code:string}> | True | 证券列表；market/code 必须来自 SearchSecuritiesAsync 或可信配置。 |
| `fields` | number[] | True | 数字 FieldID 数组；不接受字符串字段名。 |

返回：`同 RequestIntradayTrendDataAsync`

### RequestCallAuctionDataAsync

集合竞价分时。

| 参数 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| `securities` | Array<{market:string, code:string}> | True | 证券列表；market/code 必须来自 SearchSecuritiesAsync 或可信配置。 |
| `fields` | number[] | True | 数字 FieldID 数组；不接受字符串字段名。 |

返回：`同 RequestIntradayTrendDataAsync`

### RequestTickDataAsync

通用逐笔，可指定交易时段。

| 参数 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| `securities` | Array<{market:string, code:string}> | True | 证券列表；market/code 必须来自 SearchSecuritiesAsync 或可信配置。 |
| `fields` | number[] | True | 数字 FieldID 数组；不接受字符串字段名。 |
| `tradeClass` | number | True | 文档口径：0=盘前、1=盘中、2=盘后。 |
| `count` | number | False | 最新 N 条，默认 100；与 timeRange 二选一。 |
| `timeRange` | object | False | 支持 offset + toLatest、beginTime/endTime、tradeDate。 |

返回：`{ [market+code]: Array<{ time:number, [fieldId:string]: number }> }`

### RequestIntradayTickDataAsync

盘中逐笔快捷入口。

| 参数 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| `securities` | Array<{market:string, code:string}> | True | 证券列表；market/code 必须来自 SearchSecuritiesAsync 或可信配置。 |
| `fields` | number[] | True | 数字 FieldID 数组；不接受字符串字段名。 |
| `count` | number | False | 最新 N 条，默认 100；与 timeRange 二选一。 |
| `timeRange` | object | False | 支持 offset + toLatest、beginTime/endTime、tradeDate。 |

返回：`{ [market+code]: Array<{ time:number, [fieldId:string]: number }> }`

### RequestPreMarketTickDataAsync

盘前逐笔快捷入口。

| 参数 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| `securities` | Array<{market:string, code:string}> | True | 证券列表；market/code 必须来自 SearchSecuritiesAsync 或可信配置。 |
| `fields` | number[] | True | 数字 FieldID 数组；不接受字符串字段名。 |
| `count` | number | False | 最新 N 条，默认 100；与 timeRange 二选一。 |
| `timeRange` | object | False | 支持 offset + toLatest、beginTime/endTime、tradeDate。 |

返回：`同 RequestIntradayTickDataAsync`

### RequestPostMarketTickDataAsync

盘后逐笔快捷入口。

| 参数 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| `securities` | Array<{market:string, code:string}> | True | 证券列表；market/code 必须来自 SearchSecuritiesAsync 或可信配置。 |
| `fields` | number[] | True | 数字 FieldID 数组；不接受字符串字段名。 |
| `count` | number | False | 最新 N 条，默认 100；与 timeRange 二选一。 |
| `timeRange` | object | False | 支持 offset + toLatest、beginTime/endTime、tradeDate。 |

返回：`同 RequestIntradayTickDataAsync`

### RequestSortDataAsync

按板块返回排序后的证券代码列表。

| 参数 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| `block` | number | True | 板块 ID，如 14=沪深A股、50854=全部A股。 |
| `sortField` | number | True | 排序 FieldID；涨跌幅用 199112。 |
| `sortOrder` | number | True | 0=升序、1=降序。 |
| `offset` | number | True | 分页偏移，从 0 开始。 |
| `count` | number | True | 分页大小，最大 200。 |
| `excludeBlocks` | number[] | False | 排除板块，如 55301=ST。 |

返回：`{ total:number, items:Array<{security:string}> }`

### SearchSecuritiesAsync

把代码、中文名或拼音解析成 market+code。

| 参数 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| `keyword` | string | True | 搜索关键词。 |
| `limit` | number | False | 最大返回数量，默认 20。 |

返回：`Array<{security,name,code,market}>`

### SearchBlocksAsync

按名称模糊搜索客户端市场/行业/概念板块。

| 参数 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| `keyword` | string | True | 板块名称关键词。 |
| `limit` | number | False | 默认 50，范围 1-200。 |

返回：`{ data:Array<{id,idHex,name}>, total:number }`

### HttpGetAsync

经客户端管道代理的 GET。DataHub 接口依赖此通道复用登录态。

| 参数 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| `url` | string | True | 完整 GET URL。 |
| `headers` | object | False | 可选请求头；不要传入或读取 Cookie。 |

返回：`业务方原始响应；MCP 中常为 JSON 字符串。`

### HttpPostAsync

经客户端管道代理的 POST。

| 参数 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| `url` | string | True | 完整 POST URL。 |
| `body` | string | False | 原始请求体。 |
| `headers` | object | False | 可选请求头。 |

返回：`业务方原始响应。`

### GetCookie

内部登录态辅助接口；仅出现在接口目录，当前 MCP 不提供，也不应提取或输出 Cookie。

> 不在复用范围内。

## 订阅类 API

| API | 用途 | 参数 | 推送结构 |
|---|---|---|---|
| `SubscribeRealtime` | 实时行情差量推送。 | securities, fields | `{ [market+code]: { [changedFieldId:string]: value } }` |
| `SubscribeIntradayCandle` | 单证券日内 K 线增量推送。 | securities(单只), fields, period?, adjustType? | `{ [market+code]: Array<row> }` |
| `SubscribeIntradayTrend` | 单证券盘中分时增量推送。 | securities(单只), fields | `{ [market+code]: Array<row> }` |
| `SubscribeTrend` | 单证券通用分时增量推送。 | securities(单只), fields, tradeClass | `{ [market+code]: Array<row> }` |
| `SubscribeIntradayTick` | 单证券盘中逐笔增量推送。 | securities(单只), fields | `{ [market+code]: Array<row> }` |
| `SubscribeTick` | 单证券通用逐笔增量推送。 | securities(单只), fields, tradeClass | `{ [market+code]: Array<row> }` |

## MCP 目录工具

| 工具 | 用途 |
|---|---|
| `candle_query` | 查询单只证券的原始 OHLCV/K 线数据（日/周/月/分钟）；已有标准指标时优先使用 indicator_query |
| `client_exec_script` | 在受限沙箱里执行客户端编排脚本（多步取数/操作的自定义组合） |
| `data_subscribe` | 订阅实时数据流，收到首帧推送后返回并自动退订 |
| `http_get` | 经管道桥接的通用 HTTP GET（DataHub、涨跌分布等场景，须先读对应契约） |
| `http_post` | 经管道桥接的通用 HTTP POST（带请求体，同 http_get 链路） |
| `indicator_query` | 服务端计算常用标准技术指标并返回结构化结果，不操作当前图表；已有 K 线时也应优先使用本工具，避免 Agent 手工重算 |
| `read_doc` | 按需加载受信任的 MCP 工具操作文档与调用链规则 |
| `realtime_query` | 查询证券实时行情字段（最新价、涨跌幅、成交量等） |
| `search_blocks` | 按名称模糊搜索板块树，返回板块 ID |
| `search_fields` | 按数据类型搜索 DataAccessor 字段目录，返回查询工具使用的数字 FieldID |
| `search_securities` | 把代码/中文名/拼音解析为 {market, code}，所有行情工具的前置 |
| `sort_query` | 按板块范围取排行榜（涨幅榜/跌幅榜等）证券列表 |
| `tick_query` | 查询逐笔成交数据（价格、量、买卖方向） |
| `trend_query` | 查询分时走势数据（当日或多日分时） |
| `wencai_query` | 问财结构化查询（21 个 skill：财务、行情筛选、宏观、基金、选股等） |

## 市场编码

| market | 含义 | 示例 |
|---|---|---|
| `USHA` | 沪市 A 股 | 600519 |
| `USZA` | 深市 A 股 | 000001 |
| `USBA` | 北交所 A 股 | 430047 |
| `USHI` | 沪市指数 | 1A0001 / 1B0300 |
| `USZI` | 深市指数 | 399001 / 399006 |
| `URFI` | 同花顺行业/概念指数 | 881279 / 885517 |
| `URFA` | 同花顺三级行业 | 884168 |
| `USHJ` | 沪市基金 | 510300 |
| `USZJ` | 深市基金 | 159919 |
| `UHK` | 港股 | 按搜索结果 |
| `UCF` | 国内商品期货 | 按搜索结果 |
| `UFI` | 全球指数 | 按搜索结果 |

## 字段目录规模

| 类型 | 字段数 |
|---|---:|
| realtime | 260 |
| candle | 7 |
| trend | 4 |
| tick | 5 |

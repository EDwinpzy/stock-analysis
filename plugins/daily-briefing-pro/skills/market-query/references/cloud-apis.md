# 同花顺金融数据（扶摇）REST API 目录

共 120 个 GET 端点。请求头使用 `X-api-key`，Base URL 为 `https://fuyao.aicubes.cn`。

| 接口 | 路径 | 必需参数 | 可用性 | 文档 |
|---|---|---|---|---|
| 行情快照 | `/api/a-share/prices/snapshot` | - | API Key | [文档](https://fuyao.aicubes.cn/docs/api-reference/prices/) |
| 历史 K 线 | `/api/a-share/prices/historical` | `thscode`, `interval`, `start`, `end` | API Key | [文档](https://fuyao.aicubes.cn/docs/api-reference/prices/) |
| 批量历史 K 线 | `/api/a-share/prices/historical-batch` | `thscodes`, `interval`, `start`, `end` | API Key | [文档](https://fuyao.aicubes.cn/docs/api-reference/prices/) |
| 标的检索 | `/api/meta/tickers/search` | `q` | API Key | [文档](https://fuyao.aicubes.cn/docs/api-reference/ticker-search/) |
| 除复权数据 | `/api/a-share/corporate-actions/adjustment-factors` | `thscode` | API Key | [文档](https://fuyao.aicubes.cn/docs/api-reference/corporate-actions/) |
| 标的列表获取 | `/api/meta/tickers/list` | - | API Key | [文档](https://fuyao.aicubes.cn/docs/api-reference/ticker-list/) |
| 利润表 | `/api/a-share/financials/income-statements` | `thscode`, `period` | API Key | [文档](https://fuyao.aicubes.cn/docs/api-reference/financials/) |
| 资产负债表 | `/api/a-share/financials/balance-sheets` | `thscode`, `period` | API Key | [文档](https://fuyao.aicubes.cn/docs/api-reference/financials/) |
| 现金流量表 | `/api/a-share/financials/cash-flow-statements` | `thscode`, `period` | API Key | [文档](https://fuyao.aicubes.cn/docs/api-reference/financials/) |
| 批量利润表 | `/api/a-share/financials/income-statements-batch` | `thscodes`, `period` | API Key | [文档](https://fuyao.aicubes.cn/docs/api-reference/financials/) |
| 批量资产负债表 | `/api/a-share/financials/balance-sheets-batch` | `thscodes`, `period` | API Key | [文档](https://fuyao.aicubes.cn/docs/api-reference/financials/) |
| 批量现金流量表 | `/api/a-share/financials/cash-flow-statements-batch` | `thscodes`, `period` | API Key | [文档](https://fuyao.aicubes.cn/docs/api-reference/financials/) |
| 交易日历 | `/api/a-share/calendar/trading-days` | - | API Key | [文档](https://fuyao.aicubes.cn/docs/api-reference/calendar/) |
| 同花顺指数列表 | `/api/a-share-index/catalog/ths-index-list` | - | API Key | [文档](https://fuyao.aicubes.cn/docs/api-reference/a-share-index/) |
| 同花顺指数成分股 | `/api/a-share-index/constituents/ths-stock-list` | `thscode` | API Key | [文档](https://fuyao.aicubes.cn/docs/api-reference/a-share-index/) |
| 指数行情快照 | `/api/a-share-index/prices/snapshot` | `thscodes` | API Key | [文档](https://fuyao.aicubes.cn/docs/api-reference/a-share-index/) |
| 指数历史 K 线 | `/api/a-share-index/prices/historical` | `thscode`, `interval`, `start`, `end` | API Key | [文档](https://fuyao.aicubes.cn/docs/api-reference/a-share-index/) |
| 个股反查对应行业/板块 | `/api/a-share-index/constituents/ths-index-list-by-stock` | `thscode` | API Key | [文档](https://fuyao.aicubes.cn/docs/api-reference/a-share-index/) |
| 指数批量历史 K 线 | `/api/a-share-index/prices/historical-batch` | `thscodes`, `interval`, `start`, `end` | API Key | [文档](https://fuyao.aicubes.cn/docs/api-reference/a-share-index/) |
| 新股发行与申购 | `/api/a-share/ipo/calendar-list` | `market`, `status` | API Key | [文档](https://fuyao.aicubes.cn/docs/api-reference/a-share-ipo/) |
| 异动股票 | `/api/a-share/special-data/abnormal-monitor-list` | - | API Key | [文档](https://fuyao.aicubes.cn/docs/api-reference/abnormal-monitor/) |
| 个股异动原因列表 | `/api/a-share/special-data/anomaly-analysis-list` | - | API Key | [文档](https://fuyao.aicubes.cn/docs/api-reference/anomaly-analysis/) |
| 按股票查询个股异动原因 | `/api/a-share/special-data/anomaly-analysis-stock` | `thscodes` | API Key | [文档](https://fuyao.aicubes.cn/docs/api-reference/anomaly-analysis/) |
| 集合竞价个股机会筛选 | `/api/a-share/special-data/auction-stock-opportunities` | - | API Key | [文档](https://fuyao.aicubes.cn/docs/api-reference/auction-opportunities/) |
| 集合竞价可选交易日期 | `/api/a-share/special-data/auction-opportunity-dates` | - | API Key | [文档](https://fuyao.aicubes.cn/docs/api-reference/auction-opportunities/) |
| A股集合竞价快照 | `/api/a-share/auction/snapshot` | `thscodes` | API Key | [文档](https://fuyao.aicubes.cn/docs/api-reference/auction/) |
| 短线风向标竞价基准 | `/api/a-share/auction/short-term-benchmark` | - | API Key | [文档](https://fuyao.aicubes.cn/docs/api-reference/auction/) |
| 资金流向实时快照 | `/api/a-share/capital-flow/snapshot` | `thscode` | 仅客户端 | [文档](https://fuyao.aicubes.cn/docs/api-reference/capital-flow/) |
| 资金流向历史 | `/api/a-share/capital-flow/historical` | `thscode`, `interval`, `start`, `end` | 仅客户端 | [文档](https://fuyao.aicubes.cn/docs/api-reference/capital-flow/) |
| 筹码形态可选日期 | `/api/a-share/special-data/chip-shape-dates` | - | 仅客户端 | [文档](https://fuyao.aicubes.cn/docs/api-reference/chip-shape/) |
| 筹码形态股票筛选 | `/api/a-share/special-data/chip-shape-stocks` | `shape` | 仅客户端 | [文档](https://fuyao.aicubes.cn/docs/api-reference/chip-shape/) |
| 龙虎榜数据 | `/api/a-share/special-data/dragon-tiger-list` | - | API Key | [文档](https://fuyao.aicubes.cn/docs/api-reference/dragon-tiger-data/) |
| 营业部经典战绩 | `/api/a-share/special-data/dragon-tiger-department-classic-record` | `department_id` | API Key | [文档](https://fuyao.aicubes.cn/docs/api-reference/dragon-tiger-department/) |
| 营业部历史上榜记录 | `/api/a-share/special-data/dragon-tiger-department-history` | `department_id` | API Key | [文档](https://fuyao.aicubes.cn/docs/api-reference/dragon-tiger-department/) |
| 个股机构交易详情 | `/api/a-share/special-data/dragon-tiger-stock-institution` | `thscode` | API Key | [文档](https://fuyao.aicubes.cn/docs/api-reference/dragon-tiger-institution/) |
| 宽基ETF申购净流入 | `/api/fund/etf-flow/net-inflow-historical` | - | 仅客户端 | [文档](https://fuyao.aicubes.cn/docs/api-reference/etf-net-flow/) |
| 基金在线回测 | `/api/fund/backtest/result` | `thscode`, `buy_conditions`, `sell_conditions`, `buy_frequency_type`, `max_buy_times`, `per_buy_amount` | API Key | [文档](https://fuyao.aicubes.cn/docs/api-reference/fund-backtest/) |
| 基金回测可用指标 | `/api/fund/backtest/indicators` | - | API Key | [文档](https://fuyao.aicubes.cn/docs/api-reference/fund-backtest/) |
| 基金公司详情 | `/api/fund/companies/detail` | `company_id` | API Key | [文档](https://fuyao.aicubes.cn/docs/api-reference/fund-company/) |
| 基金分红记录 | `/api/fund/corporate-actions/dividends` | `thscode` | API Key | [文档](https://fuyao.aicubes.cn/docs/api-reference/fund-corporate-actions/) |
| 基金诊断详情 | `/api/fund/diagnostics/detail` | `thscode` | API Key | [文档](https://fuyao.aicubes.cn/docs/api-reference/fund-diagnostics/) |
| 基金财务指标 | `/api/fund/financials/indicators` | `thscode` | API Key | [文档](https://fuyao.aicubes.cn/docs/api-reference/fund-financials/) |
| 基金利润表 | `/api/fund/financials/income-statements` | `thscode` | API Key | [文档](https://fuyao.aicubes.cn/docs/api-reference/fund-financials/) |
| 基金资产负债表 | `/api/fund/financials/balance-sheets` | `thscode` | API Key | [文档](https://fuyao.aicubes.cn/docs/api-reference/fund-financials/) |
| 基金持有人结构 | `/api/fund/holders/detail` | `thscode` | API Key | [文档](https://fuyao.aicubes.cn/docs/api-reference/fund-holders/) |
| 基金前十大持有人 | `/api/fund/holders/top` | `thscode` | API Key | [文档](https://fuyao.aicubes.cn/docs/api-reference/fund-holders/) |
| 基金重仓持仓 | `/api/fund/portfolio/holdings` | `thscode` | API Key | [文档](https://fuyao.aicubes.cn/docs/api-reference/fund-holdings/) |
| 投资风格 | `/api/fund/managers/investment-style` | `manager_id` | API Key | [文档](https://fuyao.aicubes.cn/docs/api-reference/fund-managers/) |
| 基金经理业绩 | `/api/fund/managers/performance` | `manager_id`, `range` | API Key | [文档](https://fuyao.aicubes.cn/docs/api-reference/fund-managers/) |
| 从业经历 | `/api/fund/managers/experience` | `manager_id` | API Key | [文档](https://fuyao.aicubes.cn/docs/api-reference/fund-managers/) |
| 基金经理详情 | `/api/fund/managers/detail` | `manager_id` | API Key | [文档](https://fuyao.aicubes.cn/docs/api-reference/fund-managers/) |
| 场内基金行情快照 | `/api/fund/market/snapshot` | `thscode` | API Key | [文档](https://fuyao.aicubes.cn/docs/api-reference/fund-market/) |
| 场内基金历史日线行情 | `/api/fund/market/historical` | `thscode`, `start`, `end` | API Key | [文档](https://fuyao.aicubes.cn/docs/api-reference/fund-market/) |
| 场内基金批量历史日线行情 | `/api/fund/market/historical-batch` | `thscodes`, `start`, `end` | API Key | [文档](https://fuyao.aicubes.cn/docs/api-reference/fund-market/) |
| 基金资讯列表 | `/api/fund/news/article-list` | `thscode` | API Key | [文档](https://fuyao.aicubes.cn/docs/api-reference/fund-news/) |
| 基金募集列表 | `/api/fund/offerings/list` | `subscribe` | API Key | [文档](https://fuyao.aicubes.cn/docs/api-reference/fund-offerings/) |
| 基金净值 | `/api/fund/performance/nav` | `thscode` | API Key | [文档](https://fuyao.aicubes.cn/docs/api-reference/fund-performance/) |
| 基金区间收益 | `/api/fund/performance/returns` | `thscode` | API Key | [文档](https://fuyao.aicubes.cn/docs/api-reference/fund-performance/) |
| 基金历史业绩指标 | `/api/fund/performance/indicators-historical` | `thscode`, `start`, `end` | API Key | [文档](https://fuyao.aicubes.cn/docs/api-reference/fund-performance/) |
| 基金最大回撤 | `/api/fund/performance/drawdowns` | `thscode` | API Key | [文档](https://fuyao.aicubes.cn/docs/api-reference/fund-performance/) |
| 基金历史股票持仓 | `/api/fund/portfolio/stock-history` | `thscode`, `report_type`, `end_date` | API Key | [文档](https://fuyao.aicubes.cn/docs/api-reference/fund-portfolio/) |
| 基金历史债券持仓 | `/api/fund/portfolio/bond-history` | `thscode`, `report_type`, `end_date` | API Key | [文档](https://fuyao.aicubes.cn/docs/api-reference/fund-portfolio/) |
| 基金股票持仓报告日期 | `/api/fund/portfolio/stock-report-dates` | `thscode` | API Key | [文档](https://fuyao.aicubes.cn/docs/api-reference/fund-portfolio/) |
| 基金债券持仓报告日期 | `/api/fund/portfolio/bond-report-dates` | `thscode` | API Key | [文档](https://fuyao.aicubes.cn/docs/api-reference/fund-portfolio/) |
| 基金资产配置 | `/api/fund/portfolio/asset-allocation` | `thscode` | API Key | [文档](https://fuyao.aicubes.cn/docs/api-reference/fund-portfolio/) |
| 基金行业配置 | `/api/fund/portfolio/industry-allocation` | `thscode` | API Key | [文档](https://fuyao.aicubes.cn/docs/api-reference/fund-portfolio/) |
| 基金基本资料 | `/api/fund/profile/detail` | `thscode` | API Key | [文档](https://fuyao.aicubes.cn/docs/api-reference/fund-profile/) |
| QDII额度汇总 | `/api/fund/quota/summary` | `tab` | API Key | [文档](https://fuyao.aicubes.cn/docs/api-reference/fund-quota/) |
| QDII额度列表 | `/api/fund/quota/list` | `tab` | API Key | [文档](https://fuyao.aicubes.cn/docs/api-reference/fund-quota/) |
| 期货主连最新基差 | `/api/futures/basis/main-continuous-latest` | - | API Key | [文档](https://fuyao.aicubes.cn/docs/api-reference/futures-basis/) |
| 期货历史基差 | `/api/futures/basis/historical` | `thscode` | API Key | [文档](https://fuyao.aicubes.cn/docs/api-reference/futures-basis/) |
| 期货交易日 | `/api/futures/calendar/trading-schedule` | `thscode`, `start_date`, `end_date` | API Key | [文档](https://fuyao.aicubes.cn/docs/api-reference/futures-calendar/) |
| 期货主连资料 | `/api/futures/contracts/main-continuous-list` | - | API Key | [文档](https://fuyao.aicubes.cn/docs/api-reference/futures-contracts-extended/) |
| 期货主力合约 | `/api/futures/contracts/main-list` | - | API Key | [文档](https://fuyao.aicubes.cn/docs/api-reference/futures-contracts-extended/) |
| 期货次主力合约 | `/api/futures/contracts/secondary-main-list` | - | API Key | [文档](https://fuyao.aicubes.cn/docs/api-reference/futures-contracts-extended/) |
| 商品指数合约列表 | `/api/futures/contracts/commodity-index-list` | - | API Key | [文档](https://fuyao.aicubes.cn/docs/api-reference/futures-contracts-extended/) |
| 期货F10基本面指标历史数据 | `/api/futures/fundamentals/indicators-historical` | `indicator_ids`, `start_date`, `end_date` | 仅客户端 | [文档](https://fuyao.aicubes.cn/docs/api-reference/futures-fundamentals/) |
| 期货品种日持仓 | `/api/futures/positions/variety-daily` | `date` | API Key | [文档](https://fuyao.aicubes.cn/docs/api-reference/futures-positions/) |
| 期货公司品种日持仓 | `/api/futures/positions/company-variety-daily` | `date`, `varieties` | API Key | [文档](https://fuyao.aicubes.cn/docs/api-reference/futures-positions/) |
| 期货公司合约日持仓 | `/api/futures/positions/contract-daily` | `thscode`, `variety`, `date` | API Key | [文档](https://fuyao.aicubes.cn/docs/api-reference/futures-positions/) |
| 期货公司合约历史持仓 | `/api/futures/positions/contract-historical` | `thscode`, `variety`, `company`, `start_date` | API Key | [文档](https://fuyao.aicubes.cn/docs/api-reference/futures-positions/) |
| 期货公司列表 | `/api/futures/positions/company-list` | - | API Key | [文档](https://fuyao.aicubes.cn/docs/api-reference/futures-positions/) |
| 期货分时 | `/api/futures/prices/intraday` | `thscode` | API Key | [文档](https://fuyao.aicubes.cn/docs/api-reference/futures-prices/) |
| 期货K线 | `/api/futures/prices/daily` | `thscode` | API Key | [文档](https://fuyao.aicubes.cn/docs/api-reference/futures-prices/) |
| 期货合约详情 | `/api/futures/contracts/detail` | `thscode` | API Key | [文档](https://fuyao.aicubes.cn/docs/api-reference/futures-reference/) |
| 期货合约基础信息列表 | `/api/futures/contracts/list` | - | API Key | [文档](https://fuyao.aicubes.cn/docs/api-reference/futures-reference/) |
| 期货交易时间轴 | `/api/futures/calendar/session-timeline` | `thscode` | API Key | [文档](https://fuyao.aicubes.cn/docs/api-reference/futures-session-timeline/) |
| 期货品种资料 | `/api/futures/varieties/list` | - | API Key | [文档](https://fuyao.aicubes.cn/docs/api-reference/futures-varieties/) |
| 期货品种板块 | `/api/futures/variety-plates/list` | - | API Key | [文档](https://fuyao.aicubes.cn/docs/api-reference/futures-variety-plates/) |
| 期货历史仓单 | `/api/futures/warehouse-receipts/historical` | `thscode`, `start_date`, `end_date` | API Key | [文档](https://fuyao.aicubes.cn/docs/api-reference/futures-warehouse-receipts/) |
| 高频历史 | `/api/a-share/high-frequency/historical` | `thscode`, `start`, `end` | 仅客户端 | [文档](https://fuyao.aicubes.cn/docs/api-reference/high-frequency/) |
| 单日高频分时 | `/api/a-share/high-frequency/intraday` | `thscode` | 仅客户端 | [文档](https://fuyao.aicubes.cn/docs/api-reference/high-frequency/) |
| 港股新股递表记录 | `/api/hk-share/ipo/application-list` | - | API Key | [文档](https://fuyao.aicubes.cn/docs/api-reference/hk-share-ipo/) |
| 港股认购与待上市日历 | `/api/hk-share/ipo/calendar-list` | `status` | API Key | [文档](https://fuyao.aicubes.cn/docs/api-reference/hk-share-ipo/) |
| 港股新股发行详情 | `/api/hk-share/ipo/issue-detail` | `issue_code` | API Key | [文档](https://fuyao.aicubes.cn/docs/api-reference/hk-share-ipo/) |
| 飙升榜 | `/api/a-share/special-data/skyrocket-list` | - | API Key | [文档](https://fuyao.aicubes.cn/docs/api-reference/hot-list-data/) |
| A股热股榜单 | `/api/a-share/special-data/hot-stock-list` | - | API Key | [文档](https://fuyao.aicubes.cn/docs/api-reference/hot-list-data/) |
| 历史热股排行 | `/api/a-share/special-data/hot-stock-list-history` | `date` | API Key | [文档](https://fuyao.aicubes.cn/docs/api-reference/hot-list-data/) |
| 个股排名走势 | `/api/a-share/special-data/hot-stock-rank-trend` | `thscode`, `start_date`, `end_date` | API Key | [文档](https://fuyao.aicubes.cn/docs/api-reference/hot-list-data/) |
| 涨停股票池 | `/api/a-share/special-data/limit-up-pool` | - | API Key | [文档](https://fuyao.aicubes.cn/docs/api-reference/limit-up-data/) |
| 跌停股票池 | `/api/a-share/special-data/limit-down-pool` | - | API Key | [文档](https://fuyao.aicubes.cn/docs/api-reference/limit-up-data/) |
| 炸板股票池 | `/api/a-share/special-data/limit-break-pool` | - | API Key | [文档](https://fuyao.aicubes.cn/docs/api-reference/limit-up-data/) |
| 连板天梯 | `/api/a-share/special-data/limit-up-ladder` | - | API Key | [文档](https://fuyao.aicubes.cn/docs/api-reference/limit-up-data/) |
| 涨停强度与晋级统计 | `/api/a-share/special-data/limit-up-statistics` | - | API Key | [文档](https://fuyao.aicubes.cn/docs/api-reference/limit-up-statistics/) |
| 同花顺新增概念 | `/api/a-share-index/baseinfo/new-concepts` | - | 仅客户端 | [文档](https://fuyao.aicubes.cn/docs/api-reference/new-concepts/) |
| 日期范围异动解读 | `/api/news/anomaly/analysis` | `begin_date`, `end_date` | API Key | [文档](https://fuyao.aicubes.cn/docs/api-reference/news-anomaly-analysis/) |
| 资讯详情 | `/api/news/article/detail` | `client_type`, `encoded_seq` | API Key | [文档](https://fuyao.aicubes.cn/docs/api-reference/news-article-detail/) |
| 资讯事件库 | `/api/news/events/search` | - | 仅客户端 | [文档](https://fuyao.aicubes.cn/docs/api-reference/news-events/) |
| 快讯列表 | `/api/news/flash/list` | `tag_id`, `seq` | API Key | [文档](https://fuyao.aicubes.cn/docs/api-reference/news-flash/) |
| 快讯刷新 | `/api/news/flash/refresh` | `tag_id`, `seq`, `create_time_ms` | API Key | [文档](https://fuyao.aicubes.cn/docs/api-reference/news-flash/) |
| 公告详情与解读 | `/api/news/notice/detail` | `seq` | API Key | [文档](https://fuyao.aicubes.cn/docs/api-reference/news-notice-detail/) |
| 个股分时新闻 | `/api/news/stock/timeline-list` | `thscode`, `offset` | API Key | [文档](https://fuyao.aicubes.cn/docs/api-reference/news-stock-timeline/) |
| 热门深度专题 | `/api/news/topic/hot-list` | `tab_id` | API Key | [文档](https://fuyao.aicubes.cn/docs/api-reference/news-topics/) |
| 期权分时 | `/api/options/prices/intraday` | `thscode` | API Key | [文档](https://fuyao.aicubes.cn/docs/api-reference/options-prices/) |
| 期权K线 | `/api/options/prices/daily` | `thscode` | API Key | [文档](https://fuyao.aicubes.cn/docs/api-reference/options-prices/) |
| 期权合约详情 | `/api/options/contracts/detail` | `thscode` | API Key | [文档](https://fuyao.aicubes.cn/docs/api-reference/options-reference/) |
| 期权合约基础信息列表 | `/api/options/contracts/list` | - | API Key | [文档](https://fuyao.aicubes.cn/docs/api-reference/options-reference/) |
| 期权交易时间轴 | `/api/options/calendar/session-timeline` | `thscode` | API Key | [文档](https://fuyao.aicubes.cn/docs/api-reference/options-session-timeline/) |
| 期权品种资料 | `/api/options/varieties/list` | - | API Key | [文档](https://fuyao.aicubes.cn/docs/api-reference/options-varieties/) |
| 市场成交额预测 | `/api/a-share/special-data/turnover-prediction-snapshot` | - | 仅客户端 | [文档](https://fuyao.aicubes.cn/docs/api-reference/turnover-prediction/) |

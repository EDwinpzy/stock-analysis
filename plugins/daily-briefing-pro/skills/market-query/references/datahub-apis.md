# DataHub 行情接口清单

共 118 个 GET 契约，来源于本机 Lumi 1.0.69 的 DataHub 快照。

运行探测时间：`11/05/2026 06:47:34`。

| 运行状态 | 接口数 |
|---|---:|
| document_example_rejected | 2 |
| permission_denied | 2 |
| skipped_sensitive_dump | 3 |
| upstream_unavailable | 2 |
| verified_success | 109 |

| 分类 | 接口数 |
|---|---:|
| a-share | 40 |
| fund | 33 |
| futures | 21 |
| hk-share | 3 |
| index | 5 |
| meta | 2 |
| news | 8 |
| options | 6 |

## a-share

### 利润表

`GET /api/a-share/financials/income-statements`

A 股整体合并利润表多期序列。取数模式与参数见上文。

**运行验证**：`verified_success`，`code=0`，success

**请求参数**

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|---|---|---|---|---|
| thscode | string | 是 | — | 单只标的 thscode，不接受逗号；含交易所后缀。 |
| period | enum | 是 | annual | annual（仅 Q4 报告期）/ quarterly（每个季度末）。 |
| limit | integer | 否 | 4 | 最近 N 期模式，范围 [1, 20]；与 start / end 互斥。 |
| start | long | 否 | — | 时间区间模式起始毫秒戳，需与 end 同传。 |
| end | long | 否 | — | 时间区间模式结束毫秒戳，需满足 end >= start。 |

**主要响应字段**

| 字段 | 类型 | 说明 |
|---|---|---|
| operating_income | number | 营业收入（原币元）。 |
| operating_costs | number | 营业成本（原币元）。 |
| operating_expenses | number | 营业总成本（原币元）。 |
| sales_fee | number | 销售费用（原币元）。 |
| manage_fee | number | 管理费用（原币元）。 |
| research_and_development_expenses | number | 研发费用（原币元）。 |
| operating_profit | number | 营业利润（原币元）。 |
| interest_expenses | number | 利息费用（原币元）。 |
| profit_total | number | 利润总额（原币元）。 |
| income_tax_expense | number | 所得税费用（原币元）。 |
| net_profit | number | 净利润（原币元）。 |
| parent_holder_net_profit | number | 归属于母公司股东的净利润（原币元）。 |
| basic_eps | number | 基本每股收益（元/股）。 |

示例：`https://datahub.10jqka.com.cn/api/a-share/financials/income-statements?thscode=600519.SH&period=annual&limit=3`

<details>
<summary>响应示例</summary>

```json
{
  "code": 0,
  "message": "success",
  "request_id": "e5f6g7h8",
  "data": {
    "timestamp": 1735574400000,
    "item": [
      {
        "thscode": "600519.SH",
        "ticker": "600519",
        "period": "annual",
        "fiscal_year": 2024,
        "fiscal_period": "FY",
        "report_date_ms": 1735574400000,
        "period_end_ms": 1735574400000,
        "currency": "CNY",
        "operating_income": 174144000000,
        "operating_costs": 13000000000,
        "operating_expenses": 50000000000,
        "sales_fee": 5000000000,
        "manage_fee": 9000000000,
        "research_and_development_expenses": 150000000,
        "operating_profit": 124000000000,
        "interest_expenses": 0,
        "profit_total": 124000000000,
        "income_tax_expense": 31000000000,
        "net_profit": 93000000000,
        "parent_holder_net_profit": 86000000000,
        "basic_eps": 68.50
      }
    ]
  }
}
```

</details>
<!-- end -->
### 现金流量表

`GET /api/a-share/financials/cash-flow-statements`

A 股整体合并现金流量表多期序列。取数模式与参数同利润表。

**运行验证**：`verified_success`，`code=0`，success

**请求参数**

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|---|---|---|---|---|
| thscode | string | 是 | — | 单只标的 thscode，不接受逗号；含交易所后缀。 |
| period | enum | 是 | annual | annual（仅 Q4 报告期）/ quarterly（每个季度末）。 |
| limit | integer | 否 | 4 | 最近 N 期模式，范围 [1, 20]；与 start / end 互斥。 |
| start | long | 否 | — | 时间区间模式起始毫秒戳，需与 end 同传。 |
| end | long | 否 | — | 时间区间模式结束毫秒戳，需满足 end >= start。 |

**主要响应字段**

| 字段 | 类型 | 说明 |
|---|---|---|
| act_cash_flow_net | number | 经营活动产生的现金流量净额（原币元）。 |
| invest_cash_flow_net | number | 投资活动产生的现金流量净额（原币元）。 |
| financing_cash_flow_net | number | 筹资活动产生的现金流量净额（原币元）。 |
| pay_fixed_assets_etc_cash | number | 购建固定资产、无形资产和其他长期资产支付的现金（原币元）。 |
| pay_dividends_profits_interest_cash | number | 分配股利、利润或偿付利息支付的现金（原币元）。 |
| cash_equivalents_net_addition | number | 现金及现金等价物净增加额（原币元）。 |

示例：`https://datahub.10jqka.com.cn/api/a-share/financials/cash-flow-statements?thscode=600519.SH&period=annual&start=1577808000000&end=1735574400000`

<details>
<summary>响应示例</summary>

```json
{
  "code": 0,
  "message": "success",
  "request_id": "g7h8i9j0",
  "data": {
    "timestamp": 1735574400000,
    "item": [
      {
        "thscode": "600519.SH",
        "ticker": "600519",
        "period": "annual",
        "fiscal_year": 2024,
        "fiscal_period": "FY",
        "report_date_ms": 1735574400000,
        "period_end_ms": 1735574400000,
        "currency": "CNY",
        "act_cash_flow_net": 92000000000,
        "invest_cash_flow_net": -3000000000,
        "financing_cash_flow_net": -65000000000,
        "pay_fixed_assets_etc_cash": 3500000000,
        "pay_dividends_profits_interest_cash": 64000000000,
        "cash_equivalents_net_addition": 24000000000
      }
    ]
  }
}
```

</details>

### 资产负债表

`GET /api/a-share/financials/balance-sheets`

A 股整体合并资产负债表多期序列。取数模式与参数同利润表。

**运行验证**：`verified_success`，`code=0`，success

**请求参数**

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|---|---|---|---|---|
| thscode | string | 是 | — | 单只标的 thscode，不接受逗号；含交易所后缀。 |
| period | enum | 是 | annual | annual（仅 Q4 报告期）/ quarterly（每个季度末）。 |
| limit | integer | 否 | 4 | 最近 N 期模式，范围 [1, 20]；与 start / end 互斥。 |
| start | long | 否 | — | 时间区间模式起始毫秒戳，需与 end 同传。 |
| end | long | 否 | — | 时间区间模式结束毫秒戳，需满足 end >= start。 |

**主要响应字段**

| 字段 | 类型 | 说明 |
|---|---|---|
| assets_total | number | 资产总计（原币元）。 |
| total_current_assets | number | 流动资产合计（原币元）。 |
| non_current_nets_total | number | 非流动资产合计（原币元）。 |
| cash | number | 货币资金（原币元）。 |
| accounts_receivable | number | 应收账款（原币元）。 |
| total_debt | number | 负债合计（原币元）。 |
| holder_equity_total | number | 所有者权益（股东权益）合计（原币元）。 |

示例：`https://datahub.10jqka.com.cn/api/a-share/financials/balance-sheets?thscode=000858.SZ&period=quarterly`

<details>
<summary>响应示例</summary>

```json
{
  "code": 0,
  "message": "success",
  "request_id": "f6g7h8i9",
  "data": {
    "timestamp": 1735574400000,
    "item": [
      {
        "thscode": "000858.SZ",
        "ticker": "000858",
        "period": "quarterly",
        "fiscal_year": 2024,
        "fiscal_period": "Q4",
        "report_date_ms": 1735574400000,
        "period_end_ms": 1735574400000,
        "currency": "CNY",
        "assets_total": 250000000000,
        "total_current_assets": 200000000000,
        "non_current_nets_total": 50000000000,
        "cash": 130000000000,
        "accounts_receivable": 500000000,
        "total_debt": 60000000000,
        "holder_equity_total": 190000000000
      }
    ]
  }
}
```

</details>

### 财务指标数据

`GET /api/a-share/financials/indicators`

财务指标数据模块返回单只 A 股在指定报告期下的五类指标数据。接口返回统一响应信封ApiResponse，业务错误经 code 字段表达，HTTP 状态码恒为 200。

**运行验证**：`verified_success`，`code=0`，success

**请求参数**

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|---|---|---|---|---|
| thscode | string | 是 | — | 单只标的 thscode，含交易所后缀，如 300033.SZ。 |
| report | string | 是 | — | 报告期，示例 2025-1；格式见上方通用约定。 |

**主要响应字段**

| 字段 | 类型 | 说明 |
|---|---|---|
| code | integer | 业务状态码，0 表示成功。 |
| message | string | 业务状态说明。 |
| request_id | string | 请求追踪 ID。 |
| data.thscode | string | 入参 thscode 回显。 |
| data.report | string | 入参 report 回显。 |
| data.abilities[] | array | 五类能力块，固定顺序为 growth、profitability、solvency、operation、cash-flow。 |
| data.abilities[].ability | string | 能力标识。 |
| data.abilities[].indicators[] | array | 当前能力下的指标列表。 |
| data.abilities[].indicators[].index_id | string | 指标 ID，取值见下方表格。 |
| data.abilities[].indicators[].value | string \| null | 本期指标值。服务端保留数据源原始数值字符串，不承诺固定小数位；上游空值或缺失值标准化为 null。百分比类指标按百分数值表达，例如 89.12000000 表示 89.12%；周转率、比率、倍数类指标按指标名称对应单位解释。 |

示例：`https://datahub.10jqka.com.cn/api/a-share/financials/indicators?thscode=300033.SZ&report=2025-1`

<details>
<summary>响应示例</summary>

```json
{
  "code": 0,
  "message": "success",
  "request_id": "a1b2c3d4e5f6789012345678abcdef01",
  "data": {
    "thscode": "300033.SZ",
    "report": "2025-1",
    "abilities": [
      {
        "ability": "growth",
        "indicators": [
          {
            "index_id": "total_assets_growth_ratio",
            "value": "-16.0031"
          }
        ]
      },
      {
        "ability": "profitability",
        "indicators": [
          {
            "index_id": "sale_gross_margin",
            "value": "89.12000000"
          },
          {
            "index_id": "earned_interest_multiple",
            "value": null
          }
        ]
      }
    ]
  }
}
```

</details>

### 复权因子事件流

`GET /api/a-share/corporate-actions/adjustment-factors`

获取单只标的的 A 股复权因子事件流。**每次请求仅一个 thscode**。

**运行验证**：`verified_success`，`code=0`，success

**请求参数**

| 参数 | 位置 | 类型 | 必需 | 说明 | 默认值 |
|---|---|---|---|---|---|
| thscode | query | string | 是 | 单只标的 thscode，**不接受逗号**。 | - |
| from | query | string | 否 | 事件起始日，格式 YYYY-MM-DD。 | - |
| to | query | string | 否 | 事件截止日，格式 YYYY-MM-DD。 | - |

**主要响应字段**

| 字段 | 类型 | 说明 |
|---|---|---|
| thscode | string | 带交易所后缀的完整 thscode（与 item 同级，标识本次返回所属标的）。 |
| ticker | string | 纯代码（无交易所后缀）。 |
| item | array | 事件列表，按 ex_date_ms 降序排列（最新在前）。 |
| ticker | string | 纯代码（无交易所后缀），如 600519。 |
| ex_date_ms | long | 除权除息日，Asia/Shanghai 00:00:00 毫秒 Unix 时间戳。 |
| dividend_per_share | number | 每股现金分红（税前，原始货币）。非现金事件为 0。 |
| per_share_bonus | number | 每股送股比例（如 0.1 表示 10 送 1）。纯现金分红事件为 0。 |

示例：`https://datahub.10jqka.com.cn/api/a-share/corporate-actions/adjustment-factors?thscode=600519.SH`

<details>
<summary>响应示例</summary>

```json
{
  "code": 0,
  "message": "success",
  "request_id": "558c1d59d2e548149fb27b83eca5016a",
  "data": {
    "thscode": "600519.SH",
    "ticker": "600519",
    "item": [
      {
        "ticker": "600519",
        "ex_date_ms": 1766073600000,
        "dividend_per_share": 23.957,
        "per_share_bonus": 0
      },
      {
        "ticker": "600519",
        "ex_date_ms": 1437062400000,
        "dividend_per_share": 4.374,
        "per_share_bonus": 0.1
      }
    ]
  }
}
```

</details>

### 单日高频分时

`GET /api/a-share/high-frequency/intraday`

查询单只 A 股个股或指数在一个交易日内已经产生的高频动向点。省略日期时使用当前窗口中的最近交易日。

**运行验证**：`permission_denied`，`code=2003`，Permission denied（使用替代有效样例）

**请求参数**

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|---|---|---|---|---|
| thscode | string | 是 | — | 单只 A 股个股或指数的完整代码；不支持批量、纯代码或其他资产类型。 |
| date | string | 否 | 最近交易日 | 指定交易日，格式为 YYYY-MM-DD，且必须位于当前最近 30 个 A 股交易日内。 |

**主要响应字段**

| 字段 | 类型 | 说明 |
|---|---|---|
| timestamp | long \| null | 返回序列最后一个数据点的时间；无数据时为 null。 |
| thscode | string | 请求的完整 A 股个股或指数代码。 |
| interval | string | 固定为 trend。 |
| item | array | 按 date_ms 升序排列的当日高频动向点；无数据时为空数组。 |
| date_ms | long | 当前数据点的毫秒级 Unix 时间戳。 |
| hf_direction | number \| null | 高频动向原值；保留原始精度，可能为 null。 |

示例：`https://datahub.10jqka.com.cn/api/a-share/high-frequency/intraday?thscode=886042.TI&date=2026-09-09`

<details>
<summary>响应示例</summary>

```json
{
  "code": 0,
  "message": "success",
  "request_id": "7db85bfddf5146f49034f42db6282188",
  "data": {
    "timestamp": 1788917400000,
    "thscode": "886042.TI",
    "interval": "trend",
    "item": [
      {
        "date_ms": 1788917400000,
        "hf_direction": -0.03125
      }
    ]
  }
}
```

</details>

### 高频历史

`GET /api/a-share/high-frequency/historical`

查询单只 A 股个股或指数的日线或 1 分钟高频动向。日线包含高频动向；A 股个股日线同时包含高频参与度，指数日线的高频参与度为 null。1 分钟序列仅包含高频动向。

**运行验证**：`permission_denied`，`code=2003`，Permission denied（使用替代有效样例）

**请求参数**

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|---|---|---|---|---|
| thscode | string | 是 | — | 单只 A 股个股或指数的完整代码；不支持批量、纯代码或其他资产类型。 |
| interval | enum | 否 | 1d | 1d（日线）或 1m（1 分钟）。 |
| start | long | 是 | — | 起始时间，正毫秒级 Unix 时间戳。日线必须为东八区交易日零点；分钟线必须与 end 处于同一交易日。 |
| end | long | 是 | — | 结束时间，正毫秒级 Unix 时间戳且不早于 start。日期必须位于当前最近 30 个 A 股交易日内。 |

**主要响应字段**

| 字段 | 类型 | 说明 |
|---|---|---|
| timestamp | long \| null | 返回序列最后一个数据点的时间；无数据时为 null。 |
| thscode | string | 请求的完整 A 股个股或指数代码。 |
| interval | string | 返回周期，值为 1d 或 1m。 |
| item | array | 按 date_ms 升序排列的数据点；无数据时为空数组。 |
| date_ms | long | 当前数据点的毫秒级 Unix 时间戳。 |
| hf_direction | number \| null | 高频动向原值；保留原始精度，可能为 null。 |
| hf_participation | number \| null | 高频参与度原值，仅日线返回；A 股指数日线为 null，1 分钟数据不返回该字段。 |

示例：`https://datahub.10jqka.com.cn/api/a-share/high-frequency/historical?thscode=600519.SH&interval=1d&start=1788883200000&end=1788883200000`

<details>
<summary>响应示例</summary>

```json
{
  "code": 0,
  "message": "success",
  "request_id": "1f3d1b77d43d4dd2a8fc749619e86788",
  "data": {
    "timestamp": 1788883200000,
    "thscode": "600519.SH",
    "interval": "1d",
    "item": [
      {
        "date_ms": 1788883200000,
        "hf_direction": 0.1234567890123456789,
        "hf_participation": 0.4567890123456789012
      }
    ]
  }
}
```

</details>

### 个股机构交易详情

`GET /api/a-share/special-data/dragon-tiger-stock-institution`

按股票和交易日查询机构买入、卖出、净买入金额，以及机构数量、比例和营业部身份。同一股票的一日与三日上榜区间分别保留；省略区间参数时返回实际记录。

**运行验证**：`verified_success`，`code=0`，success

**请求参数**

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|---|---|---|---|---|
| thscode | string | 是 | — | 单个A股标准代码 |
| date | string | 否 | — | 查询日期，YYYY-MM-DD；默认日期与有效范围见接口说明；省略使用最近已完成交易日，查询范围为一年 |
| range_days | integer | 否 | — | 上榜区间，1或3；省略返回两类实际记录 |

**主要响应字段**

| 字段 | 类型 | 说明 |
|---|---|---|
| thscode | string | 股票标识 |
| trade_date | date | 查询日 |
| item | array | 业务记录列表 |
| range_days | integer | 上榜统计区间 |
| start_date | date | 区间起日 |
| end_date | date | 区间末日 |
| org_buy_value | number \| null | 机构买入汇总；单位：元 |
| org_sell_value | number \| null | 机构卖出汇总；单位：元 |
| org_net_value | number \| null | 机构净买入；单位：元 |
| org_buy_num | integer \| null | 买入机构数 |
| org_sell_num | integer \| null | 卖出机构数 |
| org_net_rate | number \| null | 区间机构净买入比例；单位：小数比例 |
| buy_departments[] | array[object] | 买入席位ID与名称索引 |
| sell_departments[] | array[object] | 卖出席位ID与名称索引 |

示例：`https://datahub.10jqka.com.cn/api/a-share/special-data/dragon-tiger-stock-institution?thscode=301052.SZ&date=2026-10-12`

<details>
<summary>响应示例</summary>

```json
{
  "code": 0,
  "message": "success",
  "request_id": "example-request",
  "data": {
    "thscode": "301052.SZ",
    "trade_date": "2026-10-12",
    "item": [
      {
        "range_days": 1,
        "start_date": "2026-10-12",
        "end_date": "2026-10-12",
        "org_buy_value": 78242315.6,
        "org_sell_value": 83760760,
        "org_net_value": -5518444.4,
        "org_buy_num": 3,
        "org_sell_num": 5,
        "org_net_rate": -0.00945038,
        "buy_departments": [
          {
            "department_id": "THS59",
            "name": "机构专用"
          },
          {
            "department_id": "T000027098",
            "name": "平安证券股份有限公司浙江分公司"
          },
          {
            "department_id": "T000058048",
            "name": "平安证券股份有限公司金华李渔路证券营业部"
          },
          {
            "department_id": "THS59",
            "name": "机构专用"
          },
          {
            "department_id": "THS59",
            "name": "机构专用"
          }
        ],
        "sell_departments": [
          {
            "department_id": "THS59",
            "name": "机构专用"
          },
          {
            "department_id": "THS59",
            "name": "机构专用"
          },
          {
            "department_id": "THS59",
            "name": "机构专用"
          },
          {
            "department_id": "THS59",
            "name": "机构专用"
          },
          {
            "department_id": "THS59",
            "name": "机构专用"
          }
        ]
      },
      {
        "range_days": 3,
        "start_date": "2026-10-09",
        "end_date": "2026-10-12",
        "org_buy_value": 133230431.75,
        "org_sell_value": 107636728,
        "org_net_value": 25593703.75,
        "org_buy_num": 4,
        "org_sell_num": 5,
        "org_net_rate": 0.03327691,
        "buy_departments": [
          {
            "department_id": "THS59",
            "name": "机构专用"
          },
          {
            "department_id": "THS59",
            "name": "机构专用"
          },
          {
            "department_id": "THS59",
            "name": "机构专用"
          },
          {
            "department_id": "THS59",
            "name": "机构专用"
          },
          {
            "department_id": "T000027098",
            "name": "平安证券股份有限公司浙江分公司"
          }
        ],
        "sell_departments": [
          {
            "department_id": "THS59",
            "name": "机构专用"
          },
          {
            "department_id": "THS59",
            "name": "机构专用"
          },
          {
            "department_id": "THS59",
            "name": "机构专用"
          },
          {
            "department_id": "THS59",
            "name": "机构专用"
          },
          {
            "department_id": "THS59",
            "name": "机构专用"
          }
        ]
      }
    ]
  }
}
```

</details>

### a股估值快照

`GET /api/a-share/valuations/snapshot`

本接口提供 A 股多股票最新估值快照，用于查看股票当前价格相对于公司盈利、净资产、营业收入和经营现金流的估值水平。当前支持市盈率（PE）、市净率（PB）、市销率（PS）和市现率（PCF）四类指标，共 5 个数据字段；其中市盈率同时提供 TTM 和 MRQ 两种口径。 这些指标可用于个股基本面分析、同行业公司对比、股票筛选和估值监控。不同指标的适用范围存在差异，建议结合公司盈利状态、行业特征、财务质量及其他基本面数据综合判断。

**运行验证**：`verified_success`，`code=0`，success

**请求参数**

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|---|---|---|---|---|
| thscodes | string | 是 | — | 英文逗号分隔的 A 股 thscode 列表，如 600519.SH,000001.SZ；每项必须为六位数字加 .SH、.SZ 或 .BJ。 |

**主要响应字段**

| 字段 | 类型 | 说明 |
|---|---|---|
| code | integer | 业务状态码，0 表示成功。 |
| message | string | 业务状态说明。 |
| request_id | string | 请求追踪 ID。 |
| data.timestamp | long \| null | 本次响应所用上游指标元数据中的最大有效时间，单位为毫秒；无有效时间时为 null。 |
| data.total | integer | 实际返回的股票条数。 |
| data.item | array | 估值快照列表，按去重后的请求顺序返回。 |
| data.item[].thscode | string | 带交易所后缀的完整 thscode。 |
| data.item[].ticker | string | 六位股票代码，不含交易所后缀。 |
| data.item[].name | string \| null | 本地 A 股代码表中的股票名称。 |
| data.item[].pe_ttm | number \| null | 市盈率 TTM。 |
| data.item[].pe_mrq | number \| null | 市盈率 MRQ。 |
| data.item[].pb_mrq | number \| null | 市净率 MRQ。 |
| data.item[].ps_ttm | number \| null | 市销率 TTM。 |
| data.item[].pcf_ttm | number \| null | 市现率 TTM。 |

示例：`https://datahub.10jqka.com.cn/api/a-share/valuations/snapshot?thscodes=600519.SH,000001.SZ`

<details>
<summary>响应示例</summary>

```json
{
  "code": 0,
  "message": "success",
  "request_id": "a1b2c3d4e5f6789012345678abcdef01",
  "data": {
    "timestamp": 1784736000000,
    "total": 1,
    "item": [
      {
        "thscode": "600519.SH",
        "ticker": "600519",
        "name": "贵州茅台",
        "pe_ttm": 21.3567,
        "pe_mrq": 20.8841,
        "pb_mrq": 7.1532,
        "ps_ttm": 10.3284,
        "pcf_ttm": 19.7716
      }
    ]
  }
}
```

</details>

### 历史 K 线

`GET /api/a-share/prices/historical`

获取单只标的的 A 股历史 K 线序列。接口层强约束：**每次请求仅一个 thscode**， 且 [start, end] 窗口跨度不超过 10 年。

**运行验证**：`verified_success`，`code=0`，success

**请求参数**

| 参数 | 位置 | 类型 | 必需 | 说明 | 默认值 |
|---|---|---|---|---|---|
| thscode | query | string | 是 | 单只标的 thscode，**不接受逗号**。多标的请分多次请求。 | - |
| interval | query | string | 是 | K 线周期，**当前仅支持** 1d(日线)。 | 1d |
| start | query | long | 是 | 起始时间，毫秒 Unix 时间戳。缺失返回 code=1001。 | - |
| end | query | long | 是 | 结束时间，毫秒 Unix 时间戳。end - start 超过 10 年返回 code=1003。 | - |
| adjust | query | string | 否 | 复权方式：none / forward(前复权) / backward(后复权)。 | forward |

**主要响应字段**

| 字段 | 类型 | 说明 |
|---|---|---|
| timestamp | long | 数据就绪时间（毫秒），为序列中最新一根 K 线的上游有效时间。 |
| item | array | K 线列表。 |
| date_ms | long | K 线日期（毫秒）。 |
| open_price | number | 开盘价。 |
| high_price | number | 最高价。 |
| low_price | number | 最低价。 |
| close_price | number | 收盘价。 |
| volume | number | 成交量（股）。 |
| turnover | number | 成交额（原始货币）。 |

示例：`https://datahub.10jqka.com.cn/api/a-share/prices/historical?thscode=600519.SH&interval=1d&start=1716105600000&end=1747641600000&adjust=forward`

<details>
<summary>响应示例</summary>

```json
{
  "code": 0,
  "message": "success",
  "request_id": "b9f91af9c77a42d6b8a04738793d2fa2",
  "data": {
    "timestamp": 1747584000000,
    "item": [
      {
        "date_ms": 1716134400000,
        "open_price": 1611.602,
        "high_price": 1626.602,
        "low_price": 1601.722,
        "close_price": 1602.612,
        "volume": 3142572.0,
        "turnover": 5401389334.87
      }
    ]
  }
}
```

</details>

### 行情快照

`GET /api/a-share/prices/snapshot`

获取 A 股行情快照。thscodes 显式传入（逗号分隔）时按入参顺序批量取数、不分页； 省略时遍历完整 A 股代码表（按 thscode 升序），并按 limit / offset 分页。

**运行验证**：`verified_success`，`code=0`，success

**请求参数**

| 参数 | 位置 | 类型 | 必需 | 说明 | 默认值 |
|---|---|---|---|---|---|
| thscodes | query | string | 否 | 逗号分隔的 thscode 列表，如 600519.SH,000001.SZ。给定时忽略分页参数。 | - |
| limit | query | integer | 否 | 分页大小，仅在 thscodes 省略时生效。 | 100 |
| offset | query | integer | 否 | 分页偏移，仅在 thscodes 省略时生效。 | 0 |

**主要响应字段**

| 字段 | 类型 | 说明 |
|---|---|---|
| timestamp | long \| null | 数据就绪时间（毫秒），为本次快照中最新的上游有效时间；无有效数据时为 null。 |
| total | int | 全市场代码表总数（用于分页模式估算页数）。 |
| item | array | 快照记录列表，单条记录也以数组返回。 |
| thscode | string | 带交易所后缀的完整 thscode，如 600519.SH。 |
| ticker | string | 纯代码（无交易所后缀），如 600519。 |
| last_price | number | 最新成交价（原始货币）。 |
| price_change | number | 相对前收盘价的涨跌额（原始货币）。 |
| price_change_ratio_pct | number | 涨跌幅，单位为百分比数值（如 1.74 表示 +1.74%）。 |
| open_price | number | 当日开盘价。 |
| high_price | number | 当日最高价。 |
| low_price | number | 当日最低价。 |
| prev_price | number | 前收盘价。 |
| volume | number | 成交量（股）。 |
| turnover | number | 成交额（原始货币）。 |

示例：`https://datahub.10jqka.com.cn/api/a-share/prices/snapshot?thscodes=600519.SH,000001.SZ`

<details>
<summary>响应示例</summary>

```json
{
  "code": 0,
  "message": "success",
  "request_id": "7e25804be878464ba420037155f041e6",
  "data": {
    "timestamp": 1784275991000,
    "total": 2,
    "item": [
      {
        "thscode": "600519.SH",
        "ticker": "600519",
        "volume": 3098875,
        "turnover": 3937375200,
        "last_price": 1277.8,
        "price_change": 21.8,
        "price_change_ratio_pct": 1.735669,
        "open_price": 1252.08,
        "high_price": 1282,
        "low_price": 1250.21,
        "prev_price": 1256
      }
    ]
  }
}
```

</details>

### 集合竞价个股机会筛选

`GET /api/a-share/special-data/auction-stock-opportunities`

筛选实时或历史集合竞价机会，一个股票可包含多条机会记录。涨幅为小数比例，数量保持返回尺度；数量单位尚未定义。说明和评级保留原值，关联板块保留 JSON 或 null。

**运行验证**：`verified_success`，`code=0`，success

**请求参数**

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|---|---|---|---|---|
| date | string | 否 | — | 查询日期，YYYY-MM-DD；默认日期与有效范围见接口说明；须属于可用日期集合 |
| warn_types | string | 否 | — | 逗号分隔的机会类型码；省略查询全部；当前类型为68710/68711/68712/68713/68714/68715/68716/68717/68718/68719/68720/68721/68722/68723/68724/68725/68726/68727 |
| market | string | 否 | a_share | 适用市场：a_share/sh_sz_main/sh_a/sz_a/gem/star |
| exclude_st | boolean | 否 | false | 是否排除ST股票，默认false |
| thscodes | string | 否 | — | 逗号分隔A股标准代码，最多50个token |
| sort_by | string | 否 | warn_time | warn_time或warn_type |
| sort_order | string | 否 | desc | desc或asc |
| page | integer | 否 | 1 | 从1开始的页码 |
| size | integer | 否 | 20 | 每页1至20条，默认20 |

**主要响应字段**

| 字段 | 类型 | 说明 |
|---|---|---|
| timestamp | integer | 快照采样时间；单位：毫秒 |
| trade_date | date | 所属交易日 |
| mode | enum | real_time/history |
| item | array | 业务记录列表 |
| pagination | object | 分页对象，包含page、size、total和has_next |
| thscode | string | 标准A股标识 |
| ticker | string | 6位股票代码 |
| name | string | 股票名称 |
| warn_type | string | 原始异动类型码 |
| warn_name | string \| null | 返回类型名称；新未知类型暂null，原码保留 |
| warn_timestamp | integer | 异动发生时间；单位：毫秒 |
| bid_price | number \| null | 匹配价；单位：元 |
| bid_change_ratio | number \| null | 竞价涨幅；单位：小数比例 |
| bid_amount | number \| null | 竞价金额；单位：元 |
| previous_amount | number \| null | 昨日成交额；单位：元 |
| bid_volume | number \| null | 竞价量，按返回尺度提供；数量单位尚未定义 |
| previous_volume | number \| null | 昨日成交量，按返回尺度提供；数量单位尚未定义 |
| explain | string \| null | 异动说明原值，例如代码字符串1.0 |
| grade | string \| null | 评级原值 |
| related_block | json \| null | 关联板块的JSON原值，可为null；非空结构按实际返回值 |

示例：`https://datahub.10jqka.com.cn/api/a-share/special-data/auction-stock-opportunities?date=2026-10-12&warn_types=68710&page=1&size=20`

<details>
<summary>响应示例</summary>

```json
{
  "code": 0,
  "message": "success",
  "request_id": "example-request",
  "data": {
    "timestamp": 1791957420099,
    "trade_date": "2026-10-12",
    "mode": "history",
    "item": [
      {
        "thscode": "603190.SH",
        "ticker": "603190",
        "name": "亚通精工",
        "warn_type": "68710",
        "warn_name": "涨停试盘",
        "warn_timestamp": 1791767895000,
        "bid_price": 16.03,
        "bid_change_ratio": 0,
        "bid_amount": 137858,
        "previous_amount": 29087826,
        "bid_volume": 8600,
        "previous_volume": 1847020,
        "explain": "1.0",
        "grade": null,
        "related_block": null
      }
    ],
    "pagination": {
      "page": 1,
      "size": 20,
      "total": 33,
      "has_next": true
    }
  }
}
```

</details>

### 集合竞价可选交易日期

`GET /api/a-share/special-data/auction-opportunity-dates`

查询集合竞价可用交易日期。日期按升序返回，实际保留范围由日期集合决定。

**运行验证**：`verified_success`，`code=0`，success

**请求参数**

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|---|---|---|---|---|
| — | — | 否 | — | 无业务参数。 |

**主要响应字段**

| 字段 | 类型 | 说明 |
|---|---|---|
| timestamp | integer | 采样时间；单位：毫秒 |
| source_updated_at | integer \| null | 业务数据源更新时间；单位：毫秒 |
| dates | array[date] | 返回可用日期，升序 |
| latest_date | date | 默认历史查询日期 |

示例：`https://datahub.10jqka.com.cn/api/a-share/special-data/auction-opportunity-dates`

<details>
<summary>响应示例</summary>

```json
{
  "code": 0,
  "message": "success",
  "request_id": "example-request",
  "data": {
    "timestamp": 1791957420098,
    "source_updated_at": 1791893766000,
    "dates": [
      "2025-10-13",
      "2026-10-13"
    ],
    "latest_date": "2026-10-13"
  }
}
```

</details>

### 短线风向标竞价基准

`GET /api/a-share/auction/short-term-benchmark`

集合竞价接口返回统一 ApiResponse 信封。thscode 使用带交易所后缀的标准代码，时间戳均为毫秒级 Unix 时间戳。

**运行验证**：`verified_success`，`code=0`，success

**请求参数**

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|---|---|---|---|---|
| date | string | 否 | 上海时区当日 | 查询日期，格式 yyyy-MM-dd；缺失或传入空字符串时使用 Asia/Shanghai 当日，显式指定非交易日时不自动回退。 |

**主要响应字段**

| 字段 | 类型 | 说明 |
|---|---|---|
| timestamp | long | 接口响应组装时间，毫秒 Unix 时间戳。 |
| date | string | 最终查询日期，格式 yyyy-MM-dd。 |
| date_ms | long | 最终查询日期在 Asia/Shanghai 当日零点的毫秒 Unix 时间戳。 |
| item | array | 短线风向标竞价基准明细。 |
| thscode | string | 完整 A 股 thscode。 |
| ticker | string | 纯股票代码。 |
| name | string | 股票简称。 |
| auction_pct | number | 集合竞价涨跌幅，百分数原值。 |
| tags | array | 短线风向标标签。 |

示例：`https://datahub.10jqka.com.cn/api/a-share/auction/short-term-benchmark?date=2026-08-14`

<details>
<summary>响应示例</summary>

```json
{
  "code": 0,
  "message": "success",
  "request_id": "4e2f1c8c38e54ff1be9be3d17533bef9",
  "data": {
    "timestamp": 1786690800000,
    "date": "2026-08-14",
    "date_ms": 1786636800000,
    "item": [
      {
        "thscode": "600519.SH",
        "ticker": "600519",
        "name": "贵州茅台",
        "auction_pct": 0.35,
        "tags": [
          "高开",
          "放量"
        ]
      }
    ]
  }
}
```

</details>

### A股集合竞价快照

`GET /api/a-share/auction/snapshot`

集合竞价接口返回统一 ApiResponse 信封。thscode 使用带交易所后缀的标准代码，时间戳均为毫秒级 Unix 时间戳。

**运行验证**：`verified_success`，`code=0`，success

**请求参数**

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|---|---|---|---|---|
| thscodes | string | 是 | — | 一个或多个 A 股 thscode，使用英文逗号分隔；单次请求当前最多 100 个，按分隔后的原始 token 数在去重前校验。服务端按请求顺序去重返回。 |
| stage | enum | 否 | final | live（实时阶段）或 final（终态）。 |

**主要响应字段**

| 字段 | 类型 | 说明 |
|---|---|---|
| data.timestamp | long | 接口响应组装时间，毫秒 Unix 时间戳；实时、终态、停牌及 not_ready 场景均会返回。上游竞价行情时间仅用于判断数据新鲜度。 |
| data.auction_phase | string | 集合竞价阶段。 |
| data.data_status | string | 数据状态。 |
| data.total | integer | 返回标的数量。 |
| data.item | array | 集合竞价明细列表。 |
| thscode / ticker / name | string | 标准代码、纯代码与股票简称。 |
| auction_price / auction_pct | number | 竞价价格与竞价涨跌幅百分数原值。 |
| auction_volume / auction_amount / auction_unmatched | number | 竞价成交量、成交额与未匹配量。 |
| auction_turnover_pct / auction_yesterday_ratio_pct / auction_volume_ratio | number | 竞价换手率、相对昨日成交量比例与竞价量比。 |
| pre_close_price / open_price / last_price | number | 前收盘价、开盘价与最新价。 |
| float_market_cap | number | 流通市值。 |

示例：`https://datahub.10jqka.com.cn/api/a-share/auction/snapshot?thscodes=600519.SH,000001.SZ&stage=final`

<details>
<summary>响应示例</summary>

```json
{
  "code": 0,
  "message": "success",
  "request_id": "99f4d83804b54d1c90681add4505eca0",
  "data": {
    "timestamp": 1786689000000,
    "auction_phase": "final",
    "data_status": "ready",
    "total": 1,
    "item": [
      {
        "thscode": "600519.SH",
        "ticker": "600519",
        "name": "贵州茅台",
        "auction_price": 1421.0,
        "auction_pct": 0.35,
        "auction_volume": 12600,
        "auction_amount": 17904600,
        "auction_unmatched": 800,
        "auction_turnover_pct": 0.01,
        "auction_yesterday_ratio_pct": 82.4,
        "auction_volume_ratio": 1.12,
        "pre_close_price": 1416.04,
        "open_price": 1421.0,
        "last_price": 1421.0,
        "float_market_cap": 1785000000000
      }
    ]
  }
}
```

</details>

### 交易日序列

`GET /api/a-share/calendar/trading-days`

A 股近一年交易日序列，**固定窗口**为 [今日 - 1 年, 今日]（Asia/Shanghai 自然日），无任何请求参数。

**运行验证**：`verified_success`，`code=0`，success

**请求参数**

| 参数 | 位置 | 类型 | 必需 | 说明 | 默认值 |
|---|---|---|---|---|---|
| - | - | - | - | 无入参。 | - |

**主要响应字段**

| 字段 | 类型 | 说明 |
|---|---|---|
| timestamp | long | 数据就绪时间（毫秒）。 |
| item | array | 交易日列表，按时间升序。 |
| date_ms | long | 单个交易日的 Asia/Shanghai 00:00:00 毫秒戳。 |
| date | string | 同一交易日的 yyyyMMdd 格式（Asia/Shanghai），方便直接展示 / 对账。 |

示例：`https://datahub.10jqka.com.cn/api/a-share/calendar/trading-days`

<details>
<summary>响应示例</summary>

```json
{
  "code": 0,
  "message": "success",
  "request_id": "a1b2c3d4e5f6789012345678abcdef01",
  "data": {
    "timestamp": 1748275200000,
    "item": [
      {
        "date_ms": 1747929600000,
        "date": "20250523"
      },
      {
        "date_ms": 1748188800000,
        "date": "20250526"
      },
      {
        "date_ms": 1748275200000,
        "date": "20250527"
      }
    ]
  }
}
```

</details>

### 龙虎榜榜单

`GET /api/a-share/special-data/dragon-tiger-list`

按交易日返回龙虎榜首页整体榜单。省略 date 时，若今天是交易日则默认取上一个交易日；若今天不是交易日，则默认取今天之前最近一个交易日。 显式传入非交易日会返回参数错误，不自动回退。

**运行验证**：`verified_success`，`code=0`，success

**请求参数**

| 参数 | 位置 | 类型 | 必需 | 说明 | 默认值 |
|---|---|---|---|---|---|
| board_type | query | enum | 否 | 榜单类型：all 全部 / org 机构榜 / hot_money 游资榜。 | all |
| date | query | string | 否 | 目标交易日，格式 yyyy-MM-dd；只支持一年内数据。显式传入非交易日返回 code=1002。 | 最近可用交易日 |

**主要响应字段**

| 字段 | 类型 | 说明 |
|---|---|---|
| timestamp | long | 目标交易日 Asia/Shanghai 00:00 毫秒时间戳。 |
| board_type | string | 实际榜单类型：all / org / hot_money。 |
| trade_date | string | 实际查询交易日，格式 yyyy-MM-dd。 |
| count | integer | 上游记录数；同一股票可能同时出现当日榜和 3 日榜。 |
| stock_count | integer | 股票去重数量。 |
| stock_items | array | 股票维度榜单；board_type=all/org 时填充，hot_money 时为空数组。 |
| hot_money_items | array | 游资维度聚合榜单；board_type=hot_money 时填充，普通榜单时为空数组。 |
| thscode | string | 带交易所后缀的标准代码，例如 002407.SZ。 |
| ticker | string | 6 位股票代码。 |
| name | string | 股票简称。 |
| concept_list | array | 所属概念列表，元素包含 name。 |
| change | number | 当日涨跌幅，小数形式。 |
| net_value | number | 龙虎榜净买入金额，单位元。 |
| net_rate | number | 龙虎榜净买入占比，小数形式。 |
| hot_rank | integer | 同花顺人气排名，数值越小越靠前。 |
| buy_value | number | 买方金额，单位元。 |
| sell_value | number | 卖方金额，单位元。 |
| limit_reason | string | 涨跌停原因。 |
| range_days | integer | 上榜区间天数，1 为当日榜，3 为 3 日榜。 |
| org_net_value | number | 机构净买入金额，单位元。 |

示例：`https://datahub.10jqka.com.cn/api/a-share/special-data/dragon-tiger-list`

<details>
<summary>响应示例</summary>

```json
{
  "code": 0,
  "message": "success",
  "request_id": "a1b2c3d4e5f6789012345678abcdef01",
  "data": {
    "timestamp": 1782921600000,
    "board_type": "all",
    "trade_date": "2026-07-01",
    "count": 80,
    "stock_count": 75,
    "stock_items": [
      {
        "thscode": "002407.SZ",
        "ticker": "002407",
        "name": "多氟多",
        "change": 0.09994,
        "net_value": 1786253128.23,
        "net_rate": 0.11901893,
        "hot_rank": 2,
        "buy_value": 2674755016.05,
        "sell_value": 888501887.82,
        "limit_reason": "半导体级氢氟酸涨价+六氟磷酸锂+大圆柱电池",
        "range_days": 3
      }
    ],
    "hot_money_items": []
  }
}
```

</details>

### 10 年全量日 K

`GET /api/dump/market-dumps/daily-k/download-url`

本页接口获取全市场 Parquet 文件的短时下载链接；链接签出成功不等于文件已下载或交付。 三个 GET 端点均无业务请求参数。先按 Lumi 的 DataHub 工具调用规则请求目标端点，再检查 HTTP/工具状态与业务响应：code=0 且 data.presigned_url 为非空字符串，才表示取得下载链接。request_id 用于排查；若返回 data.presigned_url_expires_at，按其过期时间处理。下载链接通常约 5 分钟有效。

**运行验证**：`skipped_sensitive_dump`，未请求以避免短时下载链接落盘

### 复权因子全量

`GET /api/dump/market-dumps/adjustment-factors/download-url`

日 K dump 共用相同的 Parquet schema；daily-k 提供最近约 10 年全量窗口，daily-k-10d 提供最近 10 个交易日的轻量增量窗口。复权因子 dump 使用独立的事件流 schema。

**运行验证**：`skipped_sensitive_dump`，未请求以避免短时下载链接落盘

### 最近 10 交易日日 K

`GET /api/dump/market-dumps/daily-k-10d/download-url`

本页接口获取全市场 Parquet 文件的短时下载链接；链接签出成功不等于文件已下载或交付。 三个 GET 端点均无业务请求参数。先按 Lumi 的 DataHub 工具调用规则请求目标端点，再检查 HTTP/工具状态与业务响应：code=0 且 data.presigned_url 为非空字符串，才表示取得下载链接。request_id 用于排查；若返回 data.presigned_url_expires_at，按其过期时间处理。下载链接通常约 5 分钟有效。

**运行验证**：`skipped_sensitive_dump`，未请求以避免短时下载链接落盘

### 市场成交额预测

`GET /api/a-share/special-data/turnover-prediction-snapshot`

查询当前市场成交额预测快照。source_updated_at 为业务图表更新时间；预测增减额等于预测全天成交额减昨日成交额，任一输入为空时差值为 null。

**运行验证**：`verified_success`，`code=0`，success

**请求参数**：无业务参数。

**主要响应字段**

| 字段 | 类型 | 说明 |
|---|---|---|
| timestamp | integer | 快照采样时间；单位：毫秒 |
| source_updated_at | integer \| null | 业务数据源更新时间；单位：毫秒 |
| predict_turnover | number \| null | 市场预测全天成交额；单位：元 |
| previous_turnover | number \| null | 预测变化所参照的昨日全天成交额；单位：元 |
| predict_turnover_change | number \| null | 用户授权的预测增减额；任一输入为null则null；单位：元 |

示例：`https://datahub.10jqka.com.cn/api/a-share/special-data/turnover-prediction-snapshot`

<details>
<summary>响应示例</summary>

```json
{
  "code": 0,
  "message": "success",
  "request_id": "example-request",
  "data": {
    "timestamp": 1791957420050,
    "source_updated_at": 1791881980000,
    "predict_turnover": 1688900400000,
    "previous_turnover": 1550743500000,
    "predict_turnover_change": 138156900000
  }
}
```

</details>

### 筹码形态股票筛选

`GET /api/a-share/special-data/chip-shape-stocks`

按双峰、高位密集、低位密集或低位锁定形态查询股票，保持筛选结果顺序。

**运行验证**：`verified_success`，`code=0`，success

**请求参数**

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|---|---|---|---|---|
| shape | string | 是 | — | double_peak/high_position_dense/low_position_dense/low_position_locked |
| date | string | 否 | — | 查询日期，YYYY-MM-DD；默认日期与有效范围见接口说明；须属于可用日期集合 |
| page | integer | 否 | 1 | 从1开始的页码 |
| size | integer | 否 | 20 | 每页1至20条，默认20 |

**主要响应字段**

| 字段 | 类型 | 说明 |
|---|---|---|
| date | date | 本页对应日期 |
| shape | enum | 筛选形态 |
| item | array | 业务记录列表 |
| pagination | object | 分页对象，包含page、size、total和has_next |
| thscode | string | 标准股票代码 |
| name | string | 股票名称 |
| page | integer | 从1开始的页码 |
| size | integer | 本页请求大小 |
| total | integer \| null | 结果总数；未提供时为null |
| has_next | boolean | 是否存在后续页 |

示例：`https://datahub.10jqka.com.cn/api/a-share/special-data/chip-shape-stocks?shape=double_peak&date=2026-10-13&page=1&size=20`

<details>
<summary>响应示例</summary>

```json
{
  "code": 0,
  "message": "success",
  "request_id": "example-request",
  "data": {
    "date": "2026-10-13",
    "shape": "double_peak",
    "item": [
      {
        "thscode": "300833.SZ",
        "name": "浩洋股份"
      }
    ],
    "pagination": {
      "page": 1,
      "size": 20,
      "total": 42,
      "has_next": true
    }
  }
}
```

</details>

### 筹码形态可选日期

`GET /api/a-share/special-data/chip-shape-dates`

查询筹码选股可用日期及最新日期，选股日期以本接口返回的集合为边界。

**运行验证**：`verified_success`，`code=0`，success

**请求参数**：无业务参数。

**主要响应字段**

| 字段 | 类型 | 说明 |
|---|---|---|
| latest_date | date | 数据返回最新可选日期 |
| dates | array[date] | 真实可选日期集合 |

示例：`https://datahub.10jqka.com.cn/api/a-share/special-data/chip-shape-dates`

<details>
<summary>响应示例</summary>

```json
{
  "code": 0,
  "message": "success",
  "request_id": "example-request",
  "data": {
    "latest_date": "2026-10-13",
    "dates": [
      "2026-04-13",
      "2026-10-13"
    ]
  }
}
```

</details>

### 飙升榜

`GET /api/a-share/special-data/skyrocket-list`

查询 A 股热度排名飙升榜，默认30条、可选最多100条。period=day 返回日榜，period=hour 返回小时榜；省略 period 时默认返回日榜。

**运行验证**：`verified_success`，`code=0`，success

**请求参数**

| 参数 | 位置 | 类型 | 必需 | 说明 | 默认值 |
|---|---|---|---|---|---|
| period | query | enum | 否 | 榜单周期：day 日榜 / hour 小时榜。 | day |
| limit | query | integer | 否 | 返回1至100条，不足时按实际条数。 | 30 |

**主要响应字段**

| 字段 | 类型 | 说明 |
|---|---|---|
| timestamp | long | 榜单时间戳，毫秒级 Unix 时间戳。 |
| item | array | 榜单股票条目，按limit返回，默认30条、最多100条，不足请求条数时返回实际条数。 |
| thscode | string | 带交易所后缀的标准代码，例如 603822.SH。 |
| ticker | string | 6 位股票代码。 |
| name | string | 股票简称。 |
| rank | integer | 当前排名。 |
| heat | string | 热度值，保留上游原始字符串。 |
| rank_change | integer \| null | 排名变化，正数表示上升，负数表示下降；上游缺失时为 null。 |
| rank_trend | string | 排名趋势：up / down / flat / unknown。 |

示例：`https://datahub.10jqka.com.cn/api/a-share/special-data/skyrocket-list?period=hour`

<details>
<summary>响应示例</summary>

```json
{
  "code": 0,
  "message": "success",
  "request_id": "a1b2c3d4e5f6789012345678abcdef01",
  "data": {
    "timestamp": 1748102400000,
    "item": [
      {
        "thscode": "603822.SH",
        "ticker": "603822",
        "name": "嘉澳环保",
        "rank": 1,
        "heat": "1941909",
        "rank_change": 7,
        "rank_trend": "up"
      }
    ]
  }
}
```

</details>

### 个股排名走势

`GET /api/a-share/special-data/hot-stock-rank-trend`

查询单只 A 股在一段自然日窗口内的热榜排名走势。窗口和日期都限制在一年内，返回点位与上游日线序列对齐。 该接口返回的是走势点位，不做 Top30 截断。

**运行验证**：`verified_success`，`code=0`，success

**请求参数**

| 参数 | 位置 | 类型 | 必需 | 说明 | 默认值 |
|---|---|---|---|---|---|
| thscode | query | string | 是 | 单只 A 股标的，含交易所后缀，例如 300034.SZ。 | - |
| start_date | query | string | 是 | 起始自然日，格式 yyyy-MM-dd。 | - |
| end_date | query | string | 是 | 结束自然日，格式 yyyy-MM-dd；需大于等于 start_date。 | - |

**主要响应字段**

| 字段 | 类型 | 说明 |
|---|---|---|
| timestamp | long | 起始自然日 Asia/Shanghai 00:00 毫秒时间戳。 |
| item | array | 日线排名走势点位。 |
| thscode | string | 入参标准代码。 |
| ticker | string | 6 位股票代码。 |
| date | string | 自然日，格式 yyyy-MM-dd。 |
| date_ms | long | 该自然日 Asia/Shanghai 00:00 毫秒时间戳。 |
| rank | integer | 当日热榜排名。 |

示例：`https://datahub.10jqka.com.cn/api/a-share/special-data/hot-stock-rank-trend?thscode=300034.SZ&start_date=2026-06-21&end_date=2026-07-01`

<details>
<summary>响应示例</summary>

```json
{
  "code": 0,
  "message": "success",
  "request_id": "a1b2c3d4e5f6789012345678abcdef01",
  "data": {
    "timestamp": 1781971200000,
    "item": [
      {
        "thscode": "300034.SZ",
        "ticker": "300034",
        "date": "2026-06-21",
        "date_ms": 1781971200000,
        "rank": 1740
      }
    ]
  }
}
```

</details>

### 历史热股排行

`GET /api/a-share/special-data/hot-stock-list-history`

按自然日返回历史热股榜排行。日期参数为 date=yyyy-MM-dd，按北京时间自然日查询。

**运行验证**：`verified_success`，`code=0`，success

**请求参数**

| 参数 | 位置 | 类型 | 必需 | 说明 | 默认值 |
|---|---|---|---|---|---|
| date | query | string | 是 | 目标自然日，格式 yyyy-MM-dd；只支持一年内数据。 | - |

**主要响应字段**

| 字段 | 类型 | 说明 |
|---|---|---|
| date | string | 查询自然日，格式 yyyy-MM-dd。 |
| date_ms | long | 查询自然日 Asia/Shanghai 00:00 毫秒时间戳。 |
| item | array | 历史热股榜股票条目，最多 30 条。 |
| thscode | string | 带交易所后缀的标准代码，例如 000725.SZ。 |
| ticker | string | 6 位股票代码。 |
| name | string | 股票简称。 |
| rank | integer | 当日热榜排名。 |

示例：`https://datahub.10jqka.com.cn/api/a-share/special-data/hot-stock-list-history?date=2026-06-21`

<details>
<summary>响应示例</summary>

```json
{
  "code": 0,
  "message": "success",
  "request_id": "a1b2c3d4e5f6789012345678abcdef01",
  "data": {
    "date": "2026-06-21",
    "date_ms": 1781971200000,
    "item": [
      {
        "thscode": "000725.SZ",
        "ticker": "000725",
        "name": "京东方A",
        "rank": 1
      }
    ]
  }
}
```

</details>

### A股热股榜单

`GET /api/a-share/special-data/hot-stock-list`

查询 A 股热股榜单，默认30条、可选最多100条。period=day 返回 24 小时级别榜单，period=hour 返回小时级别榜单；省略 period 时默认返回 24 小时级别榜单。

**运行验证**：`verified_success`，`code=0`，success

**请求参数**

| 参数 | 位置 | 类型 | 必需 | 说明 | 默认值 |
|---|---|---|---|---|---|
| period | query | enum | 否 | 榜单周期：day 24 小时级别 / hour 小时级别。 | day |
| limit | query | integer | 否 | 返回1至100条，不足时按实际条数。 | 30 |

示例：`https://datahub.10jqka.com.cn/api/a-share/special-data/hot-stock-list?period=day`

<details>
<summary>响应示例</summary>

```json
{
  "code": 0,
  "message": "success",
  "request_id": "a1b2c3d4e5f6789012345678abcdef01",
  "data": {
    "timestamp": 1748102400000,
    "item": [
      {
        "thscode": "603822.SH",
        "ticker": "603822",
        "name": "嘉澳环保",
        "rank": 1,
        "heat": "1941909",
        "rank_change": 7,
        "rank_trend": "up"
      }
    ]
  }
}
```

</details>

### 新股发行与申购

`GET /api/a-share/ipo/calendar-list`

按沪深或京市及待申购、可申购、待上市阶段查询股票发行记录。股票代码与申购代码分别提供，上市日期和发行价未确定时为 null。

**运行验证**：`verified_success`，`code=0`，success

**请求参数**

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|---|---|---|---|---|
| market | string | 是 | — | 适用市场：sh_sz/bj |
| status | string | 是 | — | 发行阶段：upcoming/subscribable/awaiting_listing |

**主要响应字段**

| 字段 | 类型 | 说明 |
|---|---|---|
| market | enum | 数据市场分组 |
| status | enum | 返回返回的发行阶段 |
| item | array | 业务记录列表 |
| thscode | string \| null | 发行股票的标准形式代码 |
| ticker | string | 发行股票代码 |
| name | string | 股票名称 |
| subscription_code | string \| null | 申购代码 |
| subscription_date | date \| null | 申购日期 |
| listing_date | date \| null | 上市日期 |
| issue_price | number \| null | 返回发行价，未确定时null；单位：元 |

示例：`https://datahub.10jqka.com.cn/api/a-share/ipo/calendar-list?market=bj&status=subscribable`

<details>
<summary>响应示例</summary>

```json
{
  "code": 0,
  "message": "success",
  "request_id": "example-request",
  "data": {
    "market": "bj",
    "status": "subscribable",
    "item": [
      {
        "thscode": "920285.BJ",
        "ticker": "920285",
        "name": "远大健科",
        "subscription_code": "920285",
        "subscription_date": "2026-10-14",
        "listing_date": null,
        "issue_price": 20.3
      }
    ]
  }
}
```

</details>

### 异动股票

`GET /api/a-share/special-data/abnormal-monitor-list`

查询当前或历史异动监控记录。开始和结束日期保留原监控区间，结束日期可为空；类型码 1、2 对应严重异动，其余为重点监控。

**运行验证**：`verified_success`，`code=0`，success

**请求参数**

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|---|---|---|---|---|
| state | string | 否 | current | current或history |
| page | integer | 否 | 1 | 从1开始的页码 |
| size | integer | 否 | 30 | 每页1至30条，默认30 |

**主要响应字段**

| 字段 | 类型 | 说明 |
|---|---|---|
| item | array | 业务记录列表 |
| pagination | object | 分页对象，包含page、size、total和has_next |
| thscode | string \| null | 股票标准代码 ；源null或空字符串原样保留，缺失值为null |
| name | string \| null | 股票名称 ；源null或空字符串原样保留，缺失值为null |
| start_date_ms | integer | 监控开始日期；单位：毫秒 |
| end_date_ms | integer \| null | 结束日期；单位：毫秒 |
| monitor_type | integer | 原始业务类型码 |
| monitor_label | string | 1/2=严重异动，其它=重点监控 |
| page | integer | 从1开始的页码 |
| size | integer | 本页请求大小 |
| total | integer \| null | 结果总数；未提供时为null |
| has_next | boolean | 是否存在后续页 |

示例：`https://datahub.10jqka.com.cn/api/a-share/special-data/abnormal-monitor-list?state=current&page=1&size=30`

<details>
<summary>响应示例</summary>

```json
{
  "code": 0,
  "message": "success",
  "request_id": "example-request",
  "data": {
    "item": [
      {
        "thscode": "600825.SH",
        "name": "新华传媒",
        "start_date_ms": 1791734400000,
        "end_date_ms": 1792684800000,
        "monitor_type": 1,
        "monitor_label": "严重异动"
      }
    ],
    "pagination": {
      "page": 1,
      "size": 30,
      "total": 6,
      "has_next": false
    }
  }
}
```

</details>

### 按股票查询个股异动原因

`GET /api/a-share/special-data/anomaly-analysis-stock`

按同花顺代码批量查询当日个股异动原因，按请求代码首次出现顺序返回匹配记录；格式合法但当日无异动的代码会被忽略。

**运行验证**：`verified_success`，`code=0`，success

**请求参数**

| 参数 | 位置 | 类型 | 必需 | 说明 | 默认值 |
|---|---|---|---|---|---|
| thscodes | query | string | 是 | 逗号分隔的同花顺代码列表，支持 SH / SZ / BJ 后缀，大小写不敏感；去重前最多 50 个 token。 | - |

示例：`https://datahub.10jqka.com.cn/api/a-share/special-data/anomaly-analysis-stock?thscodes=600519.SH,000001.SZ`

<details>
<summary>响应示例</summary>

```json
{
  "code": 0,
  "message": "success",
  "request_id": "a1b2c3d4e5f6789012345678abcdef01",
  "data": {
    "timestamp": 1751260800000,
    "item": [
      {
        "stock_name": "贵州茅台",
        "analysis_content": "公司股价出现异动，相关解读内容以服务端快照为准。",
        "keyword_list": [
          "白酒",
          "消费"
        ],
        "thscode": "600519.SH",
        "tag_name": "大涨"
      }
    ]
  }
}
```

</details>

### 个股异动原因列表

`GET /api/a-share/special-data/anomaly-analysis-list`

查询当日个股异动原因，可选按异动标签过滤；不传 tag_codes 时返回全部当日记录。

**运行验证**：`verified_success`，`code=0`，success

**请求参数**

| 参数 | 位置 | 类型 | 必需 | 说明 | 默认值 |
|---|---|---|---|---|---|
| tag_codes | query | string | 否 | 异动标签，逗号分隔，多个值为 OR 关系；大小写不敏感，重复值自动去重。合法值见下方标签表。 | - |

**主要响应字段**

| 字段 | 类型 | 说明 |
|---|---|---|
| timestamp | long | 数据时间戳，毫秒级 Unix 时间戳。 |
| item | array | 个股异动原因列表。 |
| stock_name | string | 股票名称。 |
| analysis_content | string | 异动解读内容。 |
| keyword_list | string[] | 关键词列表；无关键词时返回空数组。 |
| thscode | string | 带交易所后缀的同花顺代码，例如 600519.SH。 |
| tag_name | string | 异动标签展示名。 |

示例：`https://datahub.10jqka.com.cn/api/a-share/special-data/anomaly-analysis-list?tag_codes=LIMIT_UP,SHARP_FALL`

<details>
<summary>响应示例</summary>

```json
{
  "code": 0,
  "message": "success",
  "request_id": "a1b2c3d4e5f6789012345678abcdef01",
  "data": {
    "timestamp": 1751260800000,
    "item": [
      {
        "stock_name": "贵州茅台",
        "analysis_content": "公司股价出现异动，相关解读内容以服务端快照为准。",
        "keyword_list": [
          "白酒",
          "消费"
        ],
        "thscode": "600519.SH",
        "tag_name": "大涨"
      }
    ]
  }
}
```

</details>

### 营业部经典战绩

`GET /api/a-share/special-data/dragon-tiger-department-classic-record`

查询营业部身份及一条代表战绩。无代表战绩时，classic_record 为 null。

**运行验证**：`verified_success`，`code=0`，success

**请求参数**

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|---|---|---|---|---|
| department_id | string | 是 | — | 营业部业务标识 |

**主要响应字段**

| 字段 | 类型 | 说明 |
|---|---|---|
| department_id | string | 当前查询使用的营业部ID |
| department_name | string \| null | 营业部名称 |
| organization_id | string \| null | 组织业务标识 |
| classic_record | object \| null | 代表战绩对象，缺失时为null |
| thscode | string \| null | 返回已提供标准股票代码 |
| name | string \| null | 股票名称 |
| board_pattern | string \| null | 几天几板原始描述 |

示例：`https://datahub.10jqka.com.cn/api/a-share/special-data/dragon-tiger-department-classic-record?department_id=Q1218139C1`

<details>
<summary>响应示例</summary>

```json
{
  "code": 0,
  "message": "success",
  "request_id": "example-request",
  "data": {
    "department_id": "Q1218139C1",
    "department_name": "高盛(中国)上海浦东新区世纪大道证券营业部",
    "organization_id": "Q1218139C1",
    "classic_record": {
      "thscode": "603272.SH",
      "name": "*ST联翔",
      "board_pattern": "24天14板"
    }
  }
}
```

</details>

### 营业部历史上榜记录

`GET /api/a-share/special-data/dragon-tiger-department-history`

分页查询营业部上榜股票，支持净买入金额档位和排序；同股不同上榜记录分别保留。

**运行验证**：`verified_success`，`code=0`，success

**请求参数**

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|---|---|---|---|---|
| department_id | string | 是 | — | 营业部业务标识 |
| page | integer | 否 | 1 | 从1开始的页码 |
| size | integer | 否 | 30 | 每页1至30条，默认30 |
| min_net_buy_amount | integer | 否 | — | 净买入金额档位：5000000/30000000/50000000/100000000，单位元 |
| sort_field | string | 否 | trade_date | 排序字段：trade_date/change_ratio/net_buy_amount |
| sort_dir | string | 否 | desc | asc或desc |

**主要响应字段**

| 字段 | 类型 | 说明 |
|---|---|---|
| item | array | 业务记录列表 |
| pagination | object | 分页对象，包含page、size、total和has_next |
| thscode | string \| null | 股票标准代码 ；源null或空字符串原样保留，缺失值为null |
| name | string \| null | 名称 ；源null或空字符串原样保留，缺失值为null |
| trade_date | date | 上榜交易日 |
| change_ratio | number \| null | 当日涨跌幅；单位：小数比例 |
| net_buy_amount | number \| null | 净买入；单位：元 |
| rank_type | integer | 保留返回榜单区间码 |
| page | integer | 从1开始的页码 |
| size | integer | 本页请求大小 |
| total | integer \| null | 结果总数；未提供时为null |
| has_next | boolean | 是否存在后续页 |

示例：`https://datahub.10jqka.com.cn/api/a-share/special-data/dragon-tiger-department-history?department_id=Q1218139C1&page=1&size=30`

<details>
<summary>响应示例</summary>

```json
{
  "code": 0,
  "message": "success",
  "request_id": "example-request",
  "data": {
    "item": [
      {
        "thscode": "600408.SH",
        "name": "安泰集团",
        "trade_date": "2026-10-12",
        "change_ratio": -0.066138,
        "net_buy_amount": -19330482,
        "rank_type": 0
      }
    ],
    "pagination": {
      "page": 1,
      "size": 30,
      "total": 4048,
      "has_next": true
    }
  }
}
```

</details>

### 跌停股票池

`GET /api/a-share/special-data/limit-down-pool`

按交易日返回 A 股跌停股票池，首次与最后跌停时间统一为上海时区 HH:mm。

**运行验证**：`verified_success`，`code=0`，success

**请求参数**

| 参数 | 位置 | 类型 | 必需 | 说明 | 默认值 |
|---|---|---|---|---|---|
| date_ms | query | long | 否 | 交易日的上海时区零点毫秒时间戳。 | 当前自然日 |
| page | query | integer | 否 | 页码，从 1 开始。 | 1 |
| size | query | integer | 否 | 单页条数，范围 1..200。 | 50 |
| sort_field | query | enum | 否 | last_limit_time / first_limit_time / last_price / price_change_ratio_pct / turnover_ratio_pct。 | last_limit_time |
| sort_dir | query | enum | 否 | asc / desc。 | desc |

**主要响应字段**

| 字段 | 类型 | 说明 |
|---|---|---|
| thscode / ticker / name | string | 标准代码、纯代码与股票简称。 |
| last_price | decimal | 最新价。 |
| price_change_ratio_pct | decimal | 涨跌幅，百分数原值。 |
| first_limit_time / last_limit_time | string | 首次与最后跌停时间，上海时区 HH:mm。 |
| turnover_ratio_pct | decimal | 换手率，百分数原值。 |

示例：`https://datahub.10jqka.com.cn/api/a-share/special-data/limit-down-pool?page=1&size=50&sort_field=last_limit_time&sort_dir=desc`

<details>
<summary>响应示例</summary>

```json
{
  "code": 0,
  "message": "success",
  "request_id": "5d0430b287ab4fdc89f3c47cd080aa8e",
  "data": {
    "timestamp": 1786690800000,
    "pagination": {
      "total": 1,
      "pages": 1,
      "size": 50,
      "page": 1
    },
    "item": [
      {
        "thscode": "600000.SH",
        "ticker": "600000",
        "name": "示例股票",
        "last_price": 9.8,
        "price_change_ratio_pct": -10.0,
        "first_limit_time": "09:35",
        "last_limit_time": "14:56",
        "turnover_ratio_pct": 4.2
      }
    ]
  }
}
```

</details>

### 连板天梯

`GET /api/a-share/special-data/limit-up-ladder`

返回 A 股近 30 个交易日的连板梯队矩阵（按日期 -> 6 个板 -> 股票列表），用于近期连板分布、次日晋级追踪等分析。 无入参；上游当前固定返回 30 日，每个板位最多 4 只。

**运行验证**：`verified_success`，`code=0`，success

**请求参数**

| 参数 | 位置 | 类型 | 必需 | 说明 | 默认值 |
|---|---|---|---|---|---|
| - | - | - | - | 无入参。 | - |

**主要响应字段**

| 字段 | 类型 | 说明 |
|---|---|---|
| timestamp | long | 数据就绪时间（毫秒）。 |
| window | object | 窗口元信息。 |
| item | array | 按交易日组织的连板矩阵。 |
| length | integer | 交易日窗口长度。 |
| date_list | string[] | 窗口内交易日列表，按后端返回顺序排列。 |
| board_caps | object | 每个板位的最大列表长度。 |
| thscode | string | 带交易所后缀的标准代码。 |
| ticker | string | 6 位股票代码。 |
| name | string | 股票简称。 |
| board_num | integer | 连板数。 |
| seal_nextday | boolean \| null | 次一交易日是否继续封板；最近交易日没有次日参考，固定为 null。 |
| sign_level | integer | 上游标记等级。 |

示例：`https://datahub.10jqka.com.cn/api/a-share/special-data/limit-up-ladder`

<details>
<summary>响应示例</summary>

```json
{
  "code": 0,
  "message": "success",
  "request_id": "a1b2c3d4e5f6789012345678abcdef01",
  "data": {
    "timestamp": 1748102400000,
    "window": {
      "length": 30,
      "date_list": [
        "20250620",
        "20250619"
      ],
      "board_caps": {
        "two_board": 4,
        "three_board": 4,
        "four_board": 4,
        "five_board": 4,
        "six_board": 4,
        "seven_over": 4
      }
    },
    "item": [
      {
        "date": "20250620",
        "boards": {
          "two_board": [
            {
              "thscode": "603986.SH",
              "ticker": "603986",
              "name": "兆易创新",
              "board_num": 2,
              "seal_nextday": null,
              "sign_level": 1
            }
          ],
          "three_board": [],
          "four_board": [],
          "five_board": [],
          "six_board": [],
          "seven_over": []
        }
      }
    ]
  }
}
```

</details>

### 炸板股票池

`GET /api/a-share/special-data/limit-break-pool`

按交易日返回 A 股涨停炸板股票池；接口直接消费炸板集合，不在服务端生成或归因。

**运行验证**：`verified_success`，`code=0`，success

**请求参数**

| 参数 | 位置 | 类型 | 必需 | 说明 | 默认值 |
|---|---|---|---|---|---|
| date_ms | query | long | 否 | 交易日的上海时区零点毫秒时间戳。 | 当前自然日 |
| page | query | integer | 否 | 页码，从 1 开始。 | 1 |
| size | query | integer | 否 | 单页条数，范围 1..200。 | 50 |
| sort_field | query | enum | 否 | price_change_ratio_pct / open_times / last_price / turnover_ratio_pct / turnover。 | price_change_ratio_pct |
| sort_dir | query | enum | 否 | asc / desc。 | desc |

**主要响应字段**

| 字段 | 类型 | 说明 |
|---|---|---|
| thscode / ticker / name | string | 标准代码、纯代码与股票简称。 |
| last_price | decimal | 最新价。 |
| price_change_ratio_pct | decimal | 涨跌幅，百分数原值。 |
| open_times | integer | 开板次数。 |
| turnover_ratio_pct | decimal | 换手率，百分数原值。 |
| turnover | decimal | 成交额。 |

示例：`https://datahub.10jqka.com.cn/api/a-share/special-data/limit-break-pool?page=1&size=50&sort_field=open_times&sort_dir=desc`

<details>
<summary>响应示例</summary>

```json
{
  "code": 0,
  "message": "success",
  "request_id": "90015f998b184711bd65152750320b47",
  "data": {
    "timestamp": 1786690800000,
    "pagination": {
      "total": 1,
      "pages": 1,
      "size": 50,
      "page": 1
    },
    "item": [
      {
        "thscode": "000001.SZ",
        "ticker": "000001",
        "name": "示例股票",
        "last_price": 12.5,
        "price_change_ratio_pct": 7.6,
        "open_times": 3,
        "turnover_ratio_pct": 8.1,
        "turnover": 1250000000
      }
    ]
  }
}
```

</details>

### 涨停股票池

`GET /api/a-share/special-data/limit-up-pool`

按交易日返回 A 股涨停 / 连板股票池，后端固定取全部连板与 main,chinext,ssestar,north 四类板块，支持分页与排序。 返回字段聚焦涨停语义（涨停时间、原因、连板天数、封单额等），不含资金流 / 行业 / 分时预览等通用字段。

**运行验证**：`verified_success`，`code=0`，success

**请求参数**

| 参数 | 位置 | 类型 | 必需 | 说明 | 默认值 |
|---|---|---|---|---|---|
| date_ms | query | long | 否 | 查询交易日 Unix 毫秒戳（Asia/Shanghai 00:00:00）；省略时回退到服务端当前自然日。 | - |
| page | query | integer | 否 | 页码，必须 >= 1。 | 1 |
| size | query | integer | 否 | 分页大小，取值范围 1 到 200。 | 50 |
| sort_field | query | enum | 否 | 排序字段：last_price / continue_day_cnt / seal_money / limit_up_time。 | last_price |
| sort_dir | query | enum | 否 | 排序方向：asc / desc。 | desc |

**主要响应字段**

| 字段 | 类型 | 说明 |
|---|---|---|
| timestamp | long | 数据就绪时间（毫秒）。 |
| pagination | object | 分页信息。 |
| item | array | 涨停股票列表。 |
| total | integer | 总条数。 |
| pages | integer | 总页数。 |
| size | integer | 当前分页大小，回显请求参数。 |
| page | integer | 当前页码，回显请求参数。 |
| thscode | string | 带交易所后缀的标准代码，例如 603986.SH。 |
| ticker | string | 6 位股票代码。 |
| name | string | 股票简称。 |
| is_st | boolean | 是否 ST，仅展示，不作为筛选入参。 |
| is_new | boolean | 是否未开板新股，仅展示。 |
| last_price | decimal | 当前价格，单位元。 |
| price_change_ratio_pct | decimal | 涨跌幅百分比，已乘以 100。 |
| limit_up_time | string | 涨停时间，格式 HH:MM。 |
| limit_up_reason | string \| null | 涨停原因；上游空字符串会标准化为 null。 |
| continue_day_text | string | 连板文本，例如 首板、5天4板。 |
| continue_day_cnt | integer | 连板计数。 |
| seal_money | decimal | 当前封单额，单位元。 |
| max_seal_money | decimal | 峰值封单额，单位元。 |

示例：`https://datahub.10jqka.com.cn/api/a-share/special-data/limit-up-pool?page=1&size=50&sort_field=limit_up_time&sort_dir=desc`

<details>
<summary>响应示例</summary>

```json
{
  "code": 0,
  "message": "success",
  "request_id": "a1b2c3d4e5f6789012345678abcdef01",
  "data": {
    "timestamp": 1748102400000,
    "pagination": {
      "total": 126,
      "pages": 3,
      "size": 50,
      "page": 1
    },
    "item": [
      {
        "thscode": "603986.SH",
        "ticker": "603986",
        "name": "兆易创新",
        "is_st": false,
        "is_new": false,
        "last_price": 118.23,
        "price_change_ratio_pct": 10.0008,
        "limit_up_time": "09:34",
        "limit_up_reason": "存储芯片",
        "continue_day_text": "2连板",
        "continue_day_cnt": 2,
        "seal_money": 123456789.12,
        "max_seal_money": 234567890.12
      }
    ]
  }
}
```

</details>

### 涨停强度与晋级统计

`GET /api/a-share/special-data/limit-up-statistics`

查询封板率、涨停打开家数、页面板数档位及精确连板家数。二、三、四和五板以上的晋级率为页面档位口径；五板以上为合并档位，精确家数仅包含实际返回的板数。

**运行验证**：`verified_success`，`code=0`，success

**请求参数**

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|---|---|---|---|---|
| date | string | 否 | — | 查询日期，YYYY-MM-DD；默认日期与有效范围见接口说明；省略使用当天或最近交易日，范围为一年 |

**主要响应字段**

| 字段 | 类型 | 说明 |
|---|---|---|
| timestamp | integer | 采样时间；单位：毫秒 |
| trade_date | date | 业务所属交易日；核对请求日期 |
| seal_rate | number \| null | 数据返回封板率，小数保持原值；单位：小数比例 |
| open_stock_count | integer | 市场涨停打开股票家数；单位：家 |
| limit_up_stock_count | integer | 封板汇总家数；单位：家 |
| touched_limit_up_stock_count | integer | 返回封板率对应的汇总基数；单位：家 |
| page_boards | array | 页面板数档位 |
| exact_boards | array | 精确连板家数 |
| board_level | enum | one/two/three/four/five_plus |
| stock_count | integer | 对应板数档位家数；单位：家 |
| promotion_rate | number \| null | 页面档位晋级率；five_plus为合并档位，one为null；单位：小数比例 |
| board_num | integer | 返回实际返回的精确板数，N≥2 |
| stock_count | integer | 恰好N板家数，由返回直接提供；单位：家 |

示例：`https://datahub.10jqka.com.cn/api/a-share/special-data/limit-up-statistics?date=2026-10-12`

<details>
<summary>响应示例</summary>

```json
{
  "code": 0,
  "message": "success",
  "request_id": "example-request",
  "data": {
    "timestamp": 1791957420015,
    "trade_date": "2026-10-12",
    "seal_rate": 0.647887323943662,
    "open_stock_count": 25,
    "limit_up_stock_count": 46,
    "touched_limit_up_stock_count": 71,
    "page_boards": [
      {
        "board_level": "one",
        "stock_count": 28,
        "promotion_rate": null
      },
      {
        "board_level": "two",
        "stock_count": 14,
        "promotion_rate": 0.25
      },
      {
        "board_level": "three",
        "stock_count": 1,
        "promotion_rate": 0.13
      },
      {
        "board_level": "four",
        "stock_count": 0,
        "promotion_rate": 0
      },
      {
        "board_level": "five_plus",
        "stock_count": 3,
        "promotion_rate": 0.75
      }
    ],
    "exact_boards": [
      {
        "board_num": 10,
        "stock_count": 1
      },
      {
        "board_num": 6,
        "stock_count": 2
      },
      {
        "board_num": 3,
        "stock_count": 1
      },
      {
        "board_num": 2,
        "stock_count": 14
      }
    ]
  }
}
```

</details>

### 资金流向历史

`GET /api/a-share/capital-flow/historical`

查询单只 A 股的 1 分钟或日级资金流向历史。结果按 date_ms 升序排列。

**运行验证**：`verified_success`，`code=0`，success

**请求参数**

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|---|---|---|---|---|
| thscode | string | 是 | — | 单只 A 股完整代码；不支持批量、纯代码或非 A 股标的。 |
| interval | enum | 是 | — | 1m（1 分钟）或 1d（日）。 |
| start | long | 是 | — | 起始时间，毫秒级 Unix 时间戳，必须大于等于 0。 |
| end | long | 是 | — | 结束时间，毫秒级 Unix 时间戳，必须大于等于 start。1m 窗口最多 7 个自然日；1d 的结束日期不得晚于开始日期加 1 年。 |

**主要响应字段**

| 字段 | 类型 | 说明 |
|---|---|---|
| timestamp | long \| null | 返回序列中的最新有效时间点；无数据时为 null。 |
| thscode | string | 请求的 A 股完整代码。 |
| interval | string | 请求周期，值为 1m 或 1d。 |
| item | array | 按 date_ms 升序排列的历史点；无数据时为空数组。 |
| date_ms | long | 当前历史点时间，毫秒级 Unix 时间戳。 |
| super_large | object | 超大单资金对象。 |
| large | object | 大单资金对象。 |
| medium | object | 中单资金对象。 |
| small | object | 小单资金对象。 |
| inflow_amount | number \| null | 流入金额，单位为元。 |
| outflow_amount | number \| null | 流出金额，单位为元。 |

示例：`https://datahub.10jqka.com.cn/api/a-share/capital-flow/historical?thscode=600519.SH&interval=1d&start=1725148800000&end=1756684800000`

<details>
<summary>响应示例</summary>

```json
{
  "code": 0,
  "message": "success",
  "request_id": "d3a7750a0e6b4176a0f9ae66a8010a43",
  "data": {
    "timestamp": 1756684800000,
    "thscode": "600519.SH",
    "interval": "1d",
    "item": [
      {
        "date_ms": 1756684800000,
        "super_large": {
          "inflow_amount": 123456789.12,
          "outflow_amount": 100000000.00
        },
        "large": {
          "inflow_amount": 86543210.50,
          "outflow_amount": 81234567.89
        },
        "medium": {
          "inflow_amount": 45678901.23,
          "outflow_amount": 47890123.45
        },
        "small": {
          "inflow_amount": 23456789.01,
          "outflow_amount": 26789012.34
        }
      }
    ]
  }
}
```

</details>

### 资金流向实时快照

`GET /api/a-share/capital-flow/snapshot`

查询单只 A 股最新的超大单、大单、中单和小单资金流入、流出及净额。

**运行验证**：`verified_success`，`code=0`，success

**请求参数**

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|---|---|---|---|---|
| thscode | string | 是 | — | 单只 A 股完整代码；不支持批量、纯代码或非 A 股标的。 |

**主要响应字段**

| 字段 | 类型 | 说明 |
|---|---|---|
| timestamp | long \| null | 最新有效数据时间；没有可用时间时为 null。 |
| super_large | object | 超大单资金对象。 |
| large | object | 大单资金对象。 |
| medium | object | 中单资金对象。 |
| small | object | 小单资金对象。 |
| inflow_amount | number \| null | 流入金额，单位为元。 |
| outflow_amount | number \| null | 流出金额，单位为元。 |
| net_amount | number \| null | 净额，单位为元。 |

示例：`https://datahub.10jqka.com.cn/api/a-share/capital-flow/snapshot?thscode=600519.SH`

<details>
<summary>响应示例</summary>

```json
{
  "code": 0,
  "message": "success",
  "request_id": "6f6642eafac44c9489f1280bb2f16e1c",
  "data": {
    "timestamp": 1756742400000,
    "super_large": {
      "inflow_amount": 123456789.12,
      "outflow_amount": 100000000.00,
      "net_amount": 23456789.12
    },
    "large": {
      "inflow_amount": 86543210.50,
      "outflow_amount": 81234567.89,
      "net_amount": 5308642.61
    },
    "medium": {
      "inflow_amount": 45678901.23,
      "outflow_amount": 47890123.45,
      "net_amount": -2211222.22
    },
    "small": {
      "inflow_amount": 23456789.01,
      "outflow_amount": 26789012.34,
      "net_amount": -3332223.33
    }
  }
}
```

</details>

## fund

### 基金财务指标

`GET /api/fund/financials/indicators`

以下接口均使用完整 thscode 唯一定位基金，返回统一 { timestamp, item[] } 数据容器，timestamp 为接口响应时间戳。

**运行验证**：`verified_success`，`code=0`，success

**请求参数**

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|---|---|---|---|---|
| thscode | string | 是 | — | 完整基金 thscode，必须保留市场后缀。 |

**主要响应字段**

| 字段 | 类型 | 说明 |
|---|---|---|
| start_date_ms / end_date_ms / publish_date_ms | long | 报告期起止时间与发布日期。 |
| distribution_profit / current_profit / current_income | number | 可分配利润、本期利润与本期收入。 |
| distribution_share_profit | number | 每份可分配利润。 |
| average_nav_profit_margin / average_share_current_profit | number | 平均净值利润率与平均每份本期利润。 |
| share_nav / sum_share_nav | number | 单位净值与累计单位净值。 |
| asset_nav | number | 基金资产净值。 |
| sum_nav_rate / nav_rate | number | 累计净值增长率与净值增长率。 |

示例：`https://datahub.10jqka.com.cn/api/fund/financials/indicators?thscode=510300.SH`

<details>
<summary>响应示例</summary>

```json
{
  "code": 0,
  "message": "success",
  "request_id": "8e6d6e85c99447a2ae89e87b98aa9e7e",
  "data": {
    "timestamp": 1786690800000,
    "item": [
      {
        "start_date_ms": 1751328000000,
        "end_date_ms": 1759190400000,
        "publish_date_ms": 1760054400000,
        "distribution_profit": 1250000000.5,
        "current_profit": 1180000000.2,
        "share_nav": 4.753,
        "nav_rate": 3.21
      }
    ]
  }
}
```

</details>

### 基金利润表

`GET /api/fund/financials/income-statements`

以下接口均使用完整 thscode 唯一定位基金，返回统一 { timestamp, item[] } 数据容器，timestamp 为接口响应时间戳。

**运行验证**：`verified_success`，`code=0`，success

**请求参数**

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|---|---|---|---|---|
| thscode | string | 是 | — | 完整基金 thscode，必须保留市场后缀。 |

**主要响应字段**

| 字段 | 类型 | 说明 |
|---|---|---|
| start_date_ms / end_date_ms / publish_date_ms | long | 报告期起止时间与发布日期。 |
| income / total_income | number | 收入与收入合计。 |
| investment_income | number | 投资收益。 |
| stock_investment_income / bond_investment_income / fund_investment_income | number | 股票、债券与基金投资收益。 |
| dividend_income / interest_income | number | 股利与利息收入。 |
| fair_value_income / exchange_income / other_income | number | 公允价值、汇兑及其他收入。 |
| fee / total_fee | number | 费用与费用合计。 |
| manager_reward / custodian_fee / transaction_cost / tax_surcharge | number | 管理人报酬、托管费、交易成本与税费。 |
| total_profit / net_profit | number | 利润总额与净利润。 |

示例：`https://datahub.10jqka.com.cn/api/fund/financials/income-statements?thscode=510300.SH`

<details>
<summary>响应示例</summary>

```json
{
  "code": 0,
  "message": "success",
  "request_id": "5bbd57b24cdd41c9b30f50ca5a57df6c",
  "data": {
    "timestamp": 1786690800000,
    "item": [
      {
        "start_date_ms": 1751328000000,
        "end_date_ms": 1759190400000,
        "publish_date_ms": 1760054400000,
        "total_income": 1680000000.2,
        "total_fee": 320000000.4,
        "total_profit": 1360000000.8,
        "net_profit": 1360000000.8
      }
    ]
  }
}
```

</details>

### 基金资产负债表

`GET /api/fund/financials/balance-sheets`

以下接口均使用完整 thscode 唯一定位基金，返回统一 { timestamp, item[] } 数据容器，timestamp 为接口响应时间戳。

**运行验证**：`verified_success`，`code=0`，success

**请求参数**

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|---|---|---|---|---|
| thscode | string | 是 | — | 完整基金 thscode，必须保留市场后缀。 |

**主要响应字段**

| 字段 | 类型 | 说明 |
|---|---|---|
| start_date_ms / end_date_ms / publish_date_ms | long | 报告期起止时间与发布日期。 |
| total_assets | number | 资产总计。 |
| bank_deposit | number | 银行存款。 |
| fund_investment / stock_investment / bond_investment | number | 基金、股票与债券投资。 |
| transactional_financial_assets / other_assets | number | 交易性金融资产与其他资产。 |
| total_liability / other_liability | number | 负债合计与其他负债。 |
| owner_total_equity / undistributed_profit | number | 所有者权益与未分配利润。 |
| liability_and_owner_equity | number | 负债和所有者权益总计。 |

示例：`https://datahub.10jqka.com.cn/api/fund/financials/balance-sheets?thscode=510300.SH`

<details>
<summary>响应示例</summary>

```json
{
  "code": 0,
  "message": "success",
  "request_id": "aaf01838ef4e44eda1a89a8a750f6fb1",
  "data": {
    "timestamp": 1786690800000,
    "item": [
      {
        "start_date_ms": 1751328000000,
        "end_date_ms": 1759190400000,
        "publish_date_ms": 1760054400000,
        "total_assets": 168000000000.0,
        "total_liability": 1200000000.0,
        "owner_total_equity": 166800000000.0,
        "liability_and_owner_equity": 168000000000.0
      }
    ]
  }
}
```

</details>

### 基金股票持仓报告日期

`GET /api/fund/portfolio/stock-report-dates`

本页接口使用完整 thscode 唯一定位基金。历史持仓来自定期披露，不代表实时持仓。

**运行验证**：`verified_success`，`code=0`，success

**请求参数**

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|---|---|---|---|---|
| thscode | string | 是 | — | 完整基金 thscode。 |
| report_type | string | 否 | — | 报告类型。 |

**主要响应字段**

| 字段 | 类型 | 说明 |
|---|---|---|
| report_type | string | 报告类型。 |
| report_type_name | string | 报告类型中文名称。 |
| start_date_ms / end_date_ms | long | 报告期起止日期，毫秒 Unix 时间戳。 |

示例：`https://datahub.10jqka.com.cn/api/fund/portfolio/stock-report-dates?thscode=510300.SH&report_type=quarter`

<details>
<summary>响应示例</summary>

```json
{
  "code": 0,
  "message": "success",
  "request_id": "b134e73e088341a791a3194c57b5fb0b",
  "data": {
    "timestamp": 1786690800000,
    "item": [
      {
        "report_type": "quarter",
        "report_type_name": "季报",
        "start_date_ms": 1775001600000,
        "end_date_ms": 1782748800000
      }
    ]
  }
}
```

</details>

### 基金历史股票持仓

`GET /api/fund/portfolio/stock-history`

本页接口使用完整 thscode 唯一定位基金。历史持仓来自定期披露，不代表实时持仓。

**运行验证**：`verified_success`，`code=0`，success

**请求参数**

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|---|---|---|---|---|
| thscode | string | 是 | — | 完整基金 thscode。 |
| report_type | string | 是 | — | 报告类型。 |
| end_date | string | 是 | — | 报告截止日期，格式 yyyy-MM-dd。 |

**主要响应字段**

| 字段 | 类型 | 说明 |
|---|---|---|
| thscode / ticker / name | string | 持仓标的完整代码、纯代码与名称。 |
| asset_type | string | 资产类型，股票持仓为 stock。 |
| hold_ratio | number | 持仓占比，百分数原值。 |
| market_value | number | 持仓市值。 |
| period_increase_pct | number | 报告期增减比例，百分数原值。 |
| rank | integer \| null | 持仓排名；仅前十大持仓返回 1–10，其余持仓返回 null。 |
| report_type | string | 报告类型。 |
| end_date_ms | long | 报告截止日期，毫秒 Unix 时间戳。 |

示例：`https://datahub.10jqka.com.cn/api/fund/portfolio/stock-history?thscode=510300.SH&report_type=quarter&end_date=2026-06-30`

<details>
<summary>响应示例</summary>

```json
{
  "code": 0,
  "message": "success",
  "request_id": "e9738357ba1b4ec98849276fe5367a19",
  "data": {
    "timestamp": 1786690800000,
    "item": [
      {
        "thscode": "600519.SH",
        "ticker": "600519",
        "name": "贵州茅台",
        "asset_type": "stock",
        "hold_ratio": 4.67,
        "market_value": 123456789.12,
        "period_increase_pct": 0.12,
        "rank": 1,
        "report_type": "quarter",
        "end_date_ms": 1782748800000
      }
    ]
  }
}
```

</details>

### 基金历史债券持仓

`GET /api/fund/portfolio/bond-history`

本页接口使用完整 thscode 唯一定位基金。历史持仓来自定期披露，不代表实时持仓。

**运行验证**：`verified_success`，`code=0`，success

**请求参数**

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|---|---|---|---|---|
| thscode | string | 是 | — | 完整基金 thscode。 |
| report_type | string | 是 | — | 报告类型。 |
| end_date | string | 是 | — | 报告截止日期，格式 yyyy-MM-dd。 |

示例：`https://datahub.10jqka.com.cn/api/fund/portfolio/bond-history?thscode=510300.SH&report_type=quarter&end_date=2026-06-30`

<details>
<summary>响应示例</summary>

```json
{
  "code": 0,
  "message": "success",
  "request_id": "6816bf90628e49388d8e14adaf751bc6",
  "data": {
    "timestamp": 1786690800000,
    "item": [
      {
        "thscode": "019547.SH",
        "ticker": "019547",
        "name": "示例国债",
        "asset_type": "bond",
        "hold_ratio": 2.35,
        "market_value": 62500000.0,
        "period_increase_pct": -0.08,
        "rank": 1,
        "report_type": "quarter",
        "end_date_ms": 1782748800000
      }
    ]
  }
}
```

</details>

### 基金行业配置

`GET /api/fund/portfolio/industry-allocation`

本页接口使用完整 thscode 唯一定位基金。历史持仓来自定期披露，不代表实时持仓。

**运行验证**：`verified_success`，`code=0`，success

**请求参数**

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|---|---|---|---|---|
| thscode | string | 是 | — | 完整基金 thscode。 |

**主要响应字段**

| 字段 | 类型 | 说明 |
|---|---|---|
| report_period | string | 报告期。 |
| industry_name | string | 行业名称。 |
| ratio_pct | number | 行业配置比例，百分数原值。 |

示例：`https://datahub.10jqka.com.cn/api/fund/portfolio/industry-allocation?thscode=510300.SH`

<details>
<summary>响应示例</summary>

```json
{
  "code": 0,
  "message": "success",
  "request_id": "6999bcf53d024fabbba27486c8a421a4",
  "data": {
    "timestamp": 1786690800000,
    "item": [
      {
        "report_period": "2026Q2",
        "industry_name": "金融",
        "ratio_pct": 18.6
      }
    ]
  }
}
```

</details>

### 基金债券持仓报告日期

`GET /api/fund/portfolio/bond-report-dates`

本页接口使用完整 thscode 唯一定位基金。历史持仓来自定期披露，不代表实时持仓。

**运行验证**：`verified_success`，`code=0`，success

**请求参数**

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|---|---|---|---|---|
| thscode | string | 是 | — | 完整基金 thscode。 |
| report_type | string | 否 | — | 报告类型。 |

示例：`https://datahub.10jqka.com.cn/api/fund/portfolio/bond-report-dates?thscode=510300.SH&report_type=quarter`

<details>
<summary>响应示例</summary>

```json
{
  "code": 0,
  "message": "success",
  "request_id": "a5eaa47bf5bd4ff5b21e7235bb011123",
  "data": {
    "timestamp": 1786690800000,
    "item": [
      {
        "report_type": "quarter",
        "report_type_name": "季报",
        "start_date_ms": 1775001600000,
        "end_date_ms": 1782748800000
      }
    ]
  }
}
```

</details>

### 基金资产配置

`GET /api/fund/portfolio/asset-allocation`

本页接口使用完整 thscode 唯一定位基金。历史持仓来自定期披露，不代表实时持仓。

**运行验证**：`verified_success`，`code=0`，success

**请求参数**

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|---|---|---|---|---|
| thscode | string | 是 | — | 完整基金 thscode。 |

**主要响应字段**

| 字段 | 类型 | 说明 |
|---|---|---|
| report_date_ms | long | 报告日期，毫秒 Unix 时间戳。 |
| stock_ratio_pct | number | 股票资产占比，百分数原值。 |
| bond_ratio_pct | number | 债券资产占比，百分数原值。 |
| deposit_ratio_pct | number | 存款占比，百分数原值。 |
| other_ratio_pct | number | 其他资产占比，百分数原值。 |

示例：`https://datahub.10jqka.com.cn/api/fund/portfolio/asset-allocation?thscode=510300.SH`

<details>
<summary>响应示例</summary>

```json
{
  "code": 0,
  "message": "success",
  "request_id": "fb4a567d631a4fafbc9ac39f2a4cc264",
  "data": {
    "timestamp": 1786690800000,
    "item": [
      {
        "report_date_ms": 1782748800000,
        "stock_ratio_pct": 82.3,
        "bond_ratio_pct": 5.2,
        "deposit_ratio_pct": 8.1,
        "other_ratio_pct": 4.4
      }
    ]
  }
}
```

</details>

### 基金持有人结构

`GET /api/fund/holders/detail`

基金持有人结构

**运行验证**：`verified_success`，`code=0`，success

**请求参数**

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|---|---|---|---|---|
| thscode | string | 是 | — | 完整基金 thscode，必须保留市场后缀。 |
| merge_scope | enum | 否 | all | all（分别返回合并/独立份额的最新记录）/ merged（A/C 等份额合并披露）/ separate（当前份额独立披露）。 |

**主要响应字段**

| 字段 | 类型 | 说明 |
|---|---|---|
| merge_scope | string | 该条记录的实际披露口径：merged 或 separate。 |
| report_date_ms | integer | 该条记录的披露报告日，毫秒 Unix 时间戳。 |
| ins_position | number | 机构投资者占比，百分数原值。 |
| holder_amount | integer | 基金份额持有人户数。 |
| avg_holder_share | number | 平均每户持有基金份额。 |
| psnl_rate | number | 个人投资者占比，百分数原值。 |
| mgmt_staff_hold_rate | number | 管理人员工持有比例，百分数原值。 |

示例：`https://datahub.10jqka.com.cn/api/fund/holders/detail?thscode=161725.SZ&merge_scope=all`

<details>
<summary>响应示例</summary>

```json
{
  "code": 0,
  "message": "success",
  "request_id": "efcdf379c79349ec8a2eb7bdf0d27882",
  "data": {
    "timestamp": 1767110400000,
    "item": [
      {
        "merge_scope": "merged",
        "report_date_ms": 1609344000000,
        "ins_position": 0.1800,
        "holder_amount": 7058156,
        "avg_holder_share": 4819.4200,
        "psnl_rate": 99.8200,
        "mgmt_staff_hold_rate": 0.0062
      },
      {
        "merge_scope": "separate",
        "report_date_ms": 1767110400000,
        "ins_position": 0.9700,
        "holder_amount": 3951034,
        "avg_holder_share": 10159.8300,
        "psnl_rate": 99.0300,
        "mgmt_staff_hold_rate": 0.0097
      }
    ]
  }
}
```

</details>

### 基金前十大持有人

`GET /api/fund/holders/top`

基金前十大持有人

**运行验证**：`verified_success`，`code=0`，success

**请求参数**

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|---|---|---|---|---|
| thscode | string | 是 | — | 完整基金 thscode。 |
| limit | integer | 否 | 服务端默认 | 返回条数，最大为 10。 |

**主要响应字段**

| 字段 | 类型 | 说明 |
|---|---|---|
| timestamp | long | 接口响应时间戳，毫秒 Unix 时间戳。 |
| limit | integer | 服务端实际采用的返回条数上限。 |
| holder_id / holder_code | string | 持有人 ID 与代码。 |
| holder_name | string | 持有人名称。 |
| holder_type | string | 持有人类型。 |
| rank | integer | 持有排名。 |
| hold_share | number | 持有份额。 |
| hold_rate_pct | number | 持有比例，百分数原值。 |
| report_date_ms / publish_date_ms | long | 报告日与发布日期，毫秒 Unix 时间戳。 |

示例：`https://datahub.10jqka.com.cn/api/fund/holders/top?thscode=510300.SH&limit=10`

<details>
<summary>响应示例</summary>

```json
{
  "code": 0,
  "message": "success",
  "request_id": "e4a3af1cf0b14210b98d023297740324",
  "data": {
    "timestamp": 1786690800000,
    "limit": 10,
    "item": [
      {
        "holder_id": "holder-001",
        "holder_code": "H001",
        "holder_name": "示例持有人",
        "holder_type": "institution",
        "rank": 1,
        "hold_share": 125000000,
        "hold_rate_pct": 8.25,
        "report_date_ms": 1785513600000,
        "publish_date_ms": 1786118400000
      }
    ]
  }
}
```

</details>

### 基金分红记录

`GET /api/fund/corporate-actions/dividends`

基金分红记录

**运行验证**：`verified_success`，`code=0`，success

**请求参数**

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|---|---|---|---|---|
| thscode | string | 是 | — | 完整基金 thscode。 |

**主要响应字段**

| 字段 | 类型 | 说明 |
|---|---|---|
| timestamp | long | 接口响应时间戳，毫秒 Unix 时间戳。 |
| dividend_count | integer | 返回的分红记录总数。 |
| dividend_total | number | 服务端返回的累计分红汇总值；不要与每 10 份现金分红混用。 |
| per_ten_cash_before_tax / per_ten_cash_after_tax | number | 每 10 份税前/税后现金分红。 |
| progress | string | 分红进度。 |
| publish_date_ms / registration_date_ms / ex_dividend_date_ms | long | 公告日、权益登记日与除息日。 |
| payment_date_ms / reinvestment_date_ms | long | 派息日与红利再投资日。 |
| profit_base_date_ms / in_dividend_date_ms | long | 收益基准日及分红相关日期。 |

示例：`https://datahub.10jqka.com.cn/api/fund/corporate-actions/dividends?thscode=510300.SH`

<details>
<summary>响应示例</summary>

```json
{
  "code": 0,
  "message": "success",
  "request_id": "40ca837351bd497f99348b04ffc5c9af",
  "data": {
    "timestamp": 1786690800000,
    "dividend_count": 1,
    "dividend_total": 0.8,
    "item": [
      {
        "per_ten_cash_before_tax": 0.8,
        "per_ten_cash_after_tax": 0.8,
        "progress": "实施",
        "publish_date_ms": 1764547200000,
        "registration_date_ms": 1765152000000,
        "ex_dividend_date_ms": 1765238400000,
        "payment_date_ms": 1765324800000,
        "reinvestment_date_ms": 1765324800000,
        "profit_base_date_ms": 1764460800000,
        "in_dividend_date_ms": 1765324800000
      }
    ]
  }
}
```

</details>

### 基金公司详情

`GET /api/fund/companies/detail`

基金公司详情

**运行验证**：`verified_success`，`code=0`，success

**请求参数**

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|---|---|---|---|---|
| company_id | string | 是 | — | 基金公司 ID，可从基金基本资料的 company_id 获取。 |

**主要响应字段**

| 字段 | 类型 | 说明 |
|---|---|---|
| company_id | string | 基金公司 ID。 |
| company_name | string | 基金公司名称。 |
| company_type | string | 基金公司类型。 |
| established_date_ms | long | 成立日期，毫秒 Unix 时间戳。 |
| fund_count | integer | 公司旗下基金数量。 |
| scale | number | 公司管理规模。 |

示例：`https://datahub.10jqka.com.cn/api/fund/companies/detail?company_id=00089990`

<details>
<summary>响应示例</summary>

```json
{
  "code": 0,
  "message": "success",
  "request_id": "3193d28e58b1477cb41ff1780d0c627d",
  "data": {
    "timestamp": 1787140798465,
    "item": [
      {
        "company_id": "00089990",
        "company_name": "华泰柏瑞基金管理有限公司",
        "company_type": "基金管理公司",
        "established_date_ms": 1100707200000,
        "fund_count": 356,
        "scale": 621043562116.96
      }
    ]
  }
}
```

</details>

### 基金基本资料

`GET /api/fund/profile/detail`

基金基本资料

**运行验证**：`verified_success`，`code=0`，success

**请求参数**

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|---|---|---|---|---|
| thscode | string | 是 | — | 完整基金 thscode，必须保留市场后缀，如 025480.OF / 510300.SH。 |

**主要响应字段**

| 字段 | 类型 | 说明 |
|---|---|---|
| thscode | string | 带市场后缀的同花顺代码。 |
| ticker | string | 纯基金代码，仅用于展示。 |
| fund_name | string \| null | 基金名称。 |
| estab_date | long \| null | 成立日期，毫秒时间戳。 |
| company_id | string \| null | 基金公司 ID，可用于查询基金公司详情。 |
| mgmt_name | string \| null | 基金管理人名称。 |
| manager_name | string \| null | 基金经理姓名。 |
| fund_scale | number \| null | 基金规模。 |
| unit_nav | number \| null | 单位净值。 |
| manager_info | array | 基金经理引用，包含经理 ID、姓名、任职收益、任职天数与起止时间。 |
| trade_rule | array | 交易规则，包含标题、展示时间与毫秒时间戳。 |
| rate_info | array | 费率信息，包含费率类型、收费模式、条件、标准费率与优惠费率。 |

示例：`https://datahub.10jqka.com.cn/api/fund/profile/detail?thscode=025480.OF`

<details>
<summary>响应示例</summary>

```json
{
  "code": 0,
  "message": "success",
  "request_id": "353e202c28494f8f98bef62d83dbfcaf",
  "data": {
    "timestamp": 1784210313786,
    "item": [
      {
        "thscode": "025480.OF",
        "ticker": "025480",
        "fund_name": "沪深300A",
        "estab_date": 1767024000000,
        "company_id": "80000222",
        "mgmt_name": "华夏基金管理有限公司",
        "manager_name": "靖博灵",
        "fund_scale": 1234567890.12,
        "unit_nav": 1.2345,
        "manager_info": [],
        "trade_rule": [],
        "rate_info": []
      }
    ]
  }
}
```

</details>

### 从业经历

`GET /api/fund/managers/experience`

基金经理接口使用从基金基本资料中取得的 manager_id。

**运行验证**：`verified_success`，`code=0`，success

**请求参数**

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|---|---|---|---|---|
| manager_id | string | 是 | — | 基金经理 ID。 |

**主要响应字段**

| 字段 | 类型 | 说明 |
|---|---|---|
| awards | array \| object \| null | 获奖经历，保留上游结构；已验证样例返回数组。 |
| heavy_assets | object | 代表性重仓资产，保留上游结构。 |
| investment_history | object | 投资与从业经历，保留上游结构。 |

示例：`https://datahub.10jqka.com.cn/api/fund/managers/experience?manager_id=H000200384`

<details>
<summary>响应示例</summary>

```json
{
  "code": 0,
  "message": "success",
  "request_id": "4b211e1309d441db9b243cfc30a2556e",
  "data": {
    "timestamp": 1787140798437,
    "item": [
      {
        "awards": null,
        "heavy_assets": {
          "stock": [
            {
              "trade_name": "贵州茅台",
              "trade_code": "600519",
              "market_value": 2403228884.47,
              "scale": 1.92
            }
          ]
        },
        "investment_history": {
          "460300": {
            "code": "460300",
            "name": "华泰柏瑞沪深300ETF联接A",
            "start": "2012-05-29",
            "end": "至今"
          }
        }
      }
    ]
  }
}
```

</details>

### 基金经理详情

`GET /api/fund/managers/detail`

基金经理接口使用从基金基本资料中取得的 manager_id。

**运行验证**：`verified_success`，`code=0`，success

**请求参数**

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|---|---|---|---|---|
| manager_id | string | 是 | — | 基金经理 ID。 |

**主要响应字段**

| 字段 | 类型 | 说明 |
|---|---|---|
| manager_id / manager_name | string | 基金经理 ID 与姓名。 |
| sex / degree | string \| null | 性别与学历。 |
| company_id / company_name | string \| null | 所属基金公司 ID 与名称。 |
| resume / photo_url | string \| null | 履历与头像链接。 |
| annual_return_pct / maximum_return_pct | number \| null | 年化收益率与最大收益率。 |
| radar_comparison | array | 雷达图对比数据。 |

示例：`https://datahub.10jqka.com.cn/api/fund/managers/detail?manager_id=H000200384`

<details>
<summary>响应示例</summary>

```json
{
  "code": 0,
  "message": "success",
  "request_id": "4d1f41d3e8084e57ae45bd03e3a6a331",
  "data": {
    "timestamp": 1787140798517,
    "item": [
      {
        "manager_id": "H000200384",
        "manager_name": "柳军",
        "sex": "m",
        "degree": null,
        "company_id": "00089990",
        "company_name": "华泰柏瑞基金管理有限公司",
        "photo_url": "https://fund.10jqka.com.cn/photos/20210702,etool_11214328996.jpg",
        "annual_return_pct": 0.05096597,
        "maximum_return_pct": -0.45588366644825656
      }
    ]
  }
}
```

</details>

### 基金经理业绩

`GET /api/fund/managers/performance`

基金经理接口使用从基金基本资料中取得的 manager_id。

**运行验证**：`verified_success`，`code=0`，success

**请求参数**

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|---|---|---|---|---|
| manager_id | string | 是 | — | 基金经理 ID。 |
| range | enum | 是 | — | month / tmonth / year / nowyear / now。 |

**主要响应字段**

| 字段 | 类型 | 说明 |
|---|---|---|
| date_ms | long | 数据日期，毫秒 Unix 时间戳。 |
| manager_return_pct | number | 基金经理收益率，百分数原值。 |
| peer_return_pct | number | 同类收益率，百分数原值。 |
| benchmark_return_pct | number | 基准收益率，百分数原值。 |

示例：`https://datahub.10jqka.com.cn/api/fund/managers/performance?manager_id=H000200384&range=year`

<details>
<summary>响应示例</summary>

```json
{
  "code": 0,
  "message": "success",
  "request_id": "89385428873f44a98cc27530b88c01c2",
  "data": {
    "timestamp": 1787140798642,
    "item": [
      {
        "date_ms": 1774281600000,
        "manager_return_pct": 2.2001672,
        "peer_return_pct": 5.75548505,
        "benchmark_return_pct": 4474.72
      }
    ]
  }
}
```

</details>

### 投资风格

`GET /api/fund/managers/investment-style`

基金经理接口使用从基金基本资料中取得的 manager_id。

**运行验证**：`verified_success`，`code=0`，success

**请求参数**

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|---|---|---|---|---|
| manager_id | string | 是 | — | 基金经理 ID。 |

**主要响应字段**

| 字段 | 类型 | 说明 |
|---|---|---|
| representative_fund_thscode / representative_fund_ticker | string \| null | 代表基金完整代码与纯代码。 |
| representative_fund_name | string \| null | 代表基金名称。 |
| investment_idea | string \| null | 投资理念。 |
| total_fund_scale | number \| null | 管理基金总规模。 |
| industry_preferences | array \| object \| null | 行业偏好，保留上游结构；已验证样例返回年度记录数组。 |

示例：`https://datahub.10jqka.com.cn/api/fund/managers/investment-style?manager_id=H000200384`

<details>
<summary>响应示例</summary>

```json
{
  "code": 0,
  "message": "success",
  "request_id": "46fded1c293c473a8b406fafe60d4b6b",
  "data": {
    "timestamp": 1787140798489,
    "item": [
      {
        "representative_fund_thscode": "510300.SH",
        "representative_fund_ticker": "510300",
        "representative_fund_name": "华泰柏瑞沪深300ETF",
        "investment_idea": null,
        "total_fund_scale": null,
        "industry_preferences": [
          {
            "report_tag": "2022",
            "percent": [
              0.07,
              0.26,
              0.11,
              0.27,
              0.05,
              0,
              0.23
            ],
            "total_fund_scale": 23304220274.36
          }
        ]
      }
    ]
  }
}
```

</details>

### 基金净值

`GET /api/fund/performance/nav`

基金净值

**运行验证**：`verified_success`，`code=0`，success

**请求参数**

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|---|---|---|---|---|
| thscode | string | 是 | — | 完整基金 thscode，必须保留市场后缀。 |
| range | string | 否 | 最新一条 | week / month / tmonth / hyear / year / twoyear / tyear / fyear。 |
| nav_type | string | 否 | unit,adj | unit（单位净值）/ adj（复权净值）/ unit,adj（同时返回）。 |

**主要响应字段**

| 字段 | 类型 | 说明 |
|---|---|---|
| nav_date | long | 净值日期，毫秒级 Unix 时间戳。 |
| unit_nav | number | 单位净值；未通过 nav_type 请求时不输出。 |
| adj_nav | number | 复权净值；未通过 nav_type 请求时不输出，不等同于累计净值。 |

示例：`https://datahub.10jqka.com.cn/api/fund/performance/nav?thscode=510300.SH&range=year&nav_type=unit`

<details>
<summary>响应示例</summary>

```json
{
  "code": 0,
  "message": "success",
  "request_id": "97634b0fbf4746afaa32e8a71adbd636",
  "data": {
    "timestamp": 1784131200000,
    "item": [
      {
        "nav_date": 1752595200000,
        "unit_nav": 4.0713
      },
      {
        "nav_date": 1752681600000,
        "unit_nav": 4.1015
      }
    ]
  }
}
```

</details>

### 基金历史业绩指标

`GET /api/fund/performance/indicators-historical`

基金历史业绩指标

**运行验证**：`verified_success`，`code=0`，success

**请求参数**

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|---|---|---|---|---|
| thscode | string | 是 | — | 完整基金 thscode。 |
| start | long | 是 | — | 起始时间，毫秒 Unix 时间戳。 |
| end | long | 是 | — | 结束时间，毫秒 Unix 时间戳。 |

**主要响应字段**

| 字段 | 类型 | 说明 |
|---|---|---|
| date_ms | long | 指标日期，毫秒 Unix 时间戳。 |
| rsi_pct | number | 净值波动（RSI）指标值。 |
| donchian_channel | number | 趋势强弱（唐奇安通道）指标值。 |
| track_index_pe_ttm_five_year_percentile | number | 估值百分位（跟踪指数 PE TTM 五年分位）。 |

示例：`https://datahub.10jqka.com.cn/api/fund/performance/indicators-historical?thscode=510300.SH&start=1735689600000&end=1767225599000`

<details>
<summary>响应示例</summary>

```json
{
  "code": 0,
  "message": "success",
  "request_id": "046f8a0b787c44a7b995c568096fa16c",
  "data": {
    "timestamp": 1767225599000,
    "item": [
      {
        "date_ms": 1767139200000,
        "rsi_pct": 53.8,
        "donchian_channel": 0.42,
        "track_index_pe_ttm_five_year_percentile": 61.3
      }
    ]
  }
}
```

</details>

### 基金区间收益

`GET /api/fund/performance/returns`

基金区间收益

**运行验证**：`verified_success`，`code=0`，success

**请求参数**

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|---|---|---|---|---|
| thscode | string | 是 | — | 完整基金 thscode，必须保留市场后缀。 |

**主要响应字段**

| 字段 | 类型 | 说明 |
|---|---|---|
| return_month | number | 近一月收益率，百分数原值。 |
| return_week | number | 近一周收益率，百分数原值。 |
| return_tmonth | number | 近三月收益率，百分数原值。 |
| return_hyear | number | 近半年收益率，百分数原值。 |
| return_year | number | 近一年收益率，百分数原值。 |
| return_twoyear | number | 近两年收益率，百分数原值。 |
| return_tyear | number | 近三年收益率，百分数原值。 |
| return_fyear | number | 近五年收益率，百分数原值。 |
| return_nowyear | number | 今年以来收益率，百分数原值。 |
| return_now | number | 成立以来收益率，百分数原值。 |
| peer_average_* | number | 对应周期的同类平均收益率；周期后缀覆盖 week、month、tmonth、hyear、year、twoyear、tyear、fyear。 |
| rank_* / rank_total_* | integer | 对应周期的同类排名与参与排名总数。 |

示例：`https://datahub.10jqka.com.cn/api/fund/performance/returns?thscode=510300.SH`

<details>
<summary>响应示例</summary>

```json
{
  "code": 0,
  "message": "success",
  "request_id": "61cb2a8b9340483aaf00e36748f77918",
  "data": {
    "timestamp": 0,
    "item": [
      {
        "return_month": -3.33,
        "return_tmonth": 0.03,
        "return_hyear": 0.19,
        "return_year": 19.66,
        "return_tyear": 28.69,
        "return_fyear": 1.77,
        "return_nowyear": 2.49,
        "return_now": 121.58
      }
    ]
  }
}
```

</details>

### 基金最大回撤

`GET /api/fund/performance/drawdowns`

基金最大回撤

**运行验证**：`verified_success`，`code=0`，success

**请求参数**

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|---|---|---|---|---|
| thscode | string | 是 | — | 完整基金 thscode。 |

**主要响应字段**

| 字段 | 类型 | 说明 |
|---|---|---|
| thscode / ticker | string | 完整基金代码与纯代码。 |
| week / month / tmonth | number | 近一周、近一月、近三月最大回撤。 |
| hyear / year / twoyear | number | 近半年、近一年、近两年最大回撤。 |
| tyear / fyear | number | 近三年、近五年最大回撤。 |
| nowyear / now | number | 今年以来、成立以来最大回撤。 |

示例：`https://datahub.10jqka.com.cn/api/fund/performance/drawdowns?thscode=510300.SH`

<details>
<summary>响应示例</summary>

```json
{
  "code": 0,
  "message": "success",
  "request_id": "7c7fdfe771fc4c61bbab8410a250b61e",
  "data": {
    "timestamp": 1786690800000,
    "item": [
      {
        "thscode": "510300.SH",
        "ticker": "510300",
        "week": -1.2,
        "month": -3.6,
        "tmonth": -6.8,
        "hyear": -9.1,
        "year": -12.5,
        "twoyear": -18.4,
        "tyear": -21.7,
        "fyear": -28.9,
        "nowyear": -7.3,
        "now": -31.2
      }
    ]
  }
}
```

</details>

### 基金募集列表

`GET /api/fund/offerings/list`

基金募集列表

**运行验证**：`verified_success`，`code=0`，success

**请求参数**

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|---|---|---|---|---|
| subscribe | enum | 是 | — | active（当前募集）或 upcoming（即将募集）。 |

**主要响应字段**

| 字段 | 类型 | 说明 |
|---|---|---|
| thscode | string | 完整基金 thscode。 |
| ticker | string | 纯基金代码。 |
| subscription_start_ms | long | 募集开始时间，毫秒 Unix 时间戳。 |
| subscription_end_ms | long | 募集结束时间，毫秒 Unix 时间戳。 |

示例：`https://datahub.10jqka.com.cn/api/fund/offerings/list?subscribe=active`

<details>
<summary>响应示例</summary>

```json
{
  "code": 0,
  "message": "success",
  "request_id": "78ae6cdd0e384175a669dcf11a36a4da",
  "data": {
    "timestamp": 1786690800000,
    "item": [
      {
        "thscode": "025480.OF",
        "ticker": "025480",
        "subscription_start_ms": 1786579200000,
        "subscription_end_ms": 1787184000000
      }
    ]
  }
}
```

</details>

### 场内基金历史日线行情

`GET /api/fund/market/historical`

仅支持 ETF；单次只允许一个 thscode，查询窗口最长 5 个自然年。价格数据采用前复权口径。

**运行验证**：`verified_success`，`code=0`，success

**请求参数**

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|---|---|---|---|---|
| thscode | string | 是 | — | 单只 ETF 的完整 thscode，必须保留市场后缀；不接受逗号分隔的多个值。 |
| interval | string | 否 | 1d | K 线周期，当前仅支持 1d（日线）。 |
| start | long | 是 | — | 起始时间，毫秒级 Unix 时间戳。 |
| end | long | 是 | — | 结束时间，毫秒级 Unix 时间戳；必须不早于 start，且窗口最长 5 个自然年。 |

**主要响应字段**

| 字段 | 类型 | 说明 |
|---|---|---|
| timestamp | long | 数据就绪时间，取序列中最新一根 K 线的有效时间。 |
| thscode | string | 请求中的 ETF thscode。 |
| interval | string | K 线周期，固定为 1d。 |
| adjust | null | 当前固定为 null；价格数据仍采用前复权口径。 |
| item | array | 历史日线数据列表。 |
| date_ms | long | 交易日期，毫秒级 Unix 时间戳。 |
| open_price | number | 前复权开盘价。 |
| high_price | number | 前复权最高价。 |
| low_price | number | 前复权最低价。 |
| close_price | number | 前复权收盘价。 |
| volume | number | 成交量。 |
| turnover | number | 成交额。 |

示例：`https://datahub.10jqka.com.cn/api/fund/market/historical?thscode=510300.SH&interval=1d&start=1626451200000&end=1784217600000`

<details>
<summary>响应示例</summary>

```json
{
  "code": 0,
  "message": "success",
  "request_id": "f47444ed0e0d4e1c883ecb66511dc311",
  "data": {
    "timestamp": 1784131200000,
    "thscode": "510300.SH",
    "interval": "1d",
    "adjust": null,
    "item": [
      {
        "date_ms": 1626624000000,
        "volume": 332046160,
        "turnover": 1709347700,
        "open_price": 4.728,
        "high_price": 4.769,
        "low_price": 4.687,
        "close_price": 4.759
      },
      {
        "date_ms": 1626710400000,
        "volume": 306679330,
        "turnover": 1581145200,
        "open_price": 4.721,
        "high_price": 4.76,
        "low_price": 4.712,
        "close_price": 4.746
      }
    ]
  }
}
```

</details>

### 场内基金行情快照

`GET /api/fund/market/snapshot`

支持 ETF 和 LOF。场外基金、REITs 或尚未开放的基金叶子类型返回 code=3004；支持的标的尚无可用快照时返回 code=3002。

**运行验证**：`verified_success`，`code=0`，success

**请求参数**

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|---|---|---|---|---|
| thscode | string | 是 | — | 单只 ETF 或 LOF 的完整 thscode，必须保留市场后缀，如 510300.SH、161725.SZ；不接受逗号分隔的多个值。 |

**主要响应字段**

| 字段 | 类型 | 说明 |
|---|---|---|
| thscode | string | ETF 或 LOF 的完整 thscode。 |
| ticker | string | ETF 或 LOF 的纯基金代码，仅用于展示。 |
| last_price | number | 最新价。 |
| open_price | number | 开盘价。 |
| high_price | number | 最高价。 |
| low_price | number | 最低价。 |
| prev_price | number | 昨收价。 |
| price_change_ratio_pct | number | 涨跌幅，百分数原值。 |
| price_change | number | 涨跌额。 |
| price_amplitude_ratio_pct | number | 振幅，百分数原值。 |
| volume | number | 成交量。 |
| turnover | number | 成交额。 |
| turnover_ratio_pct | number | 换手率，百分数原值。 |

示例：`https://datahub.10jqka.com.cn/api/fund/market/snapshot?thscode=510300.SH`

<details>
<summary>响应示例</summary>

```json
{
  "code": 0,
  "message": "success",
  "request_id": "558cdc5105964a93953b1a541e7af901",
  "data": {
    "timestamp": 1784210584000,
    "item": [
      {
        "thscode": "510300.SH",
        "ticker": "510300",
        "last_price": 4.753,
        "open_price": 4.775,
        "high_price": 4.825,
        "low_price": 4.724,
        "prev_price": 4.838,
        "price_change_ratio_pct": -1.756924,
        "price_change": -0.085,
        "price_amplitude_ratio_pct": 2.08764,
        "volume": 1657822800,
        "turnover": 7909234100,
        "turnover_ratio_pct": 9.012068
      }
    ]
  }
}
```

</details>

### 基金回测可用指标

`GET /api/fund/backtest/indicators`

基金回测可用指标

**运行验证**：`verified_success`，`code=0`，success

**请求参数**

| 参数 | 位置 | 类型 | 必需 | 说明 | 默认值 |
|---|---|---|---|---|---|
| - | - | - | - | 无业务参数。 | - |

**主要响应字段**

| 字段 | 类型 | 说明 |
|---|---|---|
| id | number | 指标标识。 |
| indicator_name | string | 指标名称。 |
| indicator_code | string | 指标编码。 |
| type | number | 上游定义的指标类型。 |
| value_kind | number | 上游定义的指标值类型。 |
| support_operation | string | 支持的条件操作符。 |
| unit | string \| null | 指标单位。 |
| description | string \| null | 指标说明。 |
| state_rules | string \| null | 状态规则。 |
| create_time | string | 上游记录创建时间，使用 ISO 本地日期时间。 |
| update_time | string | 上游记录更新时间，使用 ISO 本地日期时间。 |

示例：`https://datahub.10jqka.com.cn/api/fund/backtest/indicators`

<details>
<summary>响应示例</summary>

```json
{
  "code": 0,
  "message": "success",
  "request_id": "af1c4ed643f744218950885dd58bd2c9",
  "data": [
    {
      "id": 1,
      "indicator_name": "净值波动",
      "indicator_code": "rsi_pct",
      "type": 0,
      "value_kind": 0,
      "support_operation": ">,<",
      "unit": null,
      "description": null,
      "state_rules": null,
      "create_time": "2026-05-27T16:57:32",
      "update_time": "2026-05-27T16:57:32"
    }
  ]
}
```

</details>

### 基金在线回测

`GET /api/fund/backtest/result`

基金在线回测

**运行验证**：`verified_success`，`code=0`，success

**请求参数**

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|---|---|---|---|---|
| thscode | string | 是 | — | 含市场后缀的完整基金代码，例如 000001.OF。 |
| buy_conditions | string | 是 | — | 买入条件 JSON 字符串，必须是对象或数组。 |
| sell_conditions | string | 是 | — | 卖出条件 JSON 字符串，必须是对象或数组。 |
| buy_frequency_type | string | 是 | — | 买入频率，具体值由上游判定。 |
| max_buy_times | number | 是 | — | 最大买入次数。 |
| per_buy_amount | number | 是 | — | 每次买入金额。 |

**主要响应字段**

| 字段 | 类型 | 说明 |
|---|---|---|
| start_date | string | 回测开始日期。 |
| end_date | string | 回测结束日期。 |
| metrics | object | 回测指标。 |
| trade_count | number | 交易次数。 |
| trades | array | 交易明细。 |
| curve_points | JSON | 收益曲线点集合，兼容数组或对象结构。 |
| strategy_return | number | 策略收益。 |
| fund_return | number | 基金收益。 |
| excess_return | number | 超额收益。 |
| win_rate | number | 胜率。 |
| max_drawdown | number | 最大回撤。 |
| trade_date | string | 交易日期。 |
| type | string | 交易类型。 |
| price | number | 交易价格。 |
| amount | number | 交易金额。 |
| shares | number | 交易份额。 |
| profit | number \| null | 交易收益。 |

示例：`https://datahub.10jqka.com.cn/api/fund/backtest/result?thscode=000001.OF&buy_conditions=%7B%22indicator_code%22%3A%22rsi_pct%22%2C%22operator%22%3A%22%3E%22%2C%22value%22%3A0.5%7D&sell_conditions=%7B%22indicator_code%22%3A%22rsi_pct%22%2C%22operator%22%3A%22%3C%22%2C%22value%22%3A0.3%7D&buy_frequency_type=WEEKLY&max_buy_times=5&per_buy_amount=100`

<details>
<summary>响应示例</summary>

```json
{
  "code": 0,
  "message": "success",
  "request_id": "5fbc0c2db60a4e298a0d48c4de049642",
  "data": {
    "start_date": "2023-09-08",
    "end_date": "2026-09-08",
    "metrics": {
      "strategy_return": 0.422452870829321,
      "fund_return": 0.4099340336826627,
      "excess_return": 0.0125188371466583,
      "win_rate": 0,
      "max_drawdown": 0.2700061087331572
    },
    "trade_count": 726,
    "trades": [
      {
        "trade_date": "2023-09-11",
        "type": "BUY",
        "price": 5.8066057624,
        "amount": 100,
        "shares": 17.22176501934028,
        "profit": null
      }
    ],
    "curve_points": [
      {
        "2023-09-08": 0
      }
    ]
  }
}
```

</details>

### 基金诊断详情

`GET /api/fund/diagnostics/detail`

基金诊断详情

**运行验证**：`verified_success`，`code=0`，success

**请求参数**

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|---|---|---|---|---|
| thscode | string | 是 | — | 完整基金 thscode。 |

**主要响应字段**

| 字段 | 类型 | 说明 |
|---|---|---|
| thscode | string | 完整基金 thscode。 |
| ticker | string | 纯基金代码。 |
| fund_type | string | 基金类型。 |
| peer_code | string | 同类比较分组代码。 |
| dimensions / peer_dimensions | object | 基金诊断维度及同类对比数据，保留上游结构。 |
| probabilities / ranges | object | 概率与区间数据，保留上游结构。 |
| resilience / peer_resilience | object | 基金韧性及同类韧性数据，保留上游结构。 |

示例：`https://datahub.10jqka.com.cn/api/fund/diagnostics/detail?thscode=510300.SH`

<details>
<summary>响应示例</summary>

```json
{
  "code": 0,
  "message": "success",
  "request_id": "5fbfa0f95b854564bc40dfa027868544",
  "data": {
    "timestamp": 1786690800000,
    "item": [
      {
        "thscode": "510300.SH",
        "ticker": "510300",
        "fund_type": "exchange",
        "peer_code": "ETF-INDEX",
        "dimensions": {},
        "peer_dimensions": {},
        "probabilities": {},
        "ranges": {},
        "resilience": {},
        "peer_resilience": {}
      }
    ]
  }
}
```

</details>

### 基金重仓持仓

`GET /api/fund/portfolio/holdings`

持仓来自定期披露，不代表实时持仓。返回可同时包含股票、债券和基金资产。

**运行验证**：`verified_success`，`code=0`，success

**请求参数**

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|---|---|---|---|---|
| thscode | string | 是 | — | 完整基金 thscode，必须保留市场后缀，如 025480.OF。 |

**主要响应字段**

| 字段 | 类型 | 说明 |
|---|---|---|
| thscode | string | 持仓股票的完整 thscode。 |
| ticker | string | 持仓股票的纯代码。 |
| stock_name | string | 资产名称；字段名为兼容既有契约而保留。 |
| hold_ratio | number | 占基金净值比例的百分数原值。 |
| asset_type | string | 资产类型，如 stock / bond / fund。 |
| position_capital / position_count | number | 持仓市值与持仓数量。 |
| security_market_value_rate_pct / period_increase_rate_pct | number | 证券市值占比与报告期增减比例。 |
| investment_rank | integer | 持仓排名。 |
| start_date_ms / end_date_ms / publish_date_ms / modify_time_ms | long | 报告期、发布日期与修改时间。 |

示例：`https://datahub.10jqka.com.cn/api/fund/portfolio/holdings?thscode=025480.OF`

<details>
<summary>响应示例</summary>

```json
{
  "code": 0,
  "message": "success",
  "request_id": "0045aff2514c4e098212db69f88a5fa5",
  "data": {
    "timestamp": 0,
    "item": [
      {
        "thscode": "300750.SZ",
        "ticker": "300750",
        "stock_name": "宁德时代",
        "hold_ratio": 4.67,
        "asset_type": "stock",
        "position_capital": 123456789.12,
        "position_count": 1234567,
        "security_market_value_rate_pct": 4.67,
        "period_increase_rate_pct": 0.12,
        "investment_rank": 1,
        "end_date_ms": 1785513600000
      }
    ],
    "total_stock_ratio_pct": 82.3,
    "total_bond_ratio_pct": 5.2,
    "total_fund_ratio_pct": 0,
    "turnover_rate_pct": 96.4,
    "stock_ratio_pct": 82.3,
    "main_industry": "电子",
    "concentration_ratio": 48.6
  }
}
```

</details>

### 基金资讯列表

`GET /api/fund/news/article-list`

基金资讯列表

**运行验证**：`verified_success`，`code=0`，success

**请求参数**

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|---|---|---|---|---|
| thscode | string | 是 | — | 完整基金 thscode。 |
| limit | integer | 否 | 服务端默认 | 返回条数。 |
| offset | string | 否 | — | 不透明翻页游标；下一页应原样回传上一页的 data.offset。 |

**主要响应字段**

| 字段 | 类型 | 说明 |
|---|---|---|
| timestamp | long | 接口响应时间戳。 |
| limit | integer | 本页返回条数上限。 |
| offset | string \| null | 下一页游标；继续翻页时原样回传。 |
| has_more | boolean | 是否还有下一页；分页结束统一以该字段为准。 |
| item | array | 资讯明细列表。 |
| id | string | 资讯 ID。 |
| content_type | string | 内容类型。 |
| title / summary | string | 标题与摘要。 |
| source / author | string | 来源与作者。 |
| url / image_url | string \| null | 正文链接与图片链接。 |
| publish_time_ms | long | 发布时间，毫秒 Unix 时间戳。 |
| top | boolean | 是否置顶。 |

示例：`https://datahub.10jqka.com.cn/api/fund/news/article-list?thscode=510300.SH&limit=20`

<details>
<summary>响应示例</summary>

```json
{
  "code": 0,
  "message": "success",
  "request_id": "4132cc25f7be4c70aa490ef02b8a66bf",
  "data": {
    "timestamp": 1786690800000,
    "limit": 20,
    "offset": "next-page-cursor",
    "has_more": false,
    "item": [
      {
        "id": "article-001",
        "content_type": "news",
        "title": "基金资讯标题",
        "summary": "基金资讯摘要",
        "source": "公开资讯",
        "url": "https://example.com/article-001",
        "image_url": null,
        "author": "编辑部",
        "publish_time_ms": 1786687200000,
        "top": false
      }
    ]
  }
}
```

</details>

### 宽基ETF申购净流入

`GET /api/fund/etf-flow/net-inflow-historical`

查询宽基ETF申购净流入日统计，返回实际可用时间窗口；金额保留负值和 null。日统计按 T+1 次日更新约定提供，具体可用日以返回窗口为准。

**运行验证**：`verified_success`，`code=0`，success

**请求参数**：无业务参数。

**主要响应字段**

| 字段 | 类型 | 说明 |
|---|---|---|
| timestamp | integer | 采样时间；单位：毫秒 |
| available_start_date | date | 本份返回序列最早日期 |
| available_end_date | date | 本份返回序列最晚日期，金额可能未准备 |
| item | array | 业务记录列表 |
| date_ms | integer | 业务所属日期零点；单位：毫秒 |
| net_inflow | number \| null | 业务口径日统计净流入；保留负值与null；单位：元 |

示例：`https://datahub.10jqka.com.cn/api/fund/etf-flow/net-inflow-historical`

<details>
<summary>响应示例</summary>

```json
{
  "code": 0,
  "message": "success",
  "request_id": "example-request",
  "data": {
    "timestamp": 1791957420054,
    "available_start_date": "2026-07-14",
    "available_end_date": "2026-10-13",
    "item": [
      {
        "date_ms": 1783958400000,
        "net_inflow": 11714291730
      }
    ]
  }
}
```

</details>

### QDII额度汇总

`GET /api/fund/quota/summary`

QDII额度汇总

**运行验证**：`verified_success`，`code=0`，success

**请求参数**

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|---|---|---|---|---|
| tab | string | 是 | — | 分类数组 JSON 字符串，例如 ["nazhi100"]。 |

**主要响应字段**

| 字段 | 类型 | 说明 |
|---|---|---|
| name | string | 分类名称。 |
| unlimited | string | 无额度限制的基金数。 |
| total_limit | string | 限额合计。 |
| total | string | 基金总数。 |
| buy | string | 可购基金数。 |

示例：`https://datahub.10jqka.com.cn/api/fund/quota/summary?tab=%5B%22nazhi100%22%5D`

<details>
<summary>响应示例</summary>

```json
{
  "code": 0,
  "message": "success",
  "request_id": "6c7651d4a90141cda51b1fa16ed76272",
  "data": [
    {
      "name": "nazhi100",
      "unlimited": "0",
      "total_limit": "10690.00",
      "total": "25",
      "buy": "25"
    }
  ]
}
```

</details>

### QDII额度列表

`GET /api/fund/quota/list`

QDII额度列表

**运行验证**：`verified_success`，`code=0`，success

**请求参数**

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|---|---|---|---|---|
| tab | string | 是 | — | 分类数组 JSON 字符串。 |
| buy | boolean | 否 | — | 可购状态过滤；省略时不向上游注入默认值。 |

**主要响应字段**

| 字段 | 类型 | 说明 |
|---|---|---|
| name | string | 分类名称。 |
| sub_tab | array | 子分类列表。 |
| name | string | 子分类名称。 |
| fund_list | array | 当前子分类下的基金列表。 |
| thscode | string | 含市场后缀的完整基金代码。 |
| fund_name | string | 基金名称。 |
| quota | string \| null | 基金额度；null 表示无限额。 |
| year | string \| null | 近一年收益率。 |
| classify | string[] \| null | 共享基金额度类别列表。 |

示例：`https://datahub.10jqka.com.cn/api/fund/quota/list?tab=%5B%22remen%22%5D&buy=true`

<details>
<summary>响应示例</summary>

```json
{
  "code": 0,
  "message": "success",
  "request_id": "b8d9894004a04b3dbb93f8679e1de383",
  "data": [
    {
      "name": "remen",
      "sub_tab": [
        {
          "name": "all",
          "fund_list": [
            {
              "thscode": "539001.OF",
              "fund_name": "建信纳斯达克100指数(QDII)A人民币",
              "quota": "10.00",
              "year": "16.21",
              "classify": [
                "A",
                "C",
                "I"
              ]
            }
          ]
        }
      ]
    }
  ]
}
```

</details>

## futures

### 期货公司合约历史持仓

`GET /api/futures/positions/contract-historical`

期货持仓提供品种、公司和合约维度的日持仓与历史持仓数据。

**运行验证**：`upstream_unavailable`，`code=5003`，Futures finance upstream returned failure status（使用替代有效样例）

**请求参数**

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|---|---|---|---|---|
| thscode | string | 是 | — | 期货合约完整同花顺代码。 |
| variety | string | 是 | — | 大写品种代码，须与合约一致。 |
| company | string | 是 | — | 期货公司名称。 |
| start_date | string | 是 | — | 开始日期；须位于调用日前一年内，结束日固定为调用日。 |

示例：`https://datahub.10jqka.com.cn/api/futures/positions/contract-historical?thscode=CU2601.SHF&variety=CU&company=示例期货&start_date=2026-01-01`

<details>
<summary>响应示例</summary>

```json
{
  "code": 0,
  "message": "success",
  "request_id": "request-id",
  "data": {
    "timestamp": 1789036800000,
    "start_date": "2026-01-01",
    "end_date": "2026-09-10",
    "position_item": [],
    "average_item": []
  }
}
```

</details>

### 期货公司合约日持仓

`GET /api/futures/positions/contract-daily`

期货持仓提供品种、公司和合约维度的日持仓与历史持仓数据。

**运行验证**：`verified_success`，`code=0`，success（使用替代有效样例）

**请求参数**

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|---|---|---|---|---|
| thscode | string | 是 | — | 期货合约完整同花顺代码。 |
| variety | string | 是 | — | 大写品种代码，须与 thscode 所属品种一致。 |
| date | string | 是 | — | 交易日期，格式 yyyy-MM-dd。 |

**主要响应字段**

| 字段 | 类型 | 说明 |
|---|---|---|
| timestamp / date | long / string \| null | 数据时间与查询交易日。 |
| position_item[] | array | 公司持仓；每项含 date、thscode、ticker、company_name、成交量、多空与净持仓及其变化。 |
| average_item[] | array | 独立均价序列；每项含 date、company_long_avg、company_short_avg，不得与持仓数组按位置关联。 |

示例：`https://datahub.10jqka.com.cn/api/futures/positions/contract-daily?thscode=CU2601.SHF&variety=CU&date=2026-09-10`

<details>
<summary>响应示例</summary>

```json
{
  "code": 0,
  "message": "success",
  "request_id": "request-id",
  "data": {
    "timestamp": 1789036800000,
    "date": "2026-09-10",
    "position_item": [],
    "average_item": []
  }
}
```

</details>

### 期货公司列表

`GET /api/futures/positions/company-list`

期货持仓提供品种、公司和合约维度的日持仓与历史持仓数据。

**运行验证**：`verified_success`，`code=0`，success

**请求参数**

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|---|---|---|---|---|
| — | — | — | — | 无业务参数。 |

**主要响应字段**

| 字段 | 类型 | 说明 |
|---|---|---|
| timestamp | long | 数据时间。 |
| item[] | array | 公司列表；每项含可空的 company_id、company_name。 |

示例：`https://datahub.10jqka.com.cn/api/futures/positions/company-list`

<details>
<summary>响应示例</summary>

```json
{
  "code": 0,
  "message": "success",
  "request_id": "request-id",
  "data": {
    "timestamp": 1789036800000,
    "item": [
      {
        "company_id": "1001",
        "company_name": "示例期货"
      }
    ]
  }
}
```

</details>

### 期货公司品种日持仓

`GET /api/futures/positions/company-variety-daily`

期货持仓提供品种、公司和合约维度的日持仓与历史持仓数据。

**运行验证**：`verified_success`，`code=0`，success

**请求参数**

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|---|---|---|---|---|
| date | string | 是 | — | 交易日期，格式 yyyy-MM-dd。 |
| varieties | string | 是 | — | 1～5 个逗号分隔的大写期货品种代码。 |

**主要响应字段**

| 字段 | 类型 | 说明 |
|---|---|---|
| timestamp | long | 数据时间。 |
| item[] | array | 各期货公司的品种持仓列表。 |
| date / variety_code / company_name | string \| null | 交易日期（yyyy-MM-dd）、品种代码与公司名称。 |
| volume / volume_change / long_position / long_position_change / short_position / short_position_change / net_position / net_position_change | number \| null | 成交量、多空与净持仓及其变化。 |
| price_spread_contract | string \| null | 价差合约代码文本；多个代码按上游原值以逗号分隔。 |
| day_profit / year_profit / week_win_rate | number \| null | 日收益、年收益与周胜率。 |
| day_mood / three_day_mood / five_day_mood | number \| null | 不同周期情绪值。 |
| three_day_net_change / five_day_net_change / max_funds | number \| null | 净变化与最大资金。 |
| year_profit_days | integer \| null | 年度盈利天数。 |

示例：`https://datahub.10jqka.com.cn/api/futures/positions/company-variety-daily?date=2026-09-10&varieties=CU,AU`

<details>
<summary>响应示例</summary>

```json
{
  "code": 0,
  "message": "success",
  "request_id": "request-id",
  "data": {
    "timestamp": 1789036800000,
    "item": [
      {
        "date": "2026-09-10",
        "variety_code": "CU",
        "company_name": "示例期货",
        "volume": 1200,
        "volume_change": 30,
        "long_position": 800,
        "long_position_change": 10,
        "short_position": 700,
        "short_position_change": -5,
        "net_position": 100,
        "net_position_change": 15,
        "price_spread_contract": null,
        "day_profit": null,
        "year_profit": null,
        "week_win_rate": null,
        "day_mood": null,
        "three_day_mood": null,
        "five_day_mood": null,
        "three_day_net_change": null,
        "five_day_net_change": null,
        "max_funds": null,
        "year_profit_days": null
      }
    ]
  }
}
```

</details>

### 期货品种日持仓

`GET /api/futures/positions/variety-daily`

期货持仓提供品种、公司和合约维度的日持仓与历史持仓数据。

**运行验证**：`verified_success`，`code=0`，success

**请求参数**

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|---|---|---|---|---|
| date | string | 是 | — | 交易日期，格式 yyyy-MM-dd。 |

**主要响应字段**

| 字段 | 类型 | 说明 |
|---|---|---|
| timestamp | long | 数据时间。 |
| item[] | array | 品种日持仓列表。 |
| date / variety_code / variety_name | string \| null | 交易日期（yyyy-MM-dd）、品种代码与名称。 |
| volume / volume_change | number \| null | 成交量及变化。 |
| long_position / long_position_change / short_position / short_position_change | number \| null | 多空持仓及变化。 |
| net_position / net_position_change | number \| null | 净持仓及变化。 |
| twenty_day_avg_price / main_close_price / index_close_price / main_settle_price | number \| null | 均价、主力/指数收盘价及主力结算价。 |
| change_risk / main_change_ratio / max_funds / capital_flow | number \| null | 风险变化、涨跌幅、最大资金与资金流。 |

示例：`https://datahub.10jqka.com.cn/api/futures/positions/variety-daily?date=2026-09-10`

<details>
<summary>响应示例</summary>

```json
{
  "code": 0,
  "message": "success",
  "request_id": "request-id",
  "data": {
    "timestamp": 1789036800000,
    "item": [
      {
        "date": "2026-09-10",
        "variety_code": "CU",
        "variety_name": "沪铜",
        "volume": 120000,
        "volume_change": 1000,
        "long_position": 80000,
        "long_position_change": 500,
        "short_position": 76000,
        "short_position_change": -200,
        "net_position": 4000,
        "net_position_change": 700,
        "twenty_day_avg_price": 78000,
        "change_risk": null,
        "main_close_price": 78200,
        "index_close_price": 78100,
        "main_settle_price": 77900,
        "main_change_ratio": 0.012,
        "max_funds": null,
        "capital_flow": null
      }
    ]
  }
}
```

</details>

### 期货合约基础信息列表

`GET /api/futures/contracts/list`

从完整期货目录快照分页获取合约基础信息，适合批量同步或按目录筛选前的本地索引。

**运行验证**：`verified_success`，`code=0`，success

**请求参数**

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|---|---|---|---|---|
| limit | integer | 否 | 100 | 单页条数，范围 1-1000。 |
| offset | integer | 否 | 0 | 分页偏移，最小为 0。 |

**主要响应字段**

| 字段 | 类型 | 说明 |
|---|---|---|
| timestamp | long | 数据时间，毫秒时间戳。 |
| total | integer | 合约总数。 |
| item[] | array | 合约基础信息列表。 |

示例：`https://datahub.10jqka.com.cn/api/futures/contracts/list?limit=100&offset=0`

<details>
<summary>响应示例</summary>

```json
{
  "code": 0,
  "message": "success",
  "request_id": "request-id",
  "data": {
    "timestamp": 1789036800000,
    "total": 1,
    "item": [
      {
        "thscode": "CU2601.SHF",
        "ticker": "CU2601",
        "name": "沪铜2601",
        "exchange_code": "SHFE",
        "variety_code": "CU",
        "list_date": "2025-01-01",
        "end_date": "2026-01-15",
        "last_trade_date": "2026-01-15",
        "last_delivery_date": "2026-01-20"
      }
    ]
  }
}
```

</details>

### 期货合约详情

`GET /api/futures/contracts/detail`

期货合约基础资料提供单个合约详情与分页合约目录。

**运行验证**：`verified_success`，`code=0`，success（使用替代有效样例）

**请求参数**

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|---|---|---|---|---|
| thscode | string | 是 | — | 期货合约完整同花顺代码。 |

**主要响应字段**

| 字段 | 类型 | 说明 |
|---|---|---|
| timestamp | long | 数据时间，毫秒时间戳。 |
| thscode / ticker / name | string \| null | 完整代码、纯代码与合约名称。 |
| variety_code / variety_name / exchange_code | string \| null | 品种代码、品种名称与交易所代码。 |
| list_date | string \| null | 合约上市日期；来源缺失时为 null。 |
| end_date | string \| null | 合约上市结束日期。 |
| last_trade_date / last_delivery_date | string \| null | 最后交易日与最后交割日；来源缺失时为 null。 |

示例：`https://datahub.10jqka.com.cn/api/futures/contracts/detail?thscode=CU2601.SHF`

<details>
<summary>响应示例</summary>

```json
{
  "code": 0,
  "message": "success",
  "request_id": "request-id",
  "data": {
    "timestamp": 1789036800000,
    "thscode": "CU2601.SHF",
    "ticker": "CU2601",
    "name": "沪铜2601",
    "variety_code": "CU",
    "variety_name": "沪铜",
    "exchange_code": "SHFE",
    "list_date": "2025-01-01",
    "end_date": "2026-01-15",
    "last_trade_date": "2026-01-15",
    "last_delivery_date": "2026-01-20"
  }
}
```

</details>

### 期货历史基差

`GET /api/futures/basis/historical`

期货基差提供主连合约最新基差快照与指定区间历史数据。

**运行验证**：`verified_success`，`code=0`，success（使用替代有效样例）

**请求参数**

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|---|---|---|---|---|
| thscode | string | 是 | — | 期货合约完整同花顺代码。 |
| spot_indicator_id | string | 否 | — | 可选现货指标 ID；省略时使用上游默认口径。 |

**主要响应字段**

| 字段 | 类型 | 说明 |
|---|---|---|
| timestamp | long | 数据时间。 |
| item[].date | string \| null | 记录日期。 |
| item[].spot_price / converted_spot_price / close_price / settle_price | number \| null | 现货、折算现货、收盘与结算价格。 |
| item[].close_basis / settle_basis / close_basis_rate / settle_basis_rate | number \| null | 收盘/结算基差及其比例。 |

示例：`https://datahub.10jqka.com.cn/api/futures/basis/historical?thscode=CU2601.SHF`

<details>
<summary>响应示例</summary>

```json
{
  "code": 0,
  "message": "success",
  "request_id": "request-id",
  "data": {
    "timestamp": 1789036800000,
    "item": [
      {
        "date": "2026-09-10",
        "spot_price": 78000,
        "converted_spot_price": 78000,
        "close_price": 78200,
        "settle_price": 77900,
        "close_basis": 200,
        "settle_basis": -100,
        "close_basis_rate": 0.0026,
        "settle_basis_rate": -0.0013
      }
    ]
  }
}
```

</details>

### 期货主连最新基差

`GET /api/futures/basis/main-continuous-latest`

期货基差提供主连合约最新基差快照与指定区间历史数据。

**运行验证**：`verified_success`，`code=0`，success

**请求参数**

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|---|---|---|---|---|
| — | — | — | — | 无业务参数。 |

**主要响应字段**

| 字段 | 类型 | 说明 |
|---|---|---|
| timestamp | long | 数据时间。 |
| thscode / ticker / name / variety_name | string \| null | 主连代码与名称信息。 |
| reference_site / updated_at / spot_publish_date / spot_indicator_id / default_value | string \| null | 参考来源、更新时间、现货发布日期、指标 ID 与默认口径原值。 |
| spot_price / converted_spot_price / close_price / settle_price | number \| null | 现货、折算现货、收盘与结算价格。 |
| close_basis / settle_basis / close_basis_rate / settle_basis_rate | number \| null | 收盘/结算基差及其比例。 |
| average_close_basis / average_settle_basis | number \| null | 平均收盘与结算基差。 |

示例：`https://datahub.10jqka.com.cn/api/futures/basis/main-continuous-latest`

<details>
<summary>响应示例</summary>

```json
{
  "code": 0,
  "message": "success",
  "request_id": "request-id",
  "data": {
    "timestamp": 1789036800000,
    "item": [
      {
        "thscode": "CU.L8",
        "ticker": "CU",
        "name": "沪铜主连",
        "variety_name": "沪铜",
        "reference_site": null,
        "updated_at": "2026-09-10 15:00:00",
        "spot_publish_date": "2026-09-10",
        "spot_indicator_id": null,
        "spot_price": 78000,
        "converted_spot_price": 78000,
        "close_price": 78200,
        "settle_price": 77900,
        "close_basis": 200,
        "settle_basis": -100,
        "close_basis_rate": 0.0026,
        "settle_basis_rate": -0.0013,
        "default_value": null,
        "average_close_basis": null,
        "average_settle_basis": null
      }
    ]
  }
}
```

</details>

### 期货交易日

`GET /api/futures/calendar/trading-schedule`

查询指定期货合约在日期范围内的交易日列表及对应交易时间安排。

**运行验证**：`verified_success`，`code=0`，success（使用替代有效样例）

**请求参数**

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|---|---|---|---|---|
| thscode | string | 是 | — | 期货合约完整同花顺代码。 |
| start_date | string | 是 | — | 开始日期，格式 yyyy-MM-dd。 |
| end_date | string | 是 | — | 结束日期，不早于开始日期。 |

**主要响应字段**

| 字段 | 类型 | 说明 |
|---|---|---|
| timestamp / thscode / timezone | long / string | 数据时间、合约代码与时区。 |
| trade_dates[] | array | ISO 交易日期。 |
| regular_schedules[] | array | 常规日程；含 start_date、end_date、times[]，时间项含 start_time、end_time、offset、trans_day_type、type。 |
| special_schedules[] | array | 特殊日程；含 date、times[]，时间项含毫秒 start_time、end_time 与 type。 |
| daylight_saving_periods[] | array | 夏令时原值；每项含 start、end、offset。 |

示例：`https://datahub.10jqka.com.cn/api/futures/calendar/trading-schedule?thscode=CU2601.SHF&start_date=2026-01-09&end_date=2026-01-09`

<details>
<summary>响应示例</summary>

```json
{
  "code": 0,
  "message": "success",
  "request_id": "request-id",
  "data": {
    "timestamp": 1767888000000,
    "thscode": "CU2601.SHF",
    "trade_dates": [
      "2026-01-09"
    ],
    "regular_schedules": [],
    "special_schedules": [],
    "timezone": "Asia/Shanghai",
    "daylight_saving_periods": []
  }
}
```

</details>

### 期货交易时间轴

`GET /api/futures/calendar/session-timeline`

期货交易时间轴提供合约最近交易日的交易阶段、交易所阶段与跨日时间范围。

**运行验证**：`verified_success`，`code=0`，success（使用替代有效样例）

**请求参数**

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|---|---|---|---|---|
| thscode | string | 是 | — | 期货合约完整同花顺代码。 |

**主要响应字段**

| 字段 | 类型 | 说明 |
|---|---|---|
| timestamp / thscode / trade_date / timezone | long / string | 数据时间、合约代码、最近交易日与时区。 |
| trade_stages[] | array | 交易阶段；每项含 trade_period 与 trade_ranges[]，范围含毫秒 begin_time、end_time。 |
| exchange_sessions[] | array | 交易所阶段；每项含 trade_phase 与 phase_range[]，范围结构同上。 |

示例：`https://datahub.10jqka.com.cn/api/futures/calendar/session-timeline?thscode=CU2601.SHF`

<details>
<summary>响应示例</summary>

```json
{
  "code": 0,
  "message": "success",
  "request_id": "request-id",
  "data": {
    "timestamp": 1789036800000,
    "thscode": "CU2601.SHF",
    "trade_date": "2026-09-10",
    "timezone": "Asia/Shanghai",
    "trade_stages": [],
    "exchange_sessions": []
  }
}
```

</details>

### 期货历史仓单

`GET /api/futures/warehouse-receipts/historical`

查询指定期货合约在日期范围内的仓单数据。

**运行验证**：`verified_success`，`code=0`，success（使用替代有效样例）

**请求参数**

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|---|---|---|---|---|
| thscode | string | 是 | — | 期货合约完整同花顺代码。 |
| start_date | string | 是 | — | 开始日期，格式 yyyy-MM-dd。 |
| end_date | string | 是 | — | 结束日期，不早于开始日期。 |

**主要响应字段**

| 字段 | 类型 | 说明 |
|---|---|---|
| timestamp | long | 数据时间。 |
| item[] | array | 仓单列表；每项含 date 与可空的 amount、amount_change、equivalent_lots。 |

示例：`https://datahub.10jqka.com.cn/api/futures/warehouse-receipts/historical?thscode=CU2601.SHF&start_date=2026-09-01&end_date=2026-09-10`

<details>
<summary>响应示例</summary>

```json
{
  "code": 0,
  "message": "success",
  "request_id": "request-id",
  "data": {
    "timestamp": 1789036800000,
    "item": [
      {
        "date": "2026-09-10",
        "amount": 12000,
        "amount_change": 300,
        "equivalent_lots": 2400
      }
    ]
  }
}
```

</details>

### 期货品种板块

`GET /api/futures/variety-plates/list`

期货品种板块提供品种与板块层级的对应关系。 无业务参数。

**运行验证**：`verified_success`，`code=0`，success

**请求参数**

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|---|---|---|---|---|
| — | — | — | — | 无业务参数。 |

**主要响应字段**

| 字段 | 类型 | 说明 |
|---|---|---|
| timestamp | long | 数据时间。 |
| item[] | array | 品种板块列表；每项含可空的 variety_code、name、plate_level、plate_name。 |

示例：`https://datahub.10jqka.com.cn/api/futures/variety-plates/list`

<details>
<summary>响应示例</summary>

```json
{
  "code": 0,
  "message": "success",
  "request_id": "request-id",
  "data": {
    "timestamp": 1789036800000,
    "item": [
      {
        "variety_code": "CU",
        "name": "沪铜",
        "plate_level": 1,
        "plate_name": "有色金属"
      }
    ]
  }
}
```

</details>

### 期货品种资料

`GET /api/futures/varieties/list`

期货品种资料提供期货品种目录及交易属性。 无业务参数。

**运行验证**：`verified_success`，`code=0`，success

**请求参数**

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|---|---|---|---|---|
| — | — | — | — | 无业务参数。 |

**主要响应字段**

| 字段 | 类型 | 说明 |
|---|---|---|
| timestamp | long | 数据时间，毫秒时间戳。 |
| item[] | array | 品种列表。 |
| item[].variety_code / quote_code / name | string \| null | 品种代码、行情代码与名称。 |
| item[].exchange_code / exchange_name | string \| null | 交易所代码与名称。 |
| item[].has_night_session | boolean \| null | 是否包含夜盘。 |
| item[].margin_rate / capital_flow / long_short_ratio | number \| null | 保证金率、资金流与多空比。 |
| item[].trade_amount | number \| null | 品种交易单位数量，单位由 trade_unit 字段给出。 |
| item[].price_coefficient / tick_size / contract_multiplier | number \| null | 价格系数、最小变动价位与合约乘数。 |
| item[].price_unit / trade_unit / main_contract_thscode | string \| null | 价格单位、交易单位与主力合约代码。 |
| item[].transaction_fee / transaction_fee_rate | number \| null | 手续费与手续费率。 |
| item[].trade_sessions[] | array | 交易时段；每项含 start_time、end_time、session_type。 |

示例：`https://datahub.10jqka.com.cn/api/futures/varieties/list`

<details>
<summary>响应示例</summary>

```json
{
  "code": 0,
  "message": "success",
  "request_id": "request-id",
  "data": {
    "timestamp": 1789036800000,
    "item": [
      {
        "variety_code": "CU",
        "quote_code": "CU",
        "name": "沪铜",
        "exchange_code": "SHFE",
        "exchange_name": "上海期货交易所",
        "has_night_session": true,
        "margin_rate": 0.12,
        "main_contract_thscode": "CU2601.SHF",
        "trade_amount": 5,
        "price_coefficient": 1,
        "price_unit": "元/吨",
        "trade_unit": "吨/手",
        "tick_size": 10,
        "contract_multiplier": 5,
        "capital_flow": null,
        "long_short_ratio": null,
        "transaction_fee": null,
        "transaction_fee_rate": null,
        "trade_sessions": []
      }
    ]
  }
}
```

</details>

### 期货分时

`GET /api/futures/prices/intraday`

期货行情提供合约分时和 K 线数据；支持历史交易日分时及多周期 K 线。

**运行验证**：`verified_success`，`code=0`，success（使用替代有效样例）

**请求参数**

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|---|---|---|---|---|
| thscode | string | 是 | — | 期货合约或期货商品指数完整同花顺代码。 |
| session | enum | 否 | — | 行情阶段：pre_market-盘前、intraday-盘中、post_market-盘后；省略时使用 intraday。 |
| trade_date | string | 否 | — | 可传 0 或合法历史交易日 yyyyMMdd。 |

**主要响应字段**

| 字段 | 类型 | 说明 |
|---|---|---|
| timestamp | long | 数据时间。 |
| thscode / date / session | string | 行情标的代码、当前或最近交易日与行情阶段。 |
| item[] | array | 分时点；每项含可空的 timestamp、price、volume、turnover。 |

示例：`https://datahub.10jqka.com.cn/api/futures/prices/intraday?thscode=CU2601.SHF&session=intraday`

<details>
<summary>响应示例</summary>

```json
{
  "code": 0,
  "message": "success",
  "request_id": "request-id",
  "data": {
    "timestamp": 1767922260000,
    "thscode": "CU2601.SHF",
    "date": "2026-01-09",
    "session": "intraday",
    "item": [
      {
        "timestamp": 1767922260000,
        "price": 78200,
        "volume": 12,
        "turnover": 4692000
      }
    ]
  }
}
```

</details>

### 期货K线

`GET /api/futures/prices/daily`

期货行情提供合约分时和 K 线数据；支持历史交易日分时及多周期 K 线。

**运行验证**：`verified_success`，`code=0`，success（使用替代有效样例）

**请求参数**

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|---|---|---|---|---|
| thscode | string | 是 | — | 期货合约或期货商品指数完整同花顺代码。 |
| start | long | 否 | — | 与 end 成对提供的正毫秒时间戳；两者均省略时查询最近 100 根。 |
| end | long | 否 | — | 与 start 成对提供，且不早于 start。 |
| time_period | enum | 否 | — | 可使用 min_1、min_10、hour_1、day_1、week_1、month_1、quarter_1、year_1。 |

**主要响应字段**

| 字段 | 类型 | 说明 |
|---|---|---|
| timestamp | long | 数据时间。 |
| thscode | string | 期货合约或期货商品指数代码。 |
| interval | string | 实际返回的 K 线周期。 |
| item[] | array | 日 K；每项含可空的 timestamp、open_price、high_price、low_price、close_price、volume、turnover。 |

示例：`https://datahub.10jqka.com.cn/api/futures/prices/daily?thscode=CU2601.SHF`

<details>
<summary>响应示例</summary>

```json
{
  "code": 0,
  "message": "success",
  "request_id": "request-id",
  "data": {
    "timestamp": 1767922260000,
    "thscode": "CU2601.SHF",
    "interval": "1d",
    "item": [
      {
        "timestamp": 1767888000000,
        "open_price": 78000,
        "high_price": 78400,
        "low_price": 77800,
        "close_price": 78200,
        "volume": 120000,
        "turnover": 46920000000
      }
    ]
  }
}
```

</details>

### 期货次主力合约

`GET /api/futures/contracts/secondary-main-list`

期货主力与指数合约提供主连、主力、次主力和商品指数能力。

**运行验证**：`verified_success`，`code=0`，success

**请求参数**

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|---|---|---|---|---|
| — | — | — | — | 无业务参数。 |

示例：`https://datahub.10jqka.com.cn/api/futures/contracts/secondary-main-list`

<details>
<summary>响应示例</summary>

```json
{
  "code": 0,
  "message": "success",
  "request_id": "request-id",
  "data": {
    "timestamp": 1789036800000,
    "item": []
  }
}
```

</details>

### 期货主力合约

`GET /api/futures/contracts/main-list`

期货主力与指数合约提供主连、主力、次主力和商品指数能力。

**运行验证**：`verified_success`，`code=0`，success

**请求参数**

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|---|---|---|---|---|
| — | — | — | — | 无业务参数。 |

**主要响应字段**

| 字段 | 类型 | 说明 |
|---|---|---|
| timestamp | long | 数据时间。 |
| item[] | array | 主力合约列表。 |
| thscode / ticker / name / variety_code / variety_name / exchange_code | string \| null | 合约、品种与交易所信息。 |
| list_date | string \| null | 合约上市日期。 |
| end_date | string \| null | 合约上市结束日期。 |
| last_trade_date / last_delivery_date | string \| null | 最后交易日与最后交割日。 |
| margin_rate / transaction_fee / transaction_fee_rate | number \| null | 保证金率、手续费与手续费率。 |

示例：`https://datahub.10jqka.com.cn/api/futures/contracts/main-list`

<details>
<summary>响应示例</summary>

```json
{
  "code": 0,
  "message": "success",
  "request_id": "request-id",
  "data": {
    "timestamp": 1789036800000,
    "item": [
      {
        "thscode": "CU2601.SHF",
        "ticker": "CU2601",
        "name": "沪铜2601",
        "variety_code": "CU",
        "variety_name": "沪铜",
        "exchange_code": "SHFE",
        "list_date": "2025-01-01",
        "end_date": "2026-01-15",
        "last_trade_date": "2026-01-15",
        "last_delivery_date": "2026-01-20",
        "margin_rate": 0.12,
        "transaction_fee": null,
        "transaction_fee_rate": null
      }
    ]
  }
}
```

</details>

### 期货主连资料

`GET /api/futures/contracts/main-continuous-list`

期货主力与指数合约提供主连、主力、次主力和商品指数能力。

**运行验证**：`verified_success`，`code=0`，success

**请求参数**

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|---|---|---|---|---|
| — | — | — | — | 无业务参数。 |

**主要响应字段**

| 字段 | 类型 | 说明 |
|---|---|---|
| timestamp | long | 数据时间。 |
| item[] | array | 主连列表。 |
| thscode / ticker / name / variety_code / variety_name / exchange_code | string \| null | 主连代码、名称、品种与交易所信息。 |
| minute_visit_count / kline_visit_count | integer \| null | 分时与 K 线访问次数。 |
| statistics_date | string \| null | 统计日期。 |

示例：`https://datahub.10jqka.com.cn/api/futures/contracts/main-continuous-list`

<details>
<summary>响应示例</summary>

```json
{
  "code": 0,
  "message": "success",
  "request_id": "request-id",
  "data": {
    "timestamp": 1789036800000,
    "item": [
      {
        "thscode": "CU.L8",
        "ticker": "CU",
        "name": "沪铜主连",
        "variety_code": "CU",
        "variety_name": "沪铜",
        "exchange_code": "SHFE",
        "minute_visit_count": 1200,
        "kline_visit_count": 300,
        "statistics_date": "2026-09-10"
      }
    ]
  }
}
```

</details>

### 商品指数合约列表

`GET /api/futures/contracts/commodity-index-list`

期货主力与指数合约提供主连、主力、次主力和商品指数能力。

**运行验证**：`verified_success`，`code=0`，success

**请求参数**

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|---|---|---|---|---|
| — | — | — | — | 无业务参数。 |

**主要响应字段**

| 字段 | 类型 | 说明 |
|---|---|---|
| timestamp | long | 数据时间。 |
| item[] | array | 商品指数合约列表；每项含可空的 thscode、ticker、name、list_date、end_date。 |
| item[].end_date | string \| null | 合约上市结束日期。 |

示例：`https://datahub.10jqka.com.cn/api/futures/contracts/commodity-index-list`

<details>
<summary>响应示例</summary>

```json
{
  "code": 0,
  "message": "success",
  "request_id": "request-id",
  "data": {
    "timestamp": 1789036800000,
    "item": [
      {
        "thscode": "CUFI.WI",
        "ticker": "CUFI",
        "name": "沪铜指数",
        "list_date": "2010-01-01",
        "end_date": null
      }
    ]
  }
}
```

</details>

### 期货F10宏观指标历史数据

`GET /api/futures/fundamentals/indicators-historical`

期货 F10 宏观指标历史数据提供指定宏观指标在日期范围内的历史观测值。

**运行验证**：`verified_success`，`code=0`，success

**请求参数**

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|---|---|---|---|---|
| indicator_ids | string | 是 | — | 1～5 个逗号分隔的指标 ID。 |
| start_date | string | 是 | — | 开始日期，格式 yyyy-MM-dd。 |
| end_date | string | 是 | — | 结束日期，不早于开始日期，区间最长 5 年。 |

**主要响应字段**

| 字段 | 类型 | 说明 |
|---|---|---|
| timestamp | long | 数据时间。 |
| item[] | array | 指标列表；每项含可空 indicator_id 与非空 observations[]。 |
| observations[].date / value | string \| null / number \| null | 观察日期与数值。 |

示例：`https://datahub.10jqka.com.cn/api/futures/fundamentals/indicators-historical?indicator_ids=2825232,2825233&start_date=2026-01-01&end_date=2026-09-01`

<details>
<summary>响应示例</summary>

```json
{
  "code": 0,
  "message": "success",
  "request_id": "request-id",
  "data": {
    "timestamp": 1789036800000,
    "item": [
      {
        "indicator_id": "2825232",
        "observations": [
          {
            "date": "2026-08-28",
            "value": 50
          }
        ]
      }
    ]
  }
}
```

</details>

## hk-share

### 港股认购与待上市日历

`GET /api/hk-share/ipo/calendar-list`

查询港股可认购或待上市列表。issue_code 是发行记录标识，正式证券代码未确定时为 null；价格区间、每手股数与入场费详情由发行详情接口查询。截止日期为公共招股日期。

**运行验证**：`verified_success`，`code=0`，success

**请求参数**

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|---|---|---|---|---|
| status | string | 是 | — | 发行阶段：subscribable/awaiting_listing |

**主要响应字段**

| 字段 | 类型 | 说明 |
|---|---|---|
| status | enum | 当前阶段 |
| item | array | 业务记录列表 |
| issue_code | string | 发行记录标识，保留返回HK前缀等值 |
| thscode | string \| null | 正式代码；尚未确认时为空 |
| name | string | 发行股票名称 |
| listing_date | date \| null | 上市日期 |
| issue_price | number \| null | 已定发行价；可认购仅区间时本字段null；单位：HKD |
| currency | string \| null | HKD |
| subscription_end_date | date \| null | 公共招股截止日期；不是各券商精确时点 |
| entry_fee | number \| null | 业务返回入场费，不拆解其中费用；单位：HKD |
| issue_price_text | string \| null | 返回招股价展示文本；不从文本虚构单一发行价 |

示例：`https://datahub.10jqka.com.cn/api/hk-share/ipo/calendar-list?status=subscribable`

<details>
<summary>响应示例</summary>

```json
{
  "code": 0,
  "message": "success",
  "request_id": "example-request",
  "data": {
    "status": "subscribable",
    "item": [
      {
        "issue_code": "HK6157",
        "thscode": null,
        "name": "瘦西湖文旅",
        "listing_date": null,
        "issue_price": null,
        "currency": "HKD",
        "subscription_end_date": "2026-10-20",
        "entry_fee": 5121.14,
        "issue_price_text": "3.92-5.07"
      }
    ]
  }
}
```

</details>

### 港股新股递表记录

`GET /api/hk-share/ipo/application-list`

分页查询港股公司递表记录，保留同一公司的重复申请。页码从 1 开始，每页 50 条；总数未知时为 null，以 has_next 判断后续页。

**运行验证**：`verified_success`，`code=0`，success

**请求参数**

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|---|---|---|---|---|
| page | integer | 否 | 1 | 从1开始的页码 |

**主要响应字段**

| 字段 | 类型 | 说明 |
|---|---|---|
| item | array | 业务记录列表 |
| pagination | object | 分页对象，包含page、size、total和has_next |
| company_name | string | 递表公司名称 |
| application_date | date \| null | 递表日期 |
| page | integer | 从1开始的页码 |
| size | integer | 本页请求大小 |
| total | integer \| null | 结果总数；未提供时为null |
| has_next | boolean | 是否存在后续页 |

示例：`https://datahub.10jqka.com.cn/api/hk-share/ipo/application-list?page=1`

<details>
<summary>响应示例</summary>

```json
{
  "code": 0,
  "message": "success",
  "request_id": "example-request",
  "data": {
    "item": [
      {
        "company_name": "Pinnacle Marine Holdings Ltd",
        "application_date": "2026-10-08"
      }
    ],
    "pagination": {
      "page": 1,
      "size": 50,
      "total": null,
      "has_next": true
    }
  }
}
```

</details>

### 港股新股发行详情

`GET /api/hk-share/ipo/issue-detail`

按发行记录标识查询港股招股价格区间、每手股数与入场费。金额币种为港元，区间和费用为空时保留 null，本接口不表示该发行记录当前可认购。

**运行验证**：`verified_success`，`code=0`，success

**请求参数**

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|---|---|---|---|---|
| issue_code | string | 是 | — | 日历中的发行记录标识，最多32字符 |

**主要响应字段**

| 字段 | 类型 | 说明 |
|---|---|---|
| issue_code | string | 返回发行标识 |
| currency | string | HKD |
| issue_price_range | object \| null | 招股价格区间对象，包含可空的lower与upper；单位：HKD |
| lot_size | integer \| null | 每手股数；单位：股 |
| entry_fee | number \| null | 业务返回入场费，不自行按价格/股数推算；单位：HKD |
| lower | number \| null | 报价下界；单位：HKD |
| upper | number \| null | 报价上界；单位：HKD |

示例：`https://datahub.10jqka.com.cn/api/hk-share/ipo/issue-detail?issue_code=HK2636`

<details>
<summary>响应示例</summary>

```json
{
  "code": 0,
  "message": "success",
  "request_id": "example-request",
  "data": {
    "issue_code": "HK2636",
    "currency": "HKD",
    "issue_price_range": {
      "lower": 35.3,
      "upper": 38.8
    },
    "lot_size": 100,
    "entry_fee": 3919.13
  }
}
```

</details>

## index

### 同花顺新增概念

`GET /api/a-share-index/baseinfo/new-concepts`

分页查询新增概念及创建时间，保留概念业务代码；尚未登记的标准指数代码为 null。

**运行验证**：`verified_success`，`code=0`，success

**请求参数**

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|---|---|---|---|---|
| page | integer | 否 | 1 | 从1开始的页码 |
| size | integer | 否 | 15 | 每页1至15条，默认15 |

**主要响应字段**

| 字段 | 类型 | 说明 |
|---|---|---|
| item | array | 业务记录列表 |
| pagination | object | 分页对象，包含page、size、total和has_next |
| record_id | integer | 概念新增事件记录标识 |
| concept_code | string | 概念代码 |
| thscode | string \| null | 可映射的标准指数标识 |
| name | string | 概念名称 |
| created_at | integer | 本概念新增时间；单位：毫秒 |
| page | integer | 从1开始的页码 |
| size | integer | 本页请求大小 |
| total | integer \| null | 结果总数；未提供时为null |
| has_next | boolean | 是否存在后续页 |

示例：`https://datahub.10jqka.com.cn/api/a-share-index/baseinfo/new-concepts?page=1&size=15`

<details>
<summary>响应示例</summary>

```json
{
  "code": 0,
  "message": "success",
  "request_id": "example-request",
  "data": {
    "item": [
      {
        "record_id": 38306,
        "concept_code": "886113",
        "thscode": null,
        "name": "2026三季报预增",
        "created_at": 1791532812000
      }
    ],
    "pagination": {
      "page": 1,
      "size": 15,
      "total": 60,
      "has_next": true
    }
  }
}
```

</details>

### 同花顺指数成分股

`GET /api/a-share-index/constituents/ths-stock-list`

按单个指数 thscode 返回当前成分股清单。 支持同花顺板块指数（如 886042.TI）与标准指数（如沪深 300 000300.SH / 399300.SZ）。

**运行验证**：`verified_success`，`code=0`，success

**请求参数**

| 参数 | 位置 | 类型 | 必需 | 说明 | 默认值 |
|---|---|---|---|---|---|
| thscode | query | string | 是 | 指数 thscode，形如 {ticker}.{suffix}。入参会被 trim().toUpperCase() 标准化；**不接受逗号**，单次仅支持一个指数。 | - |

**主要响应字段**

| 字段 | 类型 | 说明 |
|---|---|---|
| timestamp | long | 数据时间戳（毫秒）。 |
| item[].thscode | string | 成分股完整 thscode。 |
| item[].ticker | string | 成分股纯代码。 |
| item[].name | string | 成分股展示名称。 |

示例：`https://datahub.10jqka.com.cn/api/a-share-index/constituents/ths-stock-list?thscode=886042.TI`

<details>
<summary>响应示例</summary>

```json
{
  "code": 0,
  "message": "success",
  "request_id": "f6g7h8i9",
  "data": {
    "timestamp": 1748102400000,
    "item": [
      {
        "thscode": "600519.SH",
        "ticker": "600519",
        "name": "贵州茅台"
      },
      {
        "thscode": "000858.SZ",
        "ticker": "000858",
        "name": "五粮液"
      }
    ]
  }
}
```

</details>

### 同花顺指数列表

`GET /api/a-share-index/catalog/ths-index-list`

按 tag（概念 / 区域 / 特色 / 行业）列出同花顺指数清单，单 tag 一次性全量返回， 无分页参数。

**运行验证**：`verified_success`，`code=0`，success

**请求参数**

| 参数 | 位置 | 类型 | 必需 | 说明 | 默认值 |
|---|---|---|---|---|---|
| tag | query | string | 否 | 标签白名单：cn_concept(A 股概念) / region(区域指数) / tszs(特色指数) / industry(行业指数)。大小写不敏感。 | cn_concept |

**主要响应字段**

| 字段 | 类型 | 说明 |
|---|---|---|
| timestamp | long | 数据时间戳（毫秒）。 |
| item[].thscode | string | 同花顺指数的完整 thscode，如 886042.TI。 |
| item[].name | string | 同花顺指数展示名称。 |

示例：`https://datahub.10jqka.com.cn/api/a-share-index/catalog/ths-index-list?tag=cn_concept`

<details>
<summary>响应示例</summary>

```json
{
  "code": 0,
  "message": "success",
  "request_id": "e5f6g7h8",
  "data": {
    "timestamp": 1748102400000,
    "item": [
      {
        "thscode": "886042.TI",
        "name": "白酒概念"
      },
      {
        "thscode": "886041.TI",
        "name": "新能源车"
      }
    ]
  }
}
```

</details>

### 指数历史 K 线

`GET /api/a-share-index/prices/historical`

获取单只指数的历史 K 线序列。每次请求仅支持一个 thscode，只支持 start / end 时间区间模式， 目前仅支持查询近 5 年的数据。指数无复权语义，因此没有 adjust 参数；本接口也没有 offset 参数。

**运行验证**：`verified_success`，`code=0`，success

**请求参数**

| 参数 | 位置 | 类型 | 必需 | 说明 | 默认值 |
|---|---|---|---|---|---|
| thscode | query | string | 是 | 单只指数 thscode，**不接受逗号**。 | - |
| interval | query | string | 是 | K 线周期，当前仅支持 1d（日线）。 | 1d |
| start | query | long | 是 | 起始时间，毫秒 Unix 时间戳。 | - |
| end | query | long | 是 | 结束时间，毫秒 Unix 时间戳；必须不早于 start，且查询区间需落在近 5 年的数据范围内。 | - |

示例：`https://datahub.10jqka.com.cn/api/a-share-index/prices/historical?thscode=000001.SH&interval=1d&start=1716105600000&end=1747641600000`

<details>
<summary>响应示例</summary>

```json
{
  "code": 0,
  "message": "success",
  "request_id": "b9f91af9c77a42d6b8a04738793d2fa2",
  "data": {
    "timestamp": 1747584000000,
    "adjust": null,
    "item": [
      {
        "date_ms": 1716134400000,
        "open_price": 3108.22,
        "high_price": 3125.74,
        "low_price": 3101.15,
        "close_price": 3120.68,
        "volume": 281000000,
        "turnover": 360000000000
      }
    ]
  }
}
```

</details>

### 指数行情快照

`GET /api/a-share-index/prices/snapshot`

按 thscodes 批量获取指数最新行情。与 A 股行情快照不同，本接口**必须传 thscodes**， 不支持空入参枚举全指数；limit / offset 仅为签名对齐保留，对当前接口无效。

**运行验证**：`verified_success`，`code=0`，success

**请求参数**

| 参数 | 位置 | 类型 | 必需 | 说明 | 默认值 |
|---|---|---|---|---|---|
| thscodes | query | string | 是 | 逗号分隔的指数 thscode 列表，如 000001.SH,399001.SZ,886042.TI,881101.TI。 | - |
| limit | query | integer | 否 | 与 A 股行情快照签名对齐，对本接口无效。 | - |
| offset | query | integer | 否 | 与 A 股行情快照签名对齐，对本接口无效。 | - |

示例：`https://datahub.10jqka.com.cn/api/a-share-index/prices/snapshot?thscodes=000001.SH,399001.SZ,886042.TI,881101.TI`

<details>
<summary>响应示例</summary>

```json
{
  "code": 0,
  "message": "success",
  "request_id": "7e25804be878464ba420037155f041e6",
  "data": {
    "timestamp": 1784275991000,
    "total": 4,
    "item": [
      {
        "thscode": "000001.SH",
        "ticker": "000001",
        "last_price": 3388.06,
        "price_change": 12.21,
        "price_change_ratio_pct": 0.3617,
        "open_price": 3370.25,
        "high_price": 3392.18,
        "low_price": 3365.4,
        "prev_price": 3375.85,
        "volume": 321000000,
        "turnover": 420000000000
      }
    ]
  }
}
```

</details>

## meta

### 标的检索

`GET /api/meta/tickers/search`

按关键词（thscode / ticker / 中英文名称）跨市场消歧，支持子串匹配。

**运行验证**：`verified_success`，`code=0`，success

**请求参数**

| 参数 | 位置 | 类型 | 必需 | 说明 | 默认值 |
|---|---|---|---|---|---|
| q | query | string | 是 | 搜索关键词：完整 thscode、ticker 代码或中英文名称（支持子串匹配）。 | - |
| exchange | query | string | 否 | 交易所过滤；支持证券交易所与 CFFEX、SHFE、INE、DCE、CZCE、GFEX、SSE、SZSE。 | - |
| asset_type | query | string | 否 | 规范化资产类型，支持单值或逗号分隔多值；完整枚举见下方。 | - |
| limit | query | integer | 否 | 返回上限，最大 50。 | 10 |

**主要响应字段**

| 字段 | 类型 | 说明 |
|---|---|---|
| timestamp | long | 数据就绪时间（毫秒），为当前代码表快照的上游加载时间。 |
| item | array | 标的列表。 |
| thscode | string | 完整 thscode，如 600519.SH。 |
| ticker | string | 纯代码，如 600519。 |
| name | string | 展示名称。 |
| exchange | string \| null | 交易所后缀（SH / SZ / BJ）；场外基金为 null，.OF 不是交易所。 |
| asset_type | string | 规范化资产类型；每条记录仅返回一个叶子类型，含义同请求参数枚举表。 |
| currency | string | 币种代码；当前基金统一为 CNY。 |
| list_date | string \| null | 上市日期，格式 yyyy-MM-dd。 |
| end_date | string \| null | 合约到期日，格式 yyyy-MM-dd。 |
| last_trade_date | string \| null | 最后交易日，格式 yyyy-MM-dd。 |
| last_delivery_date | string \| null | 最后交割日，格式 yyyy-MM-dd。 |

示例：`https://datahub.10jqka.com.cn/api/meta/tickers/search?q=%E5%B9%B3%E5%AE%89&limit=20`

<details>
<summary>响应示例</summary>

```json
{
  "code": 0,
  "message": "success",
  "request_id": "c3d4e5f6",
  "data": {
    "timestamp": 1716105600000,
    "item": [
      {
        "thscode": "601318.SH",
        "ticker": "601318",
        "name": "中国平安",
        "exchange": "SH",
        "asset_type": "a-share",
        "currency": "CNY",
        "list_date": "2007-03-01",
        "end_date": null,
        "last_trade_date": null,
        "last_delivery_date": null
      }
    ]
  }
}
```

</details>

### 标的列表获取

`GET /api/meta/tickers/list`

批量获取代码表，支持按资产类型过滤。采用 offset / limit 分页， 调用方循环递增 offset 直到 item.length < limit 即可取尽。

**运行验证**：`verified_success`，`code=0`，success

**请求参数**

| 参数 | 位置 | 类型 | 必需 | 说明 | 默认值 |
|---|---|---|---|---|---|
| asset_type | query | string | 否 | 规范化资产类型，支持单值或逗号分隔多值；省略时返回全部类型。 | 全部类型 |
| limit | query | integer | 否 | 单页条数，最大 10000。 | 1000 |
| offset | query | integer | 否 | 分页偏移。 | 0 |

**主要响应字段**

| 字段 | 类型 | 说明 |
|---|---|---|
| timestamp | long | 数据就绪时间（毫秒），为当前代码表快照的上游加载时间。 |
| item | array | 标的列表。 |
| thscode | string | 完整 thscode，如 600519.SH。 |
| ticker | string | 纯代码，如 600519。 |
| name | string | 展示名称。 |
| exchange | string \| null | 交易所后缀（SH / SZ / BJ）；场外基金为 null，.OF 不是交易所。 |
| asset_type | string | 规范化资产类型；每条记录仅返回一个叶子类型，含义同请求参数枚举表。 |
| currency | string | 币种代码；当前基金统一为 CNY。 |
| list_date | string \| null | 上市日期，格式 yyyy-MM-dd。 |
| end_date | string \| null | 合约到期日，格式 yyyy-MM-dd。 |
| last_trade_date | string \| null | 最后交易日，格式 yyyy-MM-dd。 |
| last_delivery_date | string \| null | 最后交割日，格式 yyyy-MM-dd。 |

示例：`https://datahub.10jqka.com.cn/api/meta/tickers/list?asset_type=a-share&limit=1000&offset=0`

<details>
<summary>响应示例</summary>

```json
{
  "code": 0,
  "message": "success",
  "request_id": "f7g8h9i0",
  "data": {
    "timestamp": 1716105600000,
    "item": [
      {
        "thscode": "600519.SH",
        "ticker": "600519",
        "name": "贵州茅台",
        "exchange": "SH",
        "asset_type": "a-share",
        "currency": "CNY",
        "list_date": "2001-08-27",
        "end_date": null,
        "last_trade_date": null,
        "last_delivery_date": null
      }
    ]
  }
}
```

</details>

## news

### 个股分时新闻

`GET /api/news/stock/timeline-list`

使用完整同花顺代码 thscode 查询。首屏 offset=first，后续原样回传 offset；size 省略时使用数据提供方行为。jump_url 保留原值，不保证可用于资讯详情查询。

**运行验证**：`verified_success`，`code=0`，success

**请求参数**

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|---|---|---|---|---|
| thscode | string | 是 | — | 完整同花顺代码，例如300033.SZ。 |
| offset | string | 是 | — | 分页偏移量，首屏first；后续原样回传。 |
| size | integer | 否 | — | 每页条数，范围1至100；省略使用上游行为。 |

**主要响应字段**

| 字段 | 类型 | 说明 |
|---|---|---|
| items | array | 分时新闻列表；可能为空。 |
| items[].id | string | 内容 ID。 |
| items[].type | integer 或 null | 内容类型。 |
| items[].title | string | 新闻标题。 |
| items[].author | string 或 null | 作者。 |
| items[].source | string 或 null | 新闻来源。 |
| items[].summary | string 或 null | 新闻摘要。 |
| items[].publish_time_ms | integer 或 null | Unix毫秒级时间戳；保持上游毫秒数值。 |
| items[].jump_url | string | 新闻跳转地址，非空 HTTP/HTTPS URL；不保证为密文 URL。 |
| items[].pic_url | string 或 null | 新闻图片地址。 |
| has_more | boolean | 是否还有下一页。 |
| offset | string | 下一页偏移量，用于后续分页请求。 |

示例：`https://datahub.10jqka.com.cn/api/news/stock/timeline-list?thscode=300033.SZ&offset=first`

<details>
<summary>响应示例</summary>

```json
{
  "code": 0,
  "message": "success",
  "request_id": "example-request-id",
  "data": {
    "items": [
      {
        "id": "合成示例",
        "type": 1000,
        "title": "合成示例",
        "author": "合成示例",
        "source": "合成示例",
        "summary": "合成示例",
        "publish_time_ms": 1000,
        "jump_url": "https://example.org/content",
        "pic_url": "https://example.org/content"
      }
    ],
    "has_more": true,
    "offset": "合成示例"
  }
}
```

</details>

### 公告详情与解读

`GET /api/news/notice/detail`

返回公告基本信息及结构化解读。report_period、summary、monthly_report_interpretation 可能为 null。公告序号由调用方提供。

**运行验证**：`document_example_rejected`，`code=3001`，Target not found

**请求参数**

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|---|---|---|---|---|
| seq | string | 是 | — | 不透明序号；快讯首屏传字符串0。 |

**主要响应字段**

| 字段 | 类型 | 说明 |
|---|---|---|
| seq | string | 公告序号。 |
| guid | string 或 null | 公告 GUID。 |
| title | string | 公告标题。 |
| report_period | string 或 null | 报告期，仅财报类公告有值。 |
| summary | object 或 null | 公告解读。 |
| summary.notice_type | string | 公告类型。 |
| summary.items | array | 解读项列表。 |
| summary.items[].title | string | 解读项标题。 |
| summary.items[].content | string | 解读项内容。 |
| monthly_report_interpretation | object 或 null | 月度公告解读。 |
| monthly_report_interpretation.notice_type | string | 公告类型。 |
| monthly_report_interpretation.has_findings | boolean | 是否有解读发现。 |
| monthly_report_interpretation.findings | array | 解读发现列表。 |
| monthly_report_interpretation.findings[].title | string | 发现标题。 |
| monthly_report_interpretation.findings[].blocks | array | 发现内容块。 |
| monthly_report_interpretation.findings[].blocks[].sub_title | string | 内容块小标题。 |
| monthly_report_interpretation.findings[].blocks[].content_html | string | 内容块 HTML。 |
| monthly_report_interpretation.summary_html | string | 月度解读摘要 HTML。 |

示例：`https://datahub.10jqka.com.cn/api/news/notice/detail?seq=example-notice-id`

<details>
<summary>响应示例</summary>

```json
{
  "code": 0,
  "message": "success",
  "request_id": "example-request-id",
  "data": {
    "seq": "合成示例",
    "guid": "合成示例",
    "title": "合成示例",
    "report_period": "合成示例",
    "summary": {
      "notice_type": "合成示例",
      "items": [
        {
          "title": "合成示例",
          "content": "<p>合成示例正文</p>"
        }
      ]
    },
    "monthly_report_interpretation": {
      "notice_type": "合成示例",
      "has_findings": true,
      "findings": [
        {
          "title": "合成示例",
          "blocks": [
            {
              "sub_title": "合成示例",
              "content_html": "<p>合成示例正文</p>"
            }
          ]
        }
      ],
      "summary_html": "<p>合成示例正文</p>"
    }
  }
}
```

</details>

### 快讯列表

`GET /api/news/flash/list`

首屏 seq 传字符串 0。后续传入约定序号；单次数量及翻页边界以数据提供方为准。快讯 id、seq 为字符串，tags.id 为整数。

**运行验证**：`verified_success`，`code=0`，success

**请求参数**

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|---|---|---|---|---|
| tag_id | integer | 是 | — | 快讯栏目ID。 |
| seq | string | 是 | — | 不透明序号；快讯首屏传字符串0。 |

**主要响应字段**

| 字段 | 类型 | 说明 |
|---|---|---|
| items | array | 快讯列表。 |
| items[].id | string | 不透明标识的十进制字符串，精确保留上游整数各位。 |
| items[].seq | string | 不透明标识的十进制字符串，精确保留上游整数各位。 |
| items[].title | string | 快讯标题。 |
| items[].encoded_url | string | 密文文章详情跳转地址，非空。 |
| items[].summary | string 或 null | 快讯摘要。 |
| items[].tags | array | 快讯栏目标签。 |
| items[].tags[].id | integer | 栏目标签 ID，保持上游整数类型。 |
| items[].tags[].name | string | 栏目名称。 |
| items[].type | integer | 快讯类型。 |
| items[].create_time_ms | integer | Unix毫秒级时间戳；由上游秒级值精确乘1000。 |
| items[].update_time_ms | integer | Unix毫秒级时间戳；由上游秒级值精确乘1000。 |
| items[].pic_url | string 或 null | 封面地址，无配图时可能为空。 |

示例：`https://datahub.10jqka.com.cn/api/news/flash/list?tag_id=21103&seq=0`

<details>
<summary>响应示例</summary>

```json
{
  "code": 0,
  "message": "success",
  "request_id": "example-request-id",
  "data": {
    "items": [
      {
        "id": "1000",
        "seq": "9007199254740993",
        "title": "合成示例",
        "encoded_url": "https://example.org/content",
        "summary": "合成示例",
        "tags": [
          {
            "id": 1000,
            "name": "合成示例"
          }
        ],
        "type": 1000,
        "create_time_ms": 1000000,
        "update_time_ms": 1000000,
        "pic_url": "https://example.org/content"
      }
    ]
  }
}
```

</details>

### 快讯刷新

`GET /api/news/flash/refresh`

传入已知最新 seq 和创建时间。create_time_ms 为毫秒值，须能整除 1000；调用方按业务需要处理重复记录。

**运行验证**：`verified_success`，`code=0`，success

**请求参数**

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|---|---|---|---|---|
| tag_id | integer | 是 | — | 快讯栏目ID。 |
| seq | string | 是 | — | 不透明序号；快讯首屏传字符串0。 |
| create_time_ms | integer | 是 | — | 客户端已知快讯创建时间，毫秒值须能整除1000。 |

**主要响应字段**

| 字段 | 类型 | 说明 |
|---|---|---|
| items | array | 快讯列表。 |
| items[].id | string | 不透明标识的十进制字符串，精确保留上游整数各位。 |
| items[].seq | string | 不透明标识的十进制字符串，精确保留上游整数各位。 |
| items[].title | string | 快讯标题。 |
| items[].encoded_url | string | 密文文章详情跳转地址，非空。 |
| items[].summary | string 或 null | 快讯摘要。 |
| items[].tags | array | 快讯栏目标签。 |
| items[].tags[].id | integer | 栏目标签 ID，保持上游整数类型。 |
| items[].tags[].name | string | 栏目名称。 |
| items[].type | integer | 快讯类型。 |
| items[].create_time_ms | integer | Unix毫秒级时间戳；由上游秒级值精确乘1000。 |
| items[].update_time_ms | integer | Unix毫秒级时间戳；由上游秒级值精确乘1000。 |
| items[].pic_url | string 或 null | 封面地址，无配图时可能为空。 |

示例：`https://datahub.10jqka.com.cn/api/news/flash/refresh?tag_id=21103&seq=667642844&create_time_ms=1788868800000`

<details>
<summary>响应示例</summary>

```json
{
  "code": 0,
  "message": "success",
  "request_id": "example-request-id",
  "data": {
    "items": [
      {
        "id": "1000",
        "seq": "9007199254740993",
        "title": "合成示例",
        "encoded_url": "https://example.org/content",
        "summary": "合成示例",
        "tags": [
          {
            "id": 1000,
            "name": "合成示例"
          }
        ],
        "type": 1000,
        "create_time_ms": 1000000,
        "update_time_ms": 1000000,
        "pic_url": "https://example.org/content"
      }
    ]
  }
}
```

</details>

### 热门深度专题

`GET /api/news/topic/hot-list`

按热门栏目查询专题，tab_id 由调用方提供。默认且最多 10 条，next_cursor 用于继续查询，has_more 表示是否还有下一页。时间字符串保持原格式。

**运行验证**：`verified_success`，`code=0`，success

**请求参数**

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|---|---|---|---|---|
| tab_id | integer | 是 | — | 热门专题栏目ID。 |
| cursor | string | 否 | — | 分页游标，后续查询原样回传。 |
| limit | integer | 否 | 10 | 每页条数，范围1至10。 |
| important_only | boolean | 否 | false | 是否只查询重要内容。 |

**主要响应字段**

| 字段 | 类型 | 说明 |
|---|---|---|
| items | array | 专题内容列表。 |
| items[].id | string | 不透明标识的十进制字符串，精确保留上游整数各位。 |
| items[].title | string | 标题。 |
| items[].cover | string 或 null | 封面地址。 |
| items[].url | string | 专题内容最终跳转地址，非空。 |
| items[].type | string 或 null | 内容类型。 |
| items[].seo_key | string 或 null | SEO 标识，仅配置开启时返回。 |
| items[].propagation_chain | string 或 null | 传播链路字段。 |
| items[].important_flag | integer 或 null | 重要标识。 |
| items[].pinned_flag | integer 或 null | 置顶标识。 |
| items[].pin_label | string 或 null | 置顶标签。 |
| items[].source_created_at | string 或 null | 来源创建时间。 |
| items[].source_updated_at | string 或 null | 来源更新时间。 |
| next_cursor | string 或 null | 下一页游标。 |
| has_more | boolean | 是否还有下一页。 |

示例：`https://datahub.10jqka.com.cn/api/news/topic/hot-list?tab_id=1`

<details>
<summary>响应示例</summary>

```json
{
  "code": 0,
  "message": "success",
  "request_id": "example-request-id",
  "data": {
    "items": [
      {
        "id": "9007199254740993",
        "title": "合成示例",
        "cover": "合成示例",
        "url": "https://example.org/content",
        "type": "合成示例",
        "seo_key": "合成示例",
        "propagation_chain": "合成示例",
        "important_flag": 1000,
        "pinned_flag": 1000,
        "pin_label": "合成示例",
        "source_created_at": "合成示例",
        "source_updated_at": "合成示例"
      }
    ],
    "next_cursor": "合成示例",
    "has_more": true
  }
}
```

</details>

### 日期范围异动解读

`GET /api/news/anomaly/analysis`

查询日期范围异动解读。指定标的最多返回 365 天范围，全量最多 30 天；超范围由数据提供方向结束日期截取，was_truncated 表示截断。四个时间字段保留原值，单位及标的编码格式待核实。空列表也可能表示服务降级，不能据此断言期间没有异动。

**运行验证**：`upstream_unavailable`，`code=5003`，Data source unavailable

**请求参数**

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|---|---|---|---|---|
| begin_date | string | 是 | — | 开始日期，格式yyyy-MM-dd。 |
| end_date | string | 是 | — | 结束日期，格式yyyy-MM-dd。 |
| thscode | string | 否 | — | 按上游要求提供的同花顺标的编码，格式待核实；省略查询全量。 |

**主要响应字段**

| 字段 | 类型 | 说明 |
|---|---|---|
| items | array | 异动解读列表 |
| items[].analysis_id | string | 异动解读 ID，可作为业务方幂等键使用 |
| items[].domain | string 或 null | 域 |
| items[].analysis_content | string 或 null | 解读内容 |
| items[].key_word_list | array 或 null | 关键词列表 |
| items[].anomaly_type | string 或 null | 异动类型 |
| items[].tag_code | string 或 null | 标签编码 |
| items[].tag_name | string 或 null | 标签名称 |
| items[].link_url | string | 相关内容链接地址（结果页地址） |
| items[].create_time | integer 或 null | 异动解读发生时间 |
| items[].last_anomaly_time | integer 或 null | 最后一次异动时间 |
| items[].first_publish_time | integer 或 null | 第一次进行解读的时间 |
| items[].tag_code_update_time | integer 或 null | 标签编码变更时间 |
| was_truncated | boolean | 响应数据是否被截断；true 表示结果已截断 |

示例：`https://datahub.10jqka.com.cn/api/news/anomaly/analysis?begin_date=2026-10-01&end_date=2026-10-15`

<details>
<summary>响应示例</summary>

```json
{
  "code": 0,
  "message": "success",
  "request_id": "example-request-id",
  "data": {
    "items": [
      {
        "analysis_id": "合成示例",
        "domain": "合成示例",
        "analysis_content": "<p>合成示例正文</p>",
        "key_word_list": [
          "合成示例"
        ],
        "anomaly_type": "合成示例",
        "tag_code": "合成示例",
        "tag_name": "合成示例",
        "link_url": "https://example.org/content",
        "create_time": 1000,
        "last_anomaly_time": 1000,
        "first_publish_time": 1000,
        "tag_code_update_time": 1000
      }
    ],
    "was_truncated": true
  }
}
```

</details>

### 资讯事件库

`GET /api/news/events/search`

通过受控筛选条件检索资讯事件库，返回事件标题、正文摘要、标准时间、评级及关联行业和概念。

**运行验证**：`verified_success`，`code=0`，success

**请求参数**

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|---|---|---|---|---|
| query | string | 否 | — | 标题或正文关键词，最多 200 个字符。 |
| search_param | enum | 否 | event_name | 检索域：event_name（标题）或 event_summary（正文摘要）。 |
| standard_start_time | string | 否 | — | 标准时间下界，格式 yyyy-MM-dd。 |
| standard_end_time | string | 否 | — | 标准时间上界，格式 yyyy-MM-dd。 |
| event_grading_score | string | 否 | — | 逗号分隔的评级，如 A,B。 |
| related_industry_code | string | 否 | — | 逗号分隔的关联行业代码。 |
| related_concept_code | string | 否 | — | 逗号分隔的关联概念代码。 |
| size | integer | 否 | 20 | 返回条数，范围 1-100。 |

**主要响应字段**

| 字段 | 类型 | 说明 |
|---|---|---|
| data.total | integer | 命中事件总数。 |
| data.items[] | array | 事件列表。 |
| items[].event_id / event_name / event_summary / standard_time | string \| null | 事件标识、标题、正文摘要和标准时间。 |
| items[].event_grading | object \| null | 评级对象，包含 score 与 score_reason。 |
| items[].related_industry[] / related_concept[] | array | 关联行业或概念；每项包含 code、name。 |

示例：`https://datahub.10jqka.com.cn/api/news/events/search?query=%E6%B5%99%E6%B1%9F&search_param=event_name&size=1`

<details>
<summary>响应示例</summary>

```json
{
  "code": 0,
  "message": "success",
  "request_id": "87de1ef65b134998ac8ee2a4adbec7da",
  "data": {
    "total": 1,
    "items": [
      {
        "event_id": "cbbe5a1911bde5ea11d933ecf133d718",
        "event_name": "浙江全省大范围高温天气登场",
        "event_summary": "浙江省自7月3日起受副热带高压控制，全省大部地区出现大范围高温天气，最高气温达38℃至39℃，杭州主城区最高36.4℃，迎来今年首个高温日。预计本周末多午后雷阵雨，6日至9日多云有分散性雷阵雨，防暑降温工作需加强。",
        "standard_time": "2026-07-03",
        "event_grading": {
          "score": "C",
          "score_reason": "{\"1.主体层级\": {\"理由\": \"浙江省作为经济大省，属于经济大省市政府范畴，但非国家最高决策层或全球锚点机构。\", \"得分\": 1}, \"2.事件冲击力\": {\"理由\": \"高温天气是季节性常规现象，无超预期元素或政策拐点，冲击力弱。\", \"得分\": 0}, \"3.影响范围\": {\"理由\": \"影响限于浙江省内城市群，无跨行业或全国性外溢。\", \"得分\": 1}, \"4.影响期限\": {\"理由\": \"高温天气预计持续数天至数周，属短期影响。\", \"得分\": 0}, \"5.市场与叙事强度\": {\"理由\": \"事件为气象报告，未提及市场反应或重定价，不影响金融主线。\", \"得分\": 0}, \"6.事件信息量\": {\"理由\": \"常规天气更新，无新政策或重大数据，信息量低。\", \"得分\": 0}}"
        },
        "related_industry": [],
        "related_concept": [
          {
            "code": "884073",
            "name": "制冷空调设备"
          },
          {
            "code": "884113",
            "name": "空调"
          },
          {
            "code": "882033",
            "name": "浙江"
          },
          {
            "code": "885999",
            "name": "汽车热管理"
          },
          {
            "code": "886044",
            "name": "液冷服务器"
          },
          {
            "code": "885425",
            "name": "特高压"
          }
        ]
      }
    ]
  }
}
```

</details>

### 资讯详情

`GET /api/news/article/detail`

仅返回可对外提供的资讯。正文保留 HTML；展示时按内容安全策略处理。不存在或不可提供时返回业务错误。

**运行验证**：`document_example_rejected`，`code=1002`，Invalid parameter format

**请求参数**

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|---|---|---|---|---|
| client_type | string | 是 | — | 客户端类型：WEB、WEB_ENCRYPTED、PC、PC_LIST，不区分大小写。 |
| encoded_seq | string | 是 | — | 密文资讯标识。 |

**主要响应字段**

| 字段 | 类型 | 说明 |
|---|---|---|
| encoded_seq | string | 请求中的密文资讯序列号；不返回明文 seq。 |
| title | string | 资讯标题。 |
| author | string 或 null | 作者；缺失时显式返回 null。 |
| summary | string 或 null | 摘要；缺失时显式返回 null。 |
| content | string | HTML 正文。 |
| source | string 或 null | 来源名称；缺失时显式返回 null。 |
| publish_time_ms | integer | Unix毫秒级时间戳；由上游秒级值精确乘1000。 |
| is_kuaixun | boolean 或 null | 是否为快讯；缺失时显式返回 null。 |

示例：`https://datahub.10jqka.com.cn/api/news/article/detail?client_type=WEB&encoded_seq=example-encoded-id`

<details>
<summary>响应示例</summary>

```json
{
  "code": 0,
  "message": "success",
  "request_id": "example-request-id",
  "data": {
    "encoded_seq": "合成示例",
    "title": "合成示例",
    "author": "合成示例",
    "summary": "合成示例",
    "content": "<p>合成示例正文</p>",
    "source": "合成示例",
    "publish_time_ms": 1000000,
    "is_kuaixun": true
  }
}
```

</details>

## options

### 期权合约基础信息列表

`GET /api/options/contracts/list`

从完整期权目录快照分页获取合约基础信息。

**运行验证**：`verified_success`，`code=0`，success

**请求参数**

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|---|---|---|---|---|
| limit | integer | 否 | 100 | 单页条数，范围 1-1000。 |
| offset | integer | 否 | 0 | 分页偏移，最小为 0。 |

**主要响应字段**

| 字段 | 类型 | 说明 |
|---|---|---|
| timestamp | long | 数据时间，毫秒时间戳。 |
| total | integer | 合约总数。 |
| item[] | array | 合约基础信息列表。 |

示例：`https://datahub.10jqka.com.cn/api/options/contracts/list?limit=100&offset=0`

<details>
<summary>响应示例</summary>

```json
{
  "code": 0,
  "message": "success",
  "request_id": "request-id",
  "data": {
    "timestamp": 1789036800000,
    "total": 1,
    "item": [
      {
        "thscode": "IO2601-C-4000.CFE",
        "ticker": "IO2601-C-4000",
        "name": "沪深300股指期权",
        "exchange_code": "CFFEX",
        "variety_code": "IO",
        "list_date": "2026-01-01",
        "end_date": "2026-01-16",
        "last_trade_date": "2026-01-16",
        "last_delivery_date": "2026-01-16"
      }
    ]
  }
}
```

</details>

### 期权合约详情

`GET /api/options/contracts/detail`

期权合约基础资料提供单个合约详情与分页合约目录。

**运行验证**：`verified_success`，`code=0`，success（使用替代有效样例）

**请求参数**

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|---|---|---|---|---|
| thscode | string | 是 | — | 期权合约完整同花顺代码。 |

**主要响应字段**

| 字段 | 类型 | 说明 |
|---|---|---|
| timestamp | long | 数据时间，毫秒时间戳。 |
| thscode / ticker / display_code | string \| null | 完整代码、纯代码与展示代码。 |
| name / variety_code / pinyin | string \| null | 合约名称、品种代码与拼音。 |
| list_date | string \| null | 合约上市日期；来源缺失时为 null。 |
| end_date | string \| null | 合约上市结束日期。 |
| last_trade_date / last_delivery_date | string \| null | 最后交易日与最后交割日；来源缺失时为 null。 |
| margin_rate / strike_price | number \| null | 保证金率与行权价。 |
| trade_amount | number \| null | 合约交易单位数量。 |
| underlying_code | string \| null | 上游标的代码，不保证为规范 thscode。 |
| exercise_style | string \| null | 行权方式：bermudan、american 或 european。 |
| option_type | string \| null | 期权方向：call 或 put。 |

示例：`https://datahub.10jqka.com.cn/api/options/contracts/detail?thscode=IO2601-C-4000.CFE`

<details>
<summary>响应示例</summary>

```json
{
  "code": 0,
  "message": "success",
  "request_id": "request-id",
  "data": {
    "timestamp": 1789036800000,
    "thscode": "IO2601-C-4000.CFE",
    "ticker": "IO2601-C-4000",
    "display_code": "IO2601-C-4000",
    "name": "沪深300股指期权",
    "variety_code": "IO",
    "pinyin": null,
    "list_date": "2026-01-01",
    "end_date": "2026-01-16",
    "last_trade_date": "2026-01-16",
    "last_delivery_date": "2026-01-16",
    "margin_rate": null,
    "underlying_code": "IF2601",
    "strike_price": 4000,
    "exercise_style": "european",
    "option_type": "call",
    "trade_amount": 100
  }
}
```

</details>

### 期权交易时间轴

`GET /api/options/calendar/session-timeline`

期权交易时间轴提供合约最近交易日的交易阶段、交易所阶段与跨日时间范围。

**运行验证**：`verified_success`，`code=0`，success（使用替代有效样例）

**请求参数**

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|---|---|---|---|---|
| thscode | string | 是 | — | 期权合约完整同花顺代码。 |

示例：`https://datahub.10jqka.com.cn/api/options/calendar/session-timeline?thscode=IO2601-C-4000.CFE`

<details>
<summary>响应示例</summary>

```json
{
  "code": 0,
  "message": "success",
  "request_id": "request-id",
  "data": {
    "timestamp": 1789036800000,
    "thscode": "IO2601-C-4000.CFE",
    "trade_date": "2026-09-10",
    "timezone": "Asia/Shanghai",
    "trade_stages": [],
    "exchange_sessions": []
  }
}
```

</details>

### 期权品种资料

`GET /api/options/varieties/list`

期权品种资料提供期权品种目录及交易属性。 无业务参数。

**运行验证**：`verified_success`，`code=0`，success

**请求参数**

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|---|---|---|---|---|
| — | — | — | — | 无业务参数。 |

**主要响应字段**

| 字段 | 类型 | 说明 |
|---|---|---|
| timestamp | long | 数据时间，毫秒时间戳。 |
| item[] | array | 期权品种列表。 |
| item[].variety_code / name | string \| null | 品种代码与名称。 |
| item[].exchange_code / exchange_name | string \| null | 交易所代码与名称。 |
| item[].has_night_session | boolean \| null | 是否包含夜盘。 |
| item[].margin_rate | number \| null | 保证金率。 |
| item[].trade_amount | number \| null | 品种交易单位数量，单位由 trade_unit 字段给出。 |
| item[].price_coefficient / tick_size / contract_multiplier | number \| null | 价格系数、最小变动价位与合约乘数。 |
| item[].price_unit / trade_unit | string \| null | 价格单位与交易单位。 |
| item[].transaction_fee / exercise_fee | number \| null | 交易手续费与行权手续费。 |
| item[].settlement_type | string \| null | 品种交割方式：physical-实物交割、cash-现金交割。 |
| item[].trade_sessions[] | array | 交易时段；每项含 start_time、end_time、session_type。 |

示例：`https://datahub.10jqka.com.cn/api/options/varieties/list`

<details>
<summary>响应示例</summary>

```json
{
  "code": 0,
  "message": "success",
  "request_id": "request-id",
  "data": {
    "timestamp": 1789036800000,
    "item": [
      {
        "variety_code": "IO",
        "name": "沪深300股指期权",
        "exchange_code": "CFFEX",
        "exchange_name": "中国金融期货交易所",
        "has_night_session": false,
        "margin_rate": null,
        "trade_amount": 100,
        "price_coefficient": 1,
        "price_unit": "点",
        "trade_unit": "乘数",
        "tick_size": 0.2,
        "contract_multiplier": 100,
        "transaction_fee": null,
        "exercise_fee": null,
        "settlement_type": "cash",
        "trade_sessions": []
      }
    ]
  }
}
```

</details>

### 期权分时

`GET /api/options/prices/intraday`

期权行情提供合约分时和 K 线数据；支持历史交易日分时及多周期 K 线。

**运行验证**：`verified_success`，`code=0`，success（使用替代有效样例）

**请求参数**

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|---|---|---|---|---|
| thscode | string | 是 | — | 期权合约完整同花顺代码。 |
| session | enum | 否 | — | 行情阶段：pre_market-盘前、intraday-盘中、post_market-盘后；省略时使用 intraday。 |
| trade_date | string | 否 | — | 可传 0 或合法历史交易日 yyyyMMdd。 |

**主要响应字段**

| 字段 | 类型 | 说明 |
|---|---|---|
| timestamp | long | 数据时间，毫秒时间戳。 |
| thscode / date / session | string | 合约代码、当前或最近交易日与行情阶段。 |
| item[] | array | 分时点列表；每项含可空的 timestamp、price、volume、turnover。 |

示例：`https://datahub.10jqka.com.cn/api/options/prices/intraday?thscode=IO2601-C-4000.CFE&session=intraday`

<details>
<summary>响应示例</summary>

```json
{
  "code": 0,
  "message": "success",
  "request_id": "request-id",
  "data": {
    "timestamp": 1789036800000,
    "thscode": "IO2601-C-4000.CFE",
    "date": "2026-09-10",
    "session": "intraday",
    "item": [
      {
        "timestamp": 1789036860000,
        "price": 35.2,
        "volume": 12,
        "turnover": 42240
      }
    ]
  }
}
```

</details>

### 期权K线

`GET /api/options/prices/daily`

期权行情提供合约分时和 K 线数据；支持历史交易日分时及多周期 K 线。

**运行验证**：`verified_success`，`code=0`，success（使用替代有效样例）

**请求参数**

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|---|---|---|---|---|
| thscode | string | 是 | — | 期权合约完整同花顺代码。 |
| start | long | 否 | — | 与 end 成对提供的正毫秒时间戳；两者均省略时查询最近 100 根。 |
| end | long | 否 | — | 与 start 成对提供的正毫秒时间戳，且不早于 start。 |
| time_period | enum | 否 | — | 可使用 min_1、min_10、hour_1、day_1、week_1、month_1、quarter_1、year_1。 |

**主要响应字段**

| 字段 | 类型 | 说明 |
|---|---|---|
| timestamp | long | 数据时间，毫秒时间戳。 |
| thscode | string | 期权合约代码。 |
| interval | string | 实际返回的 K 线周期。 |
| item[] | array | 日 K 列表；每项含可空的 timestamp、open_price、high_price、low_price、close_price、volume、turnover。 |

示例：`https://datahub.10jqka.com.cn/api/options/prices/daily?thscode=IO2601-C-4000.CFE`

<details>
<summary>响应示例</summary>

```json
{
  "code": 0,
  "message": "success",
  "request_id": "request-id",
  "data": {
    "timestamp": 1789036800000,
    "thscode": "IO2601-C-4000.CFE",
    "interval": "1d",
    "item": [
      {
        "timestamp": 1788950400000,
        "open_price": 34.8,
        "high_price": 36.1,
        "low_price": 34.2,
        "close_price": 35.2,
        "volume": 120,
        "turnover": 422400
      }
    ]
  }
}
```

</details>


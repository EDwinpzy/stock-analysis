---
name: industry-analysis
description: '采集并分析行业概览、竞争格局、产业链、核心标的与风险，生成报刊风格（微软雅黑单栏）HTML深度分析报告。'
metadata:
  legacy_version: "9.0.0"
  legacy_author: "WorkBuddy"
  agent_created: "true"
  critical_rules: |
    NEVER use Agent tool with run_in_background:true — it causes hangs/cancellations
    NEVER launch multiple Agents in parallel — always execute sequentially one at a time
    NEVER use custom subagent_types (industry-researcher etc) — they are not registered
    ALWAYS execute all 3 steps yourself in the main thread, sequentially
    If WebSearch/WebFetch fails, SKIP and continue — never hang waiting for data (30秒超时)
    报告生成后输出对话总结+URL编码的Markdown文件链接，不打开外部浏览器
    报告输出后要在对话里给个可点击的链接
    标题和文字用中文，专有名词保留英文(CoWoS/UCIe/Chiplet/ABF/HBM/ATE等)
    wencai_nlp批量查询一次获取全部数据，禁止拆分多次调用同一批标的的不同指标（最大性能瓶颈）
    数据采集总Bash调用数≤3次：1次主数据+1次补充(如需)+1次WebSearch(可选)
    重点分析主板的个股：同行对比/配置建议/首选标的优先选主板(60/00开头)，科创板/创业板标的作为弹性补充而非首选
    报告章节固定8章，不可增删
    CSS样式严格使用报刊风格变量体系（米白纸面+微软雅黑+单栏正文），不得修改
    正文固定单栏：8章顺序铺满，禁止再分左右两栏、禁止给章节加 .fw
    只生成HTML文件，禁止生成图片(png/jpg/svg等)、Markdown(.md)、PDF、Word等其他格式文件
  data_sources: |
    ths-advanced-analysis（主数据源：板块行情/成分股/问财NLP/财务数据/机构预测）
    WebSearch + WebFetch（辅助数据源，可用时补充行业研报/市场规模等）
    公司年报/季报（财务数据权威来源）
  style_reference: "本SKILL内嵌报刊风格设计规范（与 daily-briefing-pro 的简报/行情版面统一）"
  original_name: "行业分析"
---

# 行业/产业链深度分析报告

# 行业/产业链深度分析报告 v9.0

## 概述

本技能生成标准化的行业/产业链深度分析HTML报告，覆盖8-15个核心标的，按 **报刊风格（米白新闻纸 + 微软雅黑 + 单栏正文 + 居中报头）** 输出，与 `daily-briefing-pro` 的每日简报、行情版面共用同一套「报纸」纸面与语义色。

采用 **主线程顺序执行架构**，由主Agent按步骤依次完成数据采集、分析、报告生成，确保稳定可靠不卡住。

---

## 🚫🚫🚫 绝对禁止事项（违反必卡住）🚫🚫🚫

1. **禁止 `Agent` 工具 + `run_in_background: true`** — 后台Agent在Codex中不稳定，会被取消/超时
2. **禁止同时启动多个Agent并行** — 并行Agent互相干扰，任何一个失败整个流程卡死
3. **禁止使用自定义 subagent_type**（如 industry-researcher / chain-analyst / stock-screener / risk-doctor）— 这些不是注册的agent类型，调度必然失败
4. **禁止生成HTML以外的任何文件** — 不生成图片(png/jpg/svg)、Markdown(.md)、PDF、Word、JSON数据文件等。唯一输出产物是HTML报告文件

**唯一正确做法：主Agent自己按3步顺序执行，每一步完成后才进入下一步。**

---

## 触发条件

用户输入包含以下模式时触发：
- "XX行业分析""XX产业链分析""XX行业深度""分析XX行业"
- 用户给出行业/赛道名称要求出报告
- "XX详细拆解""XX上下游分析"

## 去重规则（生成前必做）

1. 收到行业分析请求后，第一步用 `Bash ls+grep` 搜索工作目录下是否已有匹配HTML报告
2. 搜索关键词：行业名核心词（如"机器人"→`*机器人*`、"半导体材料"→`*半导体材料*`）
3. **已有报告** → 输出URL编码的Markdown链接到对话中，告知"已找到现成报告"，不重新搜索/生成
4. **无报告** → 进入完整生成流程
5. **用户明确说"更新"/"重新生成"** → 即使有旧报告也重新生成

---

## 执行流程（3步精简版）

### Step 1：批量数据采集（目标：2-3次Bash调用完成全部数据获取）

> ⚠️ 本步骤由主Agent自己执行。核心原则：**合并查询、一次拿齐、避免重复**。WebSearch失败则跳过继续（超时30秒）。

#### 调用1：一次性获取所有标的的完整财务数据

将所有需要的标的、所有需要的指标合并到**一次** `wencai_nlp` 调用中。这是最关键的性能优化——每次调用 `wencai_nlp` 都要建立THS连接，拆分调用会浪费时间。

```python
from thsdk import THS
import pandas as pd

with THS() as ths:
    # ---- 第一部分：发现标的 ----
    # 方法A：如果行业有对应概念板块
    concept_df = ths.ths_concept().df
    target = concept_df[concept_df['名称'].str.contains('{行业关键词}', na=False)]
    if len(target) > 0:
        members = ths.block_constituents(target.iloc[0]['代码']).df
        stocks_str = '或'.join(members['名称'].head(15))
    else:
        # 方法B：无概念板块时，用wencai_nlp直接搜索
        resp = ths.wencai_nlp('{行业关键词}概念股，市盈率，总市值，非ST')
        # 从结果中提取核心标的（按市值排序取前15）
        candidate_df = resp.df
        candidate_df['总市值亿'] = candidate_df['总市值[20260713]'] / 1e8
        top_stocks = candidate_df.nlargest(15, '总市值亿')
        stocks_str = '或'.join(top_stocks['股票简称'].tolist())

    # ---- 第二部分：一次查询所有标的的所有指标 ----
    # 关键：把年报、Q1、增速、涨幅全部放在一次查询中
    all_query = (
        f'{stocks_str}，'
        f'市盈率，总市值，'
        f'2025年营业收入，2025年归属于母公司所有者的净利润，2025年销售毛利率，2025年净资产收益率ROE，'
        f'2026年一季度营业收入，2026年一季度归属于母公司所有者的净利润，2026年一季度销售毛利率，'
        f'2025年归属母公司股东的净利润同比增长率，2025年营业收入同比增长率，'
        f'2026年一季度归属母公司股东的净利润同比增长率，'
        f'年初至今涨跌幅，'
        f'非ST'
    )
    resp = ths.wencai_nlp(all_query)
    df = resp.df

    # ---- 第三部分（可选）：补充标的 ----
    # 如果第一轮结果不足，补充行业上下游相关标的
    # 只在标的不足8个时才执行，且只补充1次
    if len(df) < 8:
        supplement = '{补充标的A}或{补充标的B}或{补充标的C}'
        resp2 = ths.wencai_nlp(
            f'{supplement}，'
            f'市盈率，总市值，'
            f'2025年营业收入，2025年归属于母公司所有者的净利润，2025年销售毛利率，2025年净资产收益率ROE，'
            f'年初至今涨跌幅，非ST'
        )
        # 合并去重
        df = pd.concat([df, resp2.df]).drop_duplicates(subset='股票代码')

# 数据清洗：统一单位
df['总市值亿'] = df['总市值[20260713]'] / 1e8
df['营收亿'] = df['营业收入[20251231]'] / 1e8
df['净利亿'] = df['归属于母公司所有者的净利润[20251231]'] / 1e8
# ... 按需转换
```

#### 调用2（可选）：WebSearch补充行业宏观

```python
# 仅当需要市场规模/增速等宏观数据时执行，30秒超时
# 搜索失败直接跳过，用行业常识替代
```

#### ⚠️ 数据采集效率铁律

1. **一次wencai_nlp拿齐所有指标**：年报数据、Q1数据、增速、涨幅、ROE全部放在一次查询中。拆分调用是最常见的性能浪费。
2. **补充标的不超过1次**：如果第一轮标的不足8个，只补充1次，不要反复追加。
3. **跳过无效查询**：`ths_concept` 大部分行业返回空，不要因为没找到概念板块就卡住，直接用 wencai_nlp 搜索。
4. **总Bash调用数≤3次**：1次主数据查询 + 1次补充（如需） + 1次WebSearch（可选）。超过3次说明查询策略有问题。
5. **单个THS连接内完成所有查询**：`with THS() as ths:` 块内执行全部 thsdk 调用，避免反复建立/断开连接。

### Step 2：产业链分析 + 风险诊断

> ⚠️ 本步骤由主Agent自己执行，基于Step 1数据直接分析。

```
基于Step 1获取的成分股和财务数据：
1. 按上中下游分类（基于公司主营业务描述）
2. 筛选核心标的，按梯队/弹性排序
3. 标注涨幅风险（近60日涨幅>80%标"涨幅透支风险")
4. 识别6-8条风险（行业/政策/技术/竞争/估值等）
5. 提炼投资逻辑（3-4行精炼）
6. 整理客户订单信息（区分🟢实锤/⚠️传闻）
```

**产出**：
- 产业链Pipeline（上中下游）
- 竞争格局分析（全球+国内梯队）
- 投资逻辑与配置建议
- 客户订单信息表
- 同行核心指标对比表
- 风险提示（6-8条）
- 核心结论

### Step 3：汇编HTML报告

> ⚠️ 本步骤由主Agent自己执行，将Step 1-2结论写入固定模板。

```
Step 1-2全部结论 → 填充固定HTML模板 → 写入文件 → 对话中提供链接
```

---

## 数据源优先级

| 优先级 | 数据源 | 用途 | 可靠性 |
|--------|--------|------|--------|
| 1 | thsdk wencai_nlp | 标的筛选/财务数据/行业排名 | ✅ 高 |
| 1 | thsdk ths_concept/block_constituents | 概念板块/成分股 | ✅ 高 |
| 1 | thsdk market_data_block | 板块行情/市值 | ✅ 高 |
| 2 | WebSearch | 行业市场规模/增速/政策/研报 | ⚠️ 可能不可用 |
| 2 | WebFetch | 抓取研报/文章详细数据 | ⚠️ 可能不可用 |

**降级规则**：
- WebSearch/WebFetch不可用 → 跳过，不卡住，用thsdk数据+行业常识完成报告
- thsdk不可用 → 尝试WebSearch/WebFetch，若也不可用则标注"数据获取降级"
- **禁止伪造**：降级时如实标注，绝不凭空编造

---

## 数据铁律

1. **财务数据** → 从thsdk/公开年报获取，不可捏造
2. **客户订单** → 严格区分 🟢实锤（公告/年报/互动平台）和 ⚠️传闻（雪球/自媒体）
3. **无法验证的数据** → 标记 `[UNSOURCED]`
4. **每条数据标注来源**
5. **数字可追溯** → 禁止凭空编造市场规模/增速/市占率等关键数字

---

## 报告结构（固定8章）

| # | 章节 | 内容 | 对应HTML结构 |
|---|------|------|-------------|
| 1 | **行业概览** | KV数据卡(8个) + 三大催化表 + 产业链结构图 | `.sec` > `.sh` + `.sb` > `.kv` + `.dt` + `.icc` |
| 2 | **竞争格局** | 全球格局表 + 国内梯队分化表 | `.sec` > `.sh` + `.sb` > `.sc` > `.sch` + `.scb` > `.dt` |
| 3 | **核心标的深度** | 每个标的KV卡(8个) + 文字分析 + 配套标的表 | `.sec` > `.sh` + `.sb` > `.sc` > `.sch` + `.scb` > `.kv` + `p` + `.dt` |
| 4 | **客户订单信息** | 客户/产品/状态/来源表 | `.sec` > `.sh` + `.sb` > `.dt` |
| 5 | **同行核心指标对比** | 多标的财务+估值+客户对比表 | `.sec` > `.sh` + `.sb` > `.dt` |
| 6 | **投资逻辑与配置建议** | 弹性排序表 + 板块轮动表 + 配置建议 | `.sec` > `.sh` + `.sb` > `.lb.gold` + `.sc` > `.dt` |
| 7 | **风险提示** | 6-8条具体风险 | `.sec` > `.sh` + `.sb` > `.lb.warn` |
| 8 | **核心结论** | 一句话总结 + KV数据卡(4-6个) + 来源标注 | `.sec` > `.sh` + `.sb` > `.lb.gold` + `.kv` + `.src` |

8个 `.sec` 全部放在同一个 `<div class="g">` 内，**单栏顺序铺满**，顺序不可调换，且都不带任何分栏类。

### 章节详细规范

#### 一、行业概览

**KV数据卡**：8个数据节点，4列2行网格布局（≤960px 为2列），每个节点包含：
- `.kvk`：标签（11px，淡墨，字距 .08em）
- `.kvv`：数值（21px，雅黑粗体，红色=上涨/绿色=下跌/墨金=强调）
- `.kvsub`：辅助说明（11px，淡墨）

**三大催化表**：3行3列表格
- 表头：催化 | 驱动逻辑 | 关键数据
- 催化列用墨金高亮（`.gold`）

**产业链结构图**：横向流程图（`.cf`），5个环节
- 核心零部件 → 本行业(墨金高亮) → 配套设备 → 耗材 → 下游应用
- 每个环节用 `.cfi` 卡片，中间用报头红箭头 `.arr` 连接

#### 二、竞争格局

**全球格局表**：对比海外龙头（如爱德万vs泰瑞达），维度包括国家/市占率/核心平台/营收/PE/客户/中国份额

**国内梯队分化表**：3个梯队
- 第一梯队（金色）：首选标的，标注`<span class="st gold">首选</span>`
- 第二梯队（青色）：核心标的，标注`<span class="st mb2">核心</span>`
- 第三梯队（灰色）：配套/弹性标的

每个标的列：公司名(代码) | 卡位 | 国产化率 | 竞争壁垒

#### 三、核心标的深度

每个核心标的独立一个 `.sc` 子章节，包含：
- **标题行**：`.sch` 含 `#` 标记 + 标的名称 + 标签(定位) + 中报预期标签(`.tag2.zb`高增/`.tag2.yq`改善)
- **KV数据卡**：8个指标（市值/股价、PE TTM、营收/净利、毛利率、ROE、关键增速、关键突破等）
- **文字分析**：1段12px灰色文字，末尾用橙色粗体标注风险提示，用青色标注估值优势
- **配套标的表**：6-8个配套标的，列：标的 | 卡位 | 核心数据 | 看点

#### 四、客户订单信息

表格列：标的 | 客户名称 | 产品/服务 | 状态 | 来源
- 状态列：🟢 实锤（绿色） / ⚠️ 传闻
- 同一标的多个客户用 `rowspan` 合并
- 底部来源说明

#### 五、同行核心指标对比

表格列：标的 | 板块 | 2025营收(亿) | 2025净利(亿) | 毛利率 | ROE | PE TTM | 市值(亿) | 中报预期 | 核心客户 | 国产化壁垒
- 上涨数据用红色 `.up`，下跌用绿色 `.dn`，金色强调 `.gold`
- 中报预期用 `.tag2.zb`(高增) / `.tag2.yq`(改善)
- 主板标的板块列用金色标注，主板标的排在表格前面优先展示

#### 六、投资逻辑与配置建议

**配置建议**：`.lb.gold` 面板，4行精炼建议
- 主板首选：XX — 关键数据（主板标的优先推荐）
- 首选：XX — 核心逻辑
- 估值安全：XX — 关键数据
- 高弹性：XX — 核心逻辑，但风险提示

**弹性排序表**：列：细分赛道 | 国产化率 | 替代空间 | 核心标的 | 弹性(★评级)

**板块轮动表**（可选）：列：阶段 | 受益顺序 | 代表标的 | 当前阶段

#### 七、风险提示

`.lb.warn` 面板，6-8条风险，每条用 `.li` 列表项：
- 板块估值高企风险
- 涨幅透支风险
- 技术迭代风险
- 客户验证周期风险
- 地缘政治风险
- 下游CAPEX周期风险
- 竞争加剧风险
- 科创板流动性风险（如适用）

#### 八、核心结论

**一句话总结**：`.lb.gold` 面板，1行金色粗体大字(14px)

**KV数据卡**：4-6个核心数据节点
- 行业评级 | 首选标的 | 估值洼地 | 最大弹性 | 其他关键数据

**来源标注**：`.src` 等宽字体，列出所有数据来源

---

## 报刊风格设计规范（微软雅黑 · 单栏）

### 美学方向

**报纸新闻纸风格** — 米白纸面 + 油墨黑 + 微软雅黑 + 红涨绿跌（A股惯例）+ 墨金强调首选/高优先级。顶部居中报头（上下双线），正文单栏铺满、宽表整幅展开。整体呈现铅印金融报刊、信息密度高、线框克制的文档气质，同时保证中文小字号清晰可读。

与 `daily-briefing-pro` 的每日简报、个股行情版面共用同一套「报纸」纸面与语义色。

> **字体选择说明**：正文字体必须用 **微软雅黑（Microsoft YaHei）无衬线栈**，不要用宋体/衬线。
> 原因：Windows 上 `Noto Serif SC`、`Source Han Serif SC`、`Songti SC` 都不存在，回退到 `SimSun`（宋体），
> 在 10–13px 的中文小字号下笔画过细、发虚发糊，可读性差。微软雅黑在同样的字号下清晰得多。
> 字号上也做了配套放大：正文字号提到 13.5px，最小的辅助文字不再低于 10.5px。

### 色彩系统

```css
:root{
  /* 纸面与油墨 */
  --paper:#f5f1e8;   /* 纸面：米白新闻纸 */
  --ink:#1b1915;     /* 油墨：正文黑 */
  /* 层级背景 */
  --bg:#f5f1e8;      /* 页面底：纸面 */
  --bg2:#fffdf8;     /* 卡片面：稍亮纸白 */
  --bg3:#f1ece1;     /* 第三层：浅牛皮纸 */
  --bg4:#e6dfd0;     /* 刻度/进度条底 */
  /* 铅线 */
  --bd:rgba(27,25,21,.16);   /* 细铅线 */
  --bd2:rgba(27,25,21,.34);  /* 粗铅线/强调边 */
  /* 文字 */
  --t1:#1b1915;      /* 主文字：油墨黑 */
  --t2:#45413a;      /* 次要文字：深灰墨 */
  --t3:#7c7566;      /* 辅助文字：淡墨 */
  /* 语义色 */
  --up:#b3261e;      /* 红：上涨/增长/盈利/利好（A股红涨） */
  --dn:#1c6b46;      /* 绿：下跌/亏损/低国产化率（A股绿跌） */
  --inf:#1f4e79;     /* 蓝：表头/标签/核心 */
  --cyn:#155e63;     /* 青：第二梯队/配套 */
  --gld:#8a6a12;     /* 墨金：首选/高优先级/强调 */
  --wrn:#9a5b00;     /* 棕橙：警告/风险提示/中性 */
  --a:#8c1c13;       /* 报头红：刊头/报眼/竖线强调 */
  /* 字体：微软雅黑无衬线栈（清晰优先），不加载任何外部字体 */
  --sans:'Microsoft YaHei UI','Microsoft YaHei','PingFang SC','HarmonyOS Sans SC','Hiragino Sans GB','Segoe UI',system-ui,-apple-system,sans-serif;
  --serif:var(--sans);
  --display:var(--sans);
  --mono:var(--sans);
}
```

### 颜色语义（红涨绿跌，A股惯例）

| 颜色 | 变量 | 语义 |
|------|------|------|
| 红 `#b3261e` | `--up` | 上涨/增长/盈利/利好 |
| 绿 `#1c6b46` | `--dn` | 下跌/亏损/低国产化率/安全边际 |
| 墨金 `#8a6a12` | `--gld` | 首选/高优先级/强调/第一梯队 |
| 蓝 `#1f4e79` | `--inf` | 表头/标签/核心 |
| 棕橙 `#9a5b00` | `--wrn` | 警告/风险提示/中性 |
| 青 `#155e63` | `--cyn` | 第二梯队/配套/改善 |
| 报头红 `#8c1c13` | `--a` | 刊头/报眼/版式强调 |

> 语义色一律从 `:root` 变量引用，禁止写死十六进制色值；禁止再出现 `--ar/--ag/--ay/--ab/--ao/--ac` 这套旧变量名。

### 版式规范：报头 + 单栏正文（本版核心）

页面骨架固定为「报头 → 单栏正文容器 `.g` → 页脚」，`<body>` 内不使用 `.hero`：

```html
<div class="c">

  <!-- 报头：居中，上单线 + 下双线 -->
  <div class="np-mast">
    <div class="np-mast-kicker">{行业英文名} INDUSTRY</div>
    <div class="np-mast-title">{行业名称}行业深度分析</div>
    <div class="np-mast-sub">
      <span>{日期}</span><span class="sep">|</span>
      <span>数据日 {数据日期}</span><span class="sep">|</span>
      <span>覆盖标的 <b>{N}</b></span><span class="sep">|</span>
      <span>{技术关键词}</span>
    </div>
  </div>

  <!-- 正文：单栏，8章顺序铺满 -->
  <div class="g">
    <div class="sec">…</div>      <!-- 一、行业概览 -->
    <div class="sec">…</div>      <!-- 二、竞争格局 -->
    <div class="sec">…</div>      <!-- 三、核心标的深度 -->
    <div class="sec">…</div>      <!-- 四、客户订单信息 -->
    <div class="sec">…</div>      <!-- 五、同行核心指标对比 -->
    <div class="sec">…</div>      <!-- 六、投资逻辑与配置建议 -->
    <div class="sec">…</div>      <!-- 七、风险提示 -->
    <div class="sec">…</div>      <!-- 八、核心结论 -->
  </div>

  <div class="ft">…</div>
</div>
```

- `.g{display:grid;grid-template-columns:minmax(0,1fr);gap:18px;align-items:start}` —— **单栏**：没有中缝竖线，也没有 `.fw` 这个概念
- 8章 `.sec` 顺序不可调换，全部等宽铺满正文宽度；宽表（5列/11列）直接整幅铺开，不需要任何宽度约束
- 单栏天然响应式，窄屏无需特殊处理（仅保留 `≤960px` 的 `.kv` 两列降级）
- ⚠️ 不要再给章节加宽度限制、浮动或再套一层栅格；也不要恢复 `fw` 类名

### 组件规范

| 组件 | CSS类 | 描述 |
|------|-------|------|
| **报头** | `.np-mast` > `.np-mast-kicker` + `.np-mast-title` + `.np-mast-sub` | 居中报头：上单线+下双线，报头红英文刊头 + 雅黑大字标题 + 分隔点信息行 |
| **正文容器** | `.g` | 单栏网格容器，8章顺序铺满；不分栏、无中缝竖线 |
| **Section** | `.sec` > `.sh` + `.sb` | 可折叠章节：纸白卡片 + 顶部2px铅线 + 点击折叠 |
| **Sub-section** | `.sc` > `.sch` + `.scb` | 可折叠子章节：浅牛皮纸标题条 + 左侧报头红竖条 |
| **KV Grid** | `.kv` > `.kvi` | 数据节点网格：4列(≤960px为2列)，卡顶2px铅线 |
| **Data Table** | `.dt` | 数据表格：雅黑小字距表头 + 铅印细线 + 悬停泛红 |
| **Stock Label** | `.st` | 标的标签：首选(墨金)/核心(蓝)/弹性(青)/主板(棕橙)，一律描边铅字章 |
| **中报预期** | `.tag2` | 中报预期标签：高增(红)/改善(墨金)，描边式 |
| **Valuation** | `.vp` | 估值标签：低(红)/中(棕橙)/高(绿)，描边式 |
| **Logic Box** | `.lb` / `.lb.gold` / `.lb.warn` | 核心观点面板：左侧3px彩色边条 |
| **Chain Flow** | `.icc` > `.cf` > `.cfi` | 产业链流程图：横向卡片+报头红箭头 |
| **Source** | `.src` | 来源标注：小字淡墨 |
| **Footer** | `.ft` | 免责声明：居中淡墨 + 顶部铅线 |

### 标的标签规范

```html
<span class="st gold">首选</span>    <!-- 墨金描边铅字章，第一梯队首选 -->
<span class="st mb2">核心</span>     <!-- 蓝色描边，核心标的 -->
<span class="st cy">弹性</span>      <!-- 青色描边，高弹性标的 -->
<span class="st kc">主板</span>      <!-- 棕橙描边，主板标的 -->
```

### 中报预期标签规范

```html
<span class="tag2 zb">高增</span>   <!-- 红色描边，业绩高增 -->
<span class="tag2 yq">改善</span>   <!-- 墨金描边，业绩改善 -->
```

### 数据颜色规范

```html
<td class="up">+110%</td>           <!-- 红色：上涨/增长 -->
<td class="dn">~10%</td>            <!-- 绿色：下跌/低占比 -->
<td class="gold">极高</td>          <!-- 墨金：强调 -->
```

### KV数据卡规范

```html
<div class="kvi">
  <div class="kvk">标签名</div>           <!-- 10.5px 淡墨字距 .1em -->
  <div class="kvv up">$112亿</div>        <!-- 21px 雅黑粗体，up=红/dn=绿/gold=墨金 -->
  <div class="kvsub">来源 · 同比+48%</div> <!-- 10px 淡墨辅助 -->
</div>
```

### 产业链结构图规范

```html
<div class="cf">
  <div class="cfi"><div class="cfn">核心零部件</div><div class="cfd">PE芯片/ASIC<br>FPGA/精密机械</div></div>
  <span class="arr">→</span>
  <div class="cfi" style="border-top-color:var(--gld)"><div class="cfn" style="color:var(--gld)">★ 本行业</div><div class="cfd">描述</div></div>
  <span class="arr">→</span>
  <div class="cfi"><div class="cfn">配套设备</div><div class="cfd">描述</div></div>
  <span class="arr">→</span>
  <div class="cfi"><div class="cfn">耗材</div><div class="cfd">描述</div></div>
  <span class="arr">→</span>
  <div class="cfi"><div class="cfn">下游应用</div><div class="cfd">描述</div></div>
</div>
```

- 本行业环节用墨金顶线 + 墨金文字高亮（`border-top-color:var(--gld)` + `color:var(--gld)`）
- 箭头用 `.arr`，报头红

### 折叠交互规范

```javascript
// Section折叠
document.querySelectorAll('.sh').forEach(function(h){
  h.addEventListener('click',function(){
    var t=this.querySelector('.toggle');
    var sb=this.nextElementSibling;
    t.classList.toggle('collapsed');
    sb.classList.toggle('hide');
  });
});
// Sub-section折叠
document.querySelectorAll('.sch').forEach(function(h){
  h.addEventListener('click',function(){
    var sb=this.nextElementSibling;
    sb.classList.toggle('hide');
  });
});
```

---

## 文件命名与存放

- **文件名**: `{行业名称}行业深度分析.html`
- **输出目录**: `D:\OneDrive\Codex\股票分析\Codex\reports\行业分析\`（相对于工作空间根目录）
- 若目录不存在，自动创建
- **⚠️ 唯一输出文件：只生成HTML文件，禁止在输出目录或任何位置生成图片(.png/.jpg/.svg)、Markdown(.md)、PDF、Word、JSON数据转存等其他格式文件**

### Step 3 — 交付报告（总结+链接，缺一不可）

1. 确保输出目录存在：`D:\OneDrive\Codex\股票分析\Codex\reports\行业分析\`（若不存在则创建）
2. 生成HTML文件写入 `reports/行业分析/` 目录
3. **在对话中输出报告总结内容**（必须，不可跳过）
4. **在对话中输出报告文件链接**（必须，不可跳过）

**⚠️ 输出顺序（严格遵守）：先输出对话总结，最后输出报告链接**

**⚠️ 对话总结和报告链接是强制必做步骤，缺一不可。禁止只输出总结不输出链接。**

```
① 对话总结（Markdown格式，放在最前面，必须输出）
   - 核心结论一句话
   - 首选标的/估值洼地/最大弹性 表格
   - 关键风险提示
② 报告链接（放在对话总结之后，必须输出）
   📄 [{行业名称}行业深度分析.html](file:///...)
```

**⚠️ 禁止事项：**
- 禁止使用 `powershell Start-Process` 自动打开外部浏览器
- 禁止使用 `Bash start` 命令打开外部浏览器
- 禁止使用 `mcp__plugin_playwright` 打开报告
- 禁止把链接放在代码块(```)内 — 必须是纯Markdown才能点击
- 禁止输出原始中文路径链接或绝对路径文本兜底
- 禁止先放报告链接再放总结 — 必须总结在前、链接在后
- **禁止跳过对话总结** — 报告生成后必须在对话中输出总结内容
- **禁止跳过报告链接** — 报告生成后必须在对话中输出可点击的文件链接

---

## 报告清理

- 产物文件超过7天自动删除（以文件修改时间为准）
- 对话记录和记忆文件不删除
- 每轮对话结束时执行一次清理

---

## 质量检查清单

生成报告前逐项确认：
- [ ] 报头：`.np-mast` 居中，上单线+下双线，含英文刊头/雅黑大字标题/分隔点信息行
- [ ] 正文：包在 `.g` 里，**单栏顺序铺满**，无左右两栏、无中缝竖线、无 `fw`
- [ ] 行业概览：8个KV数据卡 + 三大催化表 + 产业链结构图
- [ ] 竞争格局：全球格局表 + 国内梯队分化表（含首选/核心/弹性标签）
- [ ] 核心标的深度：每个标的8个KV指标 + 文字分析 + 风险提示
- [ ] 客户订单信息：标的/客户/产品/状态/来源，区分🟢实锤/⚠️传闻
- [ ] 同行对比：多维度财务+估值+客户对比表
- [ ] 投资逻辑：配置建议(4行) + 弹性排序表 + 板块轮动表
- [ ] 风险提示：6-8条具体风险，用`.lb.warn`面板
- [ ] 核心结论：一句话总结 + 4-6个KV数据卡 + 来源标注
- [ ] 红涨绿跌颜色语义正确
- [ ] 墨金 `--gld` 用于首选/高优先级，报头红 `--a` 只用于刊头与栏目竖条
- [ ] 纸面为 `#f5f1e8`，正文为微软雅黑栈，正文字号 ≥13.5px，最小辅助文字 ≥10.5px，未加载任何外部字体
- [ ] 来源标注完整
- [ ] Footer免责声明
- [ ] 折叠交互正常

---

## 常见错误与修正

| 错误现象 | 原因 | 正确做法 |
|---------|------|---------|
| **Skill卡住不动** | 使用了后台并行子Agent | **禁止使用后台Agent，主线程顺序执行** |
| **Agent调度失败** | 自定义subagent_type未注册 | 不使用subagent_type，主Agent自己完成 |
| **数据采集耗时>3分钟** | wencai_nlp拆分多次调用同一批标的 | 一次查询合并所有指标（年报+Q1+增速+涨幅），总Bash调用≤3次 |
| 客户订单全标🟢 | 未区分数据来源 | 公告/年报→🟢，雪球/自媒体→⚠️ |
| 市场规模等数字无来源 | 凭空编造 | 必须标注来源，无法验证标[UNSOURCED] |
| 涨幅>80%仍推荐 | 未查涨幅风险 | 标注"涨幅透支风险" |
| 风险提示太笼统 | 只写"市场风险" | 必须具体：估值/技术/竞争/地缘/周期 |
| WebSearch不可用后卡住 | 等待超时 | 跳过WebSearch，用thsdk数据继续 |
| 用深色/黑底背景 | 违反报刊风格 | 严格使用 `--paper:#f5f1e8` 纸面体系 |
| 中文小字发虚发糊 | 用了宋体/衬线字体回退到 SimSun | 正文强制微软雅黑栈，字号 ≥13.5px，辅助文字 ≥10.5px |
| 又拆成左右两栏 | 沿用上一版的 `.fw` 分栏写法 | 正文固定单栏，`.sec` 一律不带分栏类 |
| 还在用 `.fw` | 未清理旧类名 | 删除所有 `fw`，宽表整幅铺开即可 |
| 用了旧的 `--ay/--ab/--ac/--ao` 变量 | 沿用上一版配色命名 | 统一改用 `--gld/--inf/--cyn/--wrn` |
| 通过 CDN 加载 Noto Serif SC | 违反字体规范 | 只用本地字体栈，不加载外部字体 |

---

## thsdk 调用参考

### 核心原则：一次查询拿齐，不要拆分

`wencai_nlp` 支持在一次查询中同时获取多个标的的多个指标。每次调用都要建立THS连接，拆分调用是最大的性能浪费。

### 高效查询模板（一次调用获取全部数据）

```python
from thsdk import THS
import pandas as pd

with THS() as ths:
    # 一次性获取所有标的的全部财务指标
    # 将年报+Q1+增速+涨幅合并在一次查询中
    stocks = '金宏气体或华特气体或广钢气体或侨源股份或和远气体或杭氧股份或凯美特气或九丰能源'
    query = (
        f'{stocks}，'
        f'市盈率，总市值，'
        f'2025年营业收入，2025年归属于母公司所有者的净利润，2025年销售毛利率，2025年净资产收益率ROE，'
        f'2026年一季度营业收入，2026年一季度归属于母公司所有者的净利润，2026年一季度销售毛利率，'
        f'2025年归属母公司股东的净利润同比增长率，2025年营业收入同比增长率，'
        f'2026年一季度归属母公司股东的净利润同比增长率，'
        f'年初至今涨跌幅，'
        f'非ST'
    )
    resp = ths.wencai_nlp(query)
    df = resp.df
```

### wencai_nlp 返回列名规律

- `股票代码` / `股票简称` — 基础标识
- `市盈率(pe)[YYYYMMDD]` — PE估值
- `总市值[YYYYMMDD]` — 总市值（元，需/1e8转亿）
- `销售毛利率[YYYYMMDD]` — 毛利率%
- `归属母公司股东的净利润(同比增长率)[YYYYMMDD]` — 净利润增速
- `营业收入[YYYYMMDD]` — 营收（元）
- `归属于母公司所有者的净利润[YYYYMMDD]` — 净利润（元）
- `净资产收益率roe(加权,公布值)[YYYYMMDD]` — ROE%
- `区间涨跌幅:前复权[YYYYMMDD-YYYYMMDD]` — 区间涨跌幅

### ❌ 反模式（禁止）

```python
# ❌ 错误：拆分多次调用获取同一批标的的不同指标
resp1 = ths.wencai_nlp('金宏气体或华特气体，市盈率，总市值')  # 第1次
resp2 = ths.wencai_nlp('金宏气体或华特气体，2025年营业收入')   # 第2次 - 重复！
resp3 = ths.wencai_nlp('金宏气体或华特气体，年初至今涨跌幅')   # 第3次 - 重复！
resp4 = ths.wencai_nlp('金宏气体或华特气体，2025年ROE')        # 第4次 - 重复！
```

```python
# ✅ 正确：一次调用获取同一批标的的全部指标
resp = ths.wencai_nlp('金宏气体或华特气体，市盈率，总市值，2025年营业收入，2025年销售毛利率，2025年净资产收益率ROE，年初至今涨跌幅，非ST')
```

---

## 固定HTML模板

> ⚠️ 以下模板为标准结构，调用skill时按对应占位符填充数据，不要自行增删章节。

### 模板使用规则

1. **CSS样式固定**：直接复制模板CSS，不得修改颜色/字体/padding
2. **章节结构固定**：8个章节顺序固定
3. **表格列数固定**：各章节表格列数按规范执行
4. **只替换数据**：将模板中的占位符替换为实际数据

### 完整HTML模板

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>{行业名称}行业深度分析</title>
<style>
:root{
--paper:#f5f1e8;--ink:#1b1915;
--bg:#f5f1e8;--bg2:#fffdf8;--bg3:#f1ece1;--bg4:#e6dfd0;
--bd:rgba(27,25,21,.16);--bd2:rgba(27,25,21,.34);
--t1:#1b1915;--t2:#45413a;--t3:#7c7566;
--up:#b3261e;--dn:#1c6b46;--inf:#1f4e79;--cyn:#155e63;--gld:#8a6a12;--wrn:#9a5b00;--a:#8c1c13;
--sans:'Microsoft YaHei UI','Microsoft YaHei','PingFang SC','HarmonyOS Sans SC','Hiragino Sans GB','Segoe UI',system-ui,-apple-system,sans-serif;
--serif:var(--sans);--display:var(--sans);--mono:var(--sans);
}
*{margin:0;padding:0;box-sizing:border-box}
body{background:var(--paper);color:var(--ink);font-family:var(--sans);line-height:1.8;font-size:13.5px;min-height:100vh;font-variant-numeric:lining-nums tabular-nums;-webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility}
body::after{content:'';position:fixed;inset:0;background-image:repeating-linear-gradient(0deg,rgba(27,25,21,.022) 0 1px,transparent 1px 4px);pointer-events:none;z-index:0}
.c{max-width:1280px;margin:0 auto;padding:20px 24px 40px;position:relative;z-index:1}
::-webkit-scrollbar{width:6px}::-webkit-scrollbar-thumb{background:var(--bd2);border-radius:2px}
.np-mast{margin:4px 0 20px;padding:14px 0 11px;border-top:1px solid var(--ink);border-bottom:3px double var(--ink);text-align:center}
.np-mast-kicker{font-family:var(--sans);font-size:11px;font-weight:700;letter-spacing:.3em;text-transform:uppercase;color:var(--a);margin-bottom:6px}
.np-mast-title{font-family:var(--display);font-size:44px;line-height:1.12;font-weight:900;letter-spacing:.2em;color:var(--ink);text-indent:.2em}
.np-mast-sub{display:flex;justify-content:center;align-items:center;gap:10px;flex-wrap:wrap;margin-top:8px;font-size:11.5px;color:var(--t2);letter-spacing:.06em}
.np-mast-sub .sep{color:var(--bd2)}
.np-mast-sub b{font-weight:700;color:var(--ink)}
.g{display:grid;grid-template-columns:minmax(0,1fr);gap:18px;position:relative;align-items:start}
.sec{background:var(--bg2);border:1px solid var(--bd);border-top:2px solid var(--ink);overflow:hidden}
.sh{display:flex;align-items:center;gap:8px;padding:11px 16px 10px;border-bottom:1px solid var(--ink);cursor:pointer}
.sh .icon{font-size:12px;color:var(--a)}
.sh h2{font-family:var(--display);font-size:15.5px;font-weight:700;color:var(--ink);letter-spacing:.03em}
.sh .toggle{font-size:11px;color:var(--t3);margin-left:auto;transition:.2s}
.sh .toggle.collapsed{transform:rotate(-90deg)}
.sb{padding:14px 16px;transition:max-height .3s ease;overflow:hidden}
.sb.hide{max-height:0;opacity:0;margin:0;padding:0}
.sc{margin:0 0 18px}
.sc:last-child{margin-bottom:0}
.sch{display:flex;align-items:center;gap:8px;padding:8px 12px;background:var(--bg3);border-left:3px solid var(--a);margin-bottom:12px;cursor:pointer}
.sch h3{font-family:var(--display);font-size:13.5px;font-weight:700;color:var(--ink);letter-spacing:.02em}
.sch .tag{font-size:10.5px;font-weight:700;padding:2px 8px;border:1px solid var(--bd2);color:var(--t2);letter-spacing:.04em}
.sch .ht{font-size:11px;font-weight:700;color:var(--a);margin-right:4px}
.scb{transition:max-height .3s ease;overflow:hidden}
.scb.hide{max-height:0;opacity:0;margin:0;padding:0}
.kv{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin-bottom:16px}
.kvi{background:var(--bg3);border:1px solid var(--bd);border-top:2px solid var(--ink);padding:12px 14px}
.kvi .kvk{font-size:11px;color:var(--t3);margin-bottom:4px;letter-spacing:.08em}
.kvi .kvv{font-family:var(--display);font-size:21px;font-weight:700;color:var(--ink);line-height:1.2}
.kvi .kvv.up{color:var(--up)}
.kvi .kvv.dn{color:var(--dn)}
.kvi .kvv.gold{color:var(--gld)}
.kvi .kvsub{font-size:11px;color:var(--t3);margin-top:4px;line-height:1.55}
.dt{width:100%;border-collapse:collapse;font-size:12.5px;margin-bottom:16px}
.dt th{padding:8px 10px;text-align:left;font-weight:700;color:var(--t3);font-size:11px;letter-spacing:.08em;border-bottom:1px solid var(--ink);white-space:nowrap}
.dt td{padding:7px 10px;border-bottom:1px solid rgba(27,25,21,.10);color:var(--t2);line-height:1.5}
.dt tbody tr:hover{background:rgba(140,28,19,.045)}
.dt .up{color:var(--up);font-weight:600}
.dt .dn{color:var(--dn)}
.dt .gold{color:var(--gld);font-weight:700}
.st{display:inline-block;font-size:10.5px;font-weight:700;padding:1px 6px;border:1px solid currentColor;margin-right:4px;letter-spacing:.02em}
.st.gold{color:var(--gld)}
.st.mb2{color:var(--inf)}
.st.cy{color:var(--cyn)}
.st.kc{color:var(--wrn)}
.tag2{display:inline-block;font-size:10.5px;font-weight:700;padding:1px 5px;border:1px solid currentColor;margin-left:4px;white-space:nowrap;letter-spacing:.02em}
.tag2.zb{color:var(--up)}
.tag2.yq{color:var(--gld)}
.vp{display:inline-block;font-size:10.5px;font-weight:600;padding:2px 8px;border:1px solid currentColor}
.vp.lo{color:var(--up)}
.vp.mid{color:var(--wrn)}
.vp.hi{color:var(--dn)}
.lb{border:1px solid var(--bd);border-left:3px solid var(--inf);background:rgba(31,78,121,.05);padding:14px 18px;margin-bottom:16px}
.lb.gold{border-left-color:var(--a);background:rgba(140,28,19,.05)}
.lb.warn{border-left-color:var(--dn);background:rgba(28,107,70,.05)}
.lb .li{font-size:12.5px;color:var(--t2);padding:4px 0;display:flex;align-items:flex-start;gap:8px;line-height:1.7}
.lb .li::before{content:'—';color:var(--inf);font-weight:700;flex-shrink:0}
.lb.gold .li::before{color:var(--a)}
.lb.warn .li::before{color:var(--dn)}
.icc{margin-bottom:20px}
.cf{display:flex;align-items:stretch;justify-content:center;flex-wrap:wrap;gap:8px;margin-bottom:12px}
.cfi{background:var(--bg3);border:1px solid var(--bd);border-top:2px solid var(--ink);padding:12px 16px;text-align:center;min-width:130px;flex:1 1 130px}
.cfi .cfn{font-family:var(--display);font-size:13px;font-weight:700;color:var(--ink);margin-bottom:4px}
.cfi .cfd{font-size:11px;color:var(--t3);line-height:1.55}
.cf .arr{font-size:16px;color:var(--a);align-self:center}
.src{font-size:11px;color:var(--t3);margin:8px 0 16px;line-height:1.65}
.ft{text-align:center;padding:28px 0 12px;font-size:11.5px;color:var(--t3);border-top:1px solid var(--ink);margin-top:24px;line-height:2;letter-spacing:.06em}
.ft span{color:var(--a);font-weight:700}
@media(max-width:960px){
.c{padding:14px}
.np-mast-title{font-size:29px;letter-spacing:.14em;text-indent:.14em}
.np-mast-kicker{font-size:9.5px;letter-spacing:.22em}
.g{gap:14px}
.kv{grid-template-columns:repeat(2,minmax(0,1fr))}
.sch{flex-wrap:wrap}.cfi{min-width:110px}
.sh h2{font-size:14.5px}
}
@media(prefers-reduced-motion:reduce){*,*::before,*::after{animation-duration:.01ms!important;transition-duration:.01ms!important}}
</style>
</head>
<body>
<div class="c">

<!-- 报头 -->
<div class="np-mast">
<div class="np-mast-kicker">{行业英文名} INDUSTRY</div>
<div class="np-mast-title">{行业名称}行业深度分析</div>
<div class="np-mast-sub">
<span>{日期}</span><span class="sep">|</span>
<span>数据日 {数据日期}</span><span class="sep">|</span>
<span>覆盖标的 <b>{覆盖标的数}</b></span><span class="sep">|</span>
<span>{技术关键词}</span>
</div>
</div>

<!-- 正文：单栏，8章顺序铺满 -->
<div class="g">

<!-- Section 1: 行业概览 -->
<div class="sec">
<div class="sh" onclick="this.querySelector('.toggle').classList.toggle('collapsed');this.nextElementSibling.classList.toggle('hide')">
<span class="icon">📊</span><h2>一、行业概览</h2><span class="toggle">▼</span>
</div>
<div class="sb">

<div class="kv">
<div class="kvi"><div class="kvk">{指标1标签}</div><div class="kvv up">{指标1值}</div><div class="kvsub">{来源 · 同比 · 预测}</div></div>
<div class="kvi"><div class="kvk">{指标2标签}</div><div class="kvv up">{指标2值}</div><div class="kvsub">{来源 · 说明}</div></div>
<div class="kvi"><div class="kvk">{指标3标签}</div><div class="kvv up">{指标3值}</div><div class="kvsub">{来源 · 说明}</div></div>
<div class="kvi"><div class="kvk">{指标4标签}</div><div class="kvv up">{指标4值}</div><div class="kvsub">{来源 · 说明}</div></div>
<div class="kvi"><div class="kvk">{指标5标签}</div><div class="kvv dn">{指标5值}</div><div class="kvsub">{来源 · 说明}</div></div>
<div class="kvi"><div class="kvk">{指标6标签}</div><div class="kvv dn">{指标6值}</div><div class="kvsub">{来源 · 说明}</div></div>
<div class="kvi"><div class="kvk">{指标7标签}</div><div class="kvv">{指标7值}</div><div class="kvsub">{来源 · 说明}</div></div>
<div class="kvi"><div class="kvk">{指标8标签}</div><div class="kvv">{指标8值}</div><div class="kvsub">{来源 · 说明}</div></div>
</div>

<div class="sc">
<div class="sch"><span class="ht">#</span><h3>三大催化 — 为什么是现在？</h3><span class="tag">{催化1} | {催化2} | {催化3}</span></div>
<div class="scb">
<table class="dt">
<thead><tr><th style="width:15%">催化</th><th style="width:45%">驱动逻辑</th><th style="width:40%">关键数据</th></tr></thead>
<tbody>
<tr><td class="gold">{催化1}</td><td>{驱动逻辑1}</td><td>{关键数据1}</td></tr>
<tr><td class="gold">{催化2}</td><td>{驱动逻辑2}</td><td>{关键数据2}</td></tr>
<tr><td class="gold">{催化3}</td><td>{驱动逻辑3}</td><td>{关键数据3}</td></tr>
</tbody>
</table>
</div>
</div>

<!-- 产业链结构图 -->
<div class="icc">
<div class="cf">
<div class="cfi"><div class="cfn">{上游环节1}</div><div class="cfd">{描述}</div></div>
<span class="arr">→</span>
<div class="cfi" style="border-top-color:var(--gld)"><div class="cfn" style="color:var(--gld)">{本行业}</div><div class="cfd">{描述}</div></div>
<span class="arr">→</span>
<div class="cfi"><div class="cfn">{中游环节}</div><div class="cfd">{描述}</div></div>
<span class="arr">→</span>
<div class="cfi"><div class="cfn">{耗材环节}</div><div class="cfd">{描述}</div></div>
<span class="arr">→</span>
<div class="cfi"><div class="cfn">{下游应用}</div><div class="cfd">{描述}</div></div>
</div>
</div>

</div>
</div>

<!-- Section 2: 竞争格局 -->
<div class="sec">
<div class="sh" onclick="this.querySelector('.toggle').classList.toggle('collapsed');this.nextElementSibling.classList.toggle('hide')">
<span class="icon">⚔️</span><h2>二、竞争格局</h2><span class="toggle">▼</span>
</div>
<div class="sb">

<div class="sc">
<div class="sch"><span class="ht">#</span><h3>全球格局：{格局描述}</h3><span class="tag">{海外龙头1} | {海外龙头2}</span></div>
<div class="scb">
<table class="dt">
<thead><tr><th>维度</th><th>{海外龙头1}</th><th>{海外龙头2}</th></tr></thead>
<tbody>
<tr><td class="gold">国家</td><td>{国家1}</td><td>{国家2}</td></tr>
<tr><td>全球份额</td><td class="up">{份额1}</td><td class="up">{份额2}</td></tr>
<tr><td>核心平台</td><td>{平台1}</td><td>{平台2}</td></tr>
<tr><td>2025营收</td><td class="up">{营收1}</td><td class="up">{营收2}</td></tr>
<tr><td>TTM PE</td><td>{PE1}</td><td>{PE2}</td></tr>
<tr><td>核心客户</td><td>{客户1}</td><td>{客户2}</td></tr>
<tr><td>中国份额</td><td>{中国份额1}</td><td>{中国份额2}</td></tr>
</tbody>
</table>
</div>
</div>

<div class="sc">
<div class="sch"><span class="ht">#</span><h3>国内竞争：三梯队分化</h3><span class="tag">{梯队1关键词} | {梯队2关键词} | {梯队3关键词}</span></div>
<div class="scb">
<table class="dt">
<thead><tr><th>梯队</th><th>公司</th><th>卡位</th><th>国产化率</th><th>竞争壁垒</th></tr></thead>
<tbody>
<tr><td rowspan="2" style="color:var(--gld);font-weight:700">第一梯队</td>
<td><span class="st gold">首选</span>{公司1}({代码1})</td><td>{卡位1}</td><td>{国产化率1}</td><td>{壁垒1}</td></tr>
<tr><td>{公司2}({代码2})</td><td>{卡位2}</td><td>{国产化率2}</td><td>{壁垒2}</td></tr>
<tr><td rowspan="2" style="color:var(--cyn)">第二梯队</td>
<td><span class="st mb2">核心</span>{公司3}({代码3})</td><td>{卡位3}</td><td>{国产化率3}</td><td>{壁垒3}</td></tr>
<tr><td>{公司4}({代码4})</td><td>{卡位4}</td><td>{国产化率4}</td><td>{壁垒4}</td></tr>
<tr><td rowspan="3" style="color:var(--t2)">第三梯队/配套</td>
<td>{公司5}({代码5})</td><td>{卡位5}</td><td>{国产化率5}</td><td>{壁垒5}</td></tr>
<tr><td>{公司6}({代码6})</td><td>{卡位6}</td><td>{国产化率6}</td><td>{壁垒6}</td></tr>
<tr><td>{公司7}({代码7})</td><td>{卡位7}</td><td>{国产化率7}</td><td>{壁垒7}</td></tr>
</tbody>
</table>
</div>
</div>

</div>
</div>

<!-- Section 3: 核心标的深度 -->
<div class="sec">
<div class="sh" onclick="this.querySelector('.toggle').classList.toggle('collapsed');this.nextElementSibling.classList.toggle('hide')">
<span class="icon">🎯</span><h2>三、核心标的深度</h2><span class="toggle">▼</span>
</div>
<div class="sb">

<!-- 标的1 -->
<div class="sc">
<div class="sch"><span class="ht">#</span><h3>{标的1名称}({标的1代码})</h3><span class="tag">{定位标签}</span><span class="tag2 zb">高增</span></div>
<div class="scb">
<div class="kv">
<div class="kvi"><div class="kvk">市值/股价</div><div class="kvv">{市值}亿 / {股价}</div></div>
<div class="kvi"><div class="kvk">PE TTM</div><div class="kvv">{PE}</div></div>
<div class="kvi"><div class="kvk">2025营收/净利</div><div class="kvv up">{营收}亿 / {净利}亿</div></div>
<div class="kvi"><div class="kvk">毛利率(Q1)</div><div class="kvv up">{毛利率}%</div></div>
<div class="kvi"><div class="kvk">ROE</div><div class="kvv">{ROE}%</div></div>
<div class="kvi"><div class="kvk">H1净利预增</div><div class="kvv up">{预增}</div></div>
<div class="kvi"><div class="kvk">2026Q1营收/净利</div><div class="kvv up">{Q1营收}亿 / {Q1净利}亿</div></div>
<div class="kvi"><div class="kvk">年内涨幅</div><div class="kvv up">{涨幅}%</div></div>
</div>
<p style="color:var(--t2);font-size:12px;margin-bottom:12px">{核心逻辑描述}<span style="color:var(--wrn);font-weight:700">风险提示：{风险}</span></p>
</div>
</div>

<!-- 标的2 -->
<div class="sc">
<div class="sch"><span class="ht">#</span><h3>{标的2名称}({标的2代码})</h3><span class="tag">{定位标签}</span><span class="tag2 zb">高增</span></div>
<div class="scb">
<div class="kv">
<div class="kvi"><div class="kvk">市值/股价</div><div class="kvv">{市值}亿 / {股价}</div></div>
<div class="kvi"><div class="kvk">PE TTM</div><div class="kvv">{PE}</div></div>
<div class="kvi"><div class="kvk">2025营收/净利</div><div class="kvv up">{营收}亿 / {净利}亿</div></div>
<div class="kvi"><div class="kvk">毛利率(Q1)</div><div class="kvv up" style="color:var(--gld)">{毛利率}%</div></div>
<div class="kvi"><div class="kvk">净利率(Q1)</div><div class="kvv">{净利率}%</div></div>
<div class="kvi"><div class="kvk">{关键指标6}</div><div class="kvv up">{值}</div></div>
<div class="kvi"><div class="kvk">2026E净利</div><div class="kvv up">{预估}</div></div>
<div class="kvi"><div class="kvk">2025净利增速</div><div class="kvv up">+{增速}%</div></div>
</div>
<p style="color:var(--t2);font-size:12px;margin-bottom:12px">{核心逻辑描述}<span style="color:var(--cyn)">{估值优势}</span></p>
</div>
</div>

<!-- 标的3 -->
<div class="sc">
<div class="sch"><span class="ht">#</span><h3>{标的3名称}({标的3代码})</h3><span class="tag">{定位标签}</span><span class="tag2 zb">高增</span></div>
<div class="scb">
<div class="kv">
<div class="kvi"><div class="kvk">市值/股价</div><div class="kvv">{市值}亿 / {股价}</div></div>
<div class="kvi"><div class="kvk">PE TTM</div><div class="kvv dn">{PE}</div></div>
<div class="kvi"><div class="kvk">2025营收</div><div class="kvv up">{营收}亿(+{增速}%)</div></div>
<div class="kvi"><div class="kvk">毛利率(Q1)</div><div class="kvv">{毛利率}%</div></div>
<div class="kvi"><div class="kvk">Q1营收增速</div><div class="kvv up">+{增速}%</div></div>
<div class="kvi"><div class="kvk">营收结构</div><div class="kvv">{结构}</div></div>
<div class="kvi"><div class="kvk">2026E净利</div><div class="kvv up">{预估}</div></div>
<div class="kvi"><div class="kvk">关键突破</div><div class="kvv up">{突破}</div></div>
</div>
<p style="color:var(--t2);font-size:12px;margin-bottom:12px">{核心逻辑描述}<span style="color:var(--wrn);font-weight:700">风险提示：{风险}</span></p>
</div>
</div>

<!-- 配套标的表 -->
<div class="sc">
<div class="sch"><span class="ht">#</span><h3>配套标的：{配套类别}</h3><span class="tag">{标的1} | {标的2} | {标的3}</span></div>
<div class="scb">
<table class="dt">
<thead><tr><th>标的</th><th>卡位</th><th>核心数据</th><th>看点</th></tr></thead>
<tbody>
<tr><td>{标的}({代码})</td><td>{卡位}</td><td>市值{市值}亿/PE {PE}x/股价{股价}</td><td>{看点}</td></tr>
<tr><td>{标的}({代码})</td><td>{卡位}</td><td>市值{市值}亿/PE {PE}x/股价{股价}</td><td>{看点}</td></tr>
<tr><td>{标的}({代码})</td><td>{卡位}</td><td>市值{市值}亿/PE {PE}x/Q1营收{营收}亿+{增速}%</td><td>{看点}</td></tr>
<tr><td>{标的}({代码})</td><td>{卡位}</td><td>市值{市值}亿/股价{股价}/毛利率{毛利率}%</td><td>{看点}</td></tr>
<tr><td>{标的}({代码})</td><td>{卡位}</td><td>市值{市值}亿/股价{股价}/毛利率{毛利率}%</td><td>{看点}</td></tr>
<tr><td>{标的}({代码})</td><td>{卡位}</td><td>{关键数据}</td><td>{看点}</td></tr>
</tbody>
</table>
</div>
</div>

</div>
</div>

<!-- Section 4: 客户订单信息 -->
<div class="sec">
<div class="sh" onclick="this.querySelector('.toggle').classList.toggle('collapsed');this.nextElementSibling.classList.toggle('hide')">
<span class="icon">📋</span><h2>四、客户订单信息</h2><span class="toggle">▼</span>
</div>
<div class="sb">

<table class="dt">
<thead><tr><th>标的</th><th>客户名称</th><th>产品/服务</th><th>状态</th><th>来源</th></tr></thead>
<tbody>
<tr><td rowspan="3">{标的1}</td><td>{客户1}</td><td>{产品1}</td><td><span class="up">🟢 实锤</span></td><td>{来源1}</td></tr>
<tr><td>{客户2}</td><td>{产品2}</td><td><span class="up">🟢 实锤</span></td><td>{来源2}</td></tr>
<tr><td>{客户3}</td><td>{产品3}</td><td><span class="up">🟢 实锤</span></td><td>{来源3}</td></tr>
<tr><td rowspan="2">{标的2}</td><td>{客户4}</td><td>{产品4}</td><td><span class="up">🟢 实锤</span></td><td>{来源4}</td></tr>
<tr><td>{客户5}</td><td>{产品5}</td><td><span class="up">🟢 实锤</span></td><td>{来源5}</td></tr>
<tr><td rowspan="2">{标的3}</td><td>{客户6}</td><td>{产品6}</td><td><span class="up">🟢 实锤</span></td><td>{来源6}</td></tr>
<tr><td>{客户7}</td><td>{产品7}</td><td><span class="up">🟢 实锤</span></td><td>{来源7}</td></tr>
<tr><td>{标的4}</td><td>{客户8}</td><td>{产品8}</td><td><span class="up">🟢 实锤</span></td><td>{来源8}</td></tr>
<tr><td>{标的5}</td><td>{客户9}</td><td>{产品9}</td><td><span class="up">🟢 实锤</span></td><td>{来源9}</td></tr>
<tr><td>{标的6}</td><td>{客户10}</td><td>{产品10}</td><td><span class="up">🟢 实锤</span></td><td>{来源10}</td></tr>
</tbody>
</table>
<div class="src">来源：公司年报/季报/投资者调研/互动平台。🟢实锤 = 公司公开披露；⚠️传闻 = 第三方推测</div>

</div>
</div>

<!-- Section 5: 同行对比 -->
<div class="sec">
<div class="sh" onclick="this.querySelector('.toggle').classList.toggle('collapsed');this.nextElementSibling.classList.toggle('hide')">
<span class="icon">📈</span><h2>五、同行核心指标对比</h2><span class="toggle">▼</span>
</div>
<div class="sb">

<table class="dt">
<thead><tr><th>标的</th><th>板块</th><th>2025营收(亿)</th><th>2025净利(亿)</th><th>毛利率</th><th>ROE</th><th>PE TTM</th><th>市值(亿)</th><th>中报预期</th><th>核心客户</th><th>国产化壁垒</th></tr></thead>
<tbody>
<tr>
<td><span class="st gold">CT</span>{标的1}</td><td>{板块1}</td><td class="up">{营收1}</td><td class="up">{净利1}</td><td class="up">{毛利率1}%</td><td>{ROE1}%</td><td class="dn">{PE1}x</td><td>{市值1}</td><td><span class="tag2 zb">高增</span></td><td>{客户1}</td><td class="gold">{壁垒1}</td></tr>
<tr>
<td>{标的2}</td><td>{板块2}</td><td class="up">{营收2}</td><td class="up">{净利2}</td><td class="up" style="color:var(--gld)">{毛利率2}%</td><td>{ROE2}%</td><td>{PE2}x</td><td>{市值2}</td><td><span class="tag2 zb">高增</span></td><td>{客户2}</td><td class="up">{壁垒2}</td></tr>
<tr>
<td>{标的3}</td><td>{板块3}</td><td class="up">{营收3}</td><td>{净利3}</td><td>{毛利率3}%</td><td>{ROE3}%</td><td class="dn">{PE3}x</td><td>{市值3}</td><td><span class="tag2 zb">高增</span></td><td>{客户3}</td><td class="up">{壁垒3}</td></tr>
<tr>
<td>{标的4}</td><td style="color:var(--gld)">{板块4}</td><td>{营收4}</td><td>{净利4}</td><td>{毛利率4}%</td><td>—</td><td>{PE4}x</td><td>{市值4}</td><td><span class="tag2 yq">改善</span></td><td>{客户4}</td><td>{壁垒4}</td></tr>
<tr>
<td>{标的5}</td><td>{板块5}</td><td class="up">{营收5}</td><td class="up">{净利5}</td><td>~{毛利率5}%</td><td>—</td><td>{PE5}x</td><td>{市值5}</td><td><span class="tag2 yq">改善</span></td><td>{客户5}</td><td>{壁垒5}</td></tr>
<tr>
<td>{标的6}</td><td>{板块6}</td><td>—</td><td>—</td><td>—</td><td>—</td><td class="dn">{PE6}x</td><td>{市值6}</td><td>—</td><td>{客户6}</td><td class="up">{壁垒6}</td></tr>
<tr>
<td>{标的7}</td><td>{板块7}</td><td>—</td><td>—</td><td>—</td><td>—</td><td class="dn">{PE7}x</td><td>{市值7}</td><td>—</td><td>{客户7}</td><td>{壁垒7}</td></tr>
</tbody>
</table>
<div class="src">来源：公司年报/季报/东方财富。数据截至{日期}收盘。毛利率/ROE取最新季报或年报数据。PE=TTM。</div>

</div>
</div>

<!-- Section 6: 投资逻辑 -->
<div class="sec">
<div class="sh" onclick="this.querySelector('.toggle').classList.toggle('collapsed');this.nextElementSibling.classList.toggle('hide')">
<span class="icon">💡</span><h2>六、投资逻辑与配置建议</h2><span class="toggle">▼</span>
</div>
<div class="sb">

<div class="lb gold">
<div class="li">主板首选：{标的4} — {主板逻辑4}，{关键数据4}（主板标的优先推荐）</div>
<div class="li">首选：{标的1} — {核心逻辑1}，{关键数据1}</div>
<div class="li">估值安全：{标的2} — {估值逻辑2}，{关键数据2}</div>
<div class="li">高弹性：{标的3} — {弹性逻辑3}，但{风险提示3}</div>
</div>

<div class="sc">
<div class="sch"><span class="ht">#</span><h3>弹性排序（按国产替代弹性）</h3><span class="tag">{赛道1} > {赛道2} > {赛道3} > {赛道4}</span></div>
<div class="scb">
<table class="dt">
<thead><tr><th>细分赛道</th><th>国产化率</th><th>替代空间</th><th>核心标的</th><th>弹性</th></tr></thead>
<tbody>
<tr><td>{赛道1}</td><td class="dn">~{率1}%</td><td class="up">{空间1}</td><td>{标的1}</td><td class="gold">★★★★★</td></tr>
<tr><td>{赛道2}</td><td class="dn">~{率2}%</td><td class="up">{空间2}</td><td>{标的2}</td><td class="gold">★★★★★</td></tr>
<tr><td>{赛道3}</td><td class="dn">~{率3}%</td><td class="up">{空间3}</td><td>{标的3}</td><td>★★★★</td></tr>
<tr><td>{赛道4}</td><td>{率4}</td><td class="up">{空间4}</td><td>{标的4}</td><td>★★★★</td></tr>
<tr><td>{赛道5}</td><td class="up">~{率5}%</td><td>{空间5}</td><td>{标的5}</td><td>★★★</td></tr>
<tr><td>{赛道6}</td><td class="up">>{率6}%</td><td>{空间6}</td><td>{标的6}</td><td>★★</td></tr>
</tbody>
</table>
</div>
</div>

<div class="sc">
<div class="sch"><span class="ht">#</span><h3>板块轮动顺序（芯片周期）</h3><span class="tag">{阶段1}→{阶段2}→{阶段3}→{阶段4}</span></div>
<div class="scb">
<p style="color:var(--t2);font-size:12px;margin-bottom:8px">{周期描述}</p>
<table class="dt">
<thead><tr><th>阶段</th><th>受益顺序</th><th>代表标的</th><th>当前阶段</th></tr></thead>
<tbody>
<tr><td>1.{阶段1}</td><td>{受益1}</td><td>{标的1}</td><td>✅ 进行中</td></tr>
<tr><td>2.{阶段2}</td><td>{受益2}</td><td>{标的2}</td><td>✅ 进行中</td></tr>
<tr><td>3.{阶段3}</td><td>{受益3}</td><td>{标的3}</td><td>⏳ 即将到来</td></tr>
<tr><td>4.{阶段4}</td><td>{受益4}</td><td>{标的4}</td><td>⏳ 6-12月内</td></tr>
</tbody>
</table>
</div>
</div>

</div>
</div>

<!-- Section 7: 风险提示 -->
<div class="sec">
<div class="sh" onclick="this.querySelector('.toggle').classList.toggle('collapsed');this.nextElementSibling.classList.toggle('hide')">
<span class="icon">⚠️</span><h2>七、风险提示</h2><span class="toggle">▼</span>
</div>
<div class="sb">

<div class="lb warn">
<div class="li">板块估值高企风险：{具体描述}</div>
<div class="li">涨幅透支风险：{具体描述}</div>
<div class="li">技术迭代风险：{具体描述}</div>
<div class="li">客户验证周期风险：{具体描述}</div>
<div class="li">地缘政治风险：{具体描述}</div>
<div class="li">下游CAPEX周期风险：{具体描述}</div>
<div class="li">竞争加剧风险：{具体描述}</div>
</div>

</div>
</div>

<!-- Section 8: 核心结论 -->
<div class="sec">
<div class="sh" onclick="this.querySelector('.toggle').classList.toggle('collapsed');this.nextElementSibling.classList.toggle('hide')">
<span class="icon">🏁</span><h2>八、核心结论</h2><span class="toggle">▼</span>
</div>
<div class="sb">

<div class="lb gold">
<div class="li" style="font-size:14px;color:var(--a);font-weight:700">{一句话核心结论}</div>
</div>

<div class="kv">
<div class="kvi"><div class="kvk">行业评级</div><div class="kvv up">{评级}</div><div class="kvsub">{说明}</div></div>
<div class="kvi"><div class="kvk">主板首选</div><div class="kvv gold">{主板标的}</div><div class="kvsub">{说明}</div></div>
<div class="kvi"><div class="kvk">首选标的</div><div class="kvv gold">{标的}</div><div class="kvsub">{说明}</div></div>
<div class="kvi"><div class="kvk">估值洼地</div><div class="kvv up">{标的}</div><div class="kvsub">{说明}</div></div>
<div class="kvi"><div class="kvk">最大弹性</div><div class="kvv gold">{标的}</div><div class="kvsub">{说明}</div></div>
</div>

<div class="src">
⟨数据来源⟩ {来源列表}<br>
⟨免责声明⟩ 本报告仅供研究参考，不构成投资建议。股市有风险，投资需谨慎。数据截至{日期}，部分前瞻数据为机构预测。
</div>

</div>
</div>

<!-- Footer -->
</div><!-- /g 正文 -->

<div class="ft">
{行业名称}行业深度分析 · {日期} · WorkBuddy AI 生成<br>
本报告仅为产业链研究参考，不构成任何投资建议。投资有风险，入市需谨慎。
</div>

</div>

<script>
// Section collapse toggle
document.querySelectorAll('.sh').forEach(function(h){
h.addEventListener('click',function(){
var t=this.querySelector('.toggle');
var sb=this.nextElementSibling;
t.classList.toggle('collapsed');
sb.classList.toggle('hide');
});
});
// Sub-section collapse toggle
document.querySelectorAll('.sch').forEach(function(h){
h.addEventListener('click',function(){
var sb=this.nextElementSibling;
sb.classList.toggle('hide');
});
});
</script>
</body>
</html>
```

### 占位符说明

| 占位符 | 内容示例 |
|--------|---------|
| `{行业名称}` | 半导体测试机(ATE) |
| `{行业英文名}` | Semiconductor ATE（报头英文刊头，全大写） |
| `{日期}` | 2026-07-11 |
| `{数据日期}` | 2026-06-30（财务数据截止日，与行情日区分） |
| `{覆盖标的数}` | 15（本报告覆盖的标的数量） |
| `{技术关键词}` | AI · HBM · Chiplet |
| `{指标1-8标签}` | 全球ATE市场(2025) / 中国测试设备市场(2027E) 等 |
| `{催化1-3}` | AI芯片测试强度跃升 / 先进封装增量 / 国产替代突破 |
| `{板块}` | 创业板/科创板/主板 |
| `{中报预期}` | 高增/改善 |

---

## 更新日志

### v9.1.0 (2026-09-16)
- **字体换成微软雅黑 + 正文回到单栏**
  - **字体**：正文从宋体衬线栈改为微软雅黑无衬线栈（`Microsoft YaHei UI` / `Microsoft YaHei` / `PingFang SC` / `HarmonyOS Sans SC` / `Segoe UI`）。
    原因：Windows 上 `Noto Serif SC`、`Source Han Serif SC`、`Songti SC` 全都不存在，实际回退到 `SimSun`（宋体），10–13px 的中文小字号笔画过细、发虚发糊
  - **字号配套放大**（清晰度的一半来自字号）：正文 13px → 13.5px，`行高` 1.78 → 1.8；`.kvk` 10.5→11、`.kvsub` 10→11、`.dt th` 10.5→11、`.dt 正文字` 12→12.5、`.tag2` 9.5→10.5、`.st` 10→10.5、`.vp` 10→10.5、`.src` 10→11、`.cfi .cfd` 10→11、`.sch .tag` 10→10.5；正文禁用任何低于 10.5px 的文字
  - **去掉左右两栏，正文改为单栏**：`.g` 从两列网格改为 `minmax(0,1fr)` 单列，删除 `.g::before` 中缝竖线、删除 `.g .fw` 与全部 `fw` 类名；宽表（5列/11列）直接整幅铺开
  - 移除 `'Playfair Display'`（Windows 无此字体，会静默回退），报头英文刊头改用雅黑加粗 + `.3em` 字距
  - 新增 `text-rendering:optimizeLegibility`
  - 报头、纸面色板、语义色、8章结构、表格列数、折叠交互全部保持 v9.0 不变

### v9.0.0 (2026-09-16)
- **版面重构：暗黑主题 → 报刊风格（左右两栏），与 daily-briefing-pro 统一**
  - 纸面从 `#0e0e14` 深色改为 `#f5f1e8` 米白新闻纸，正文改用宋体衬线栈（Noto Serif SC / 思源宋体 / 宋体 / SimSun），仍不加载任何外部字体
  - 语义色整体更换：`--up #b3261e` 红涨 / `--dn #1c6b46` 绿跌 / `--gld #8a6a12` 墨金 / `--inf #1f4e79` 蓝 / `--cyn #155e63` 青 / `--wrn #9a5b00` 棕橙 / `--a #8c1c13` 报头红；旧变量 `--ar/--ag/--ay/--ab/--ao/--ac` 全部废弃
  - **`Hero` 区 → `.np-mast` 居中报头**：上单线 + 下双线，报头红英文刊头 + 44px 宋体大字标题 + 分隔点信息行（日期/数据日/覆盖标的数/技术关键词）
  - **正文新增 `.g` 左右两栏容器**，中缝一条竖细线（`.g::before`），`≤960px` 自动降为单栏
  - 新增 `.fw` 横跨两栏；**一、行业概览 / 四、客户订单 / 五、同行对比三章强制 `.fw`**（宽表与横排产业链图不适合窄栏）
  - 卡片从「圆角 + 玻璃拟态 + 彩色底」改为「直角 + 纸白面 + 顶部2px铅线」；徽标从色块改为描边铅字章
  - 表格从「蓝色表头 + 深色行」改为「宋体小字距表头 + 铅印细线 + 悬停泛红」
  - 折叠交互、8章结构、固定列数全部保持不变

### v8.0.0 (2026-07-11)
- **全面重构：基于三份实际报告(半导体测试机/半导体设备零部件/晶圆代工)统一风格**
  - 样式从"专业研报/财报风格(暖白+海军蓝)"切换为"暗黑主题(深蓝黑+红涨绿跌+金色强调)"
  - 移除所有外部字体依赖(Noto Serif SC/Noto Sans SC/JetBrains Mono)，改用系统字体栈
  - 色彩系统统一为6色暗黑变量：--ar红/--ag绿/--ay金/--ab蓝/--ao橙/--ac青
  - Hero区从海军蓝封面改为深色渐变+顶部彩虹线
  - 章节从module卡片改为sec可折叠结构
  - 新增子章节sc/sch/scb可折叠结构
  - KV数据卡从3列改为4列网格
  - 新增标的标签体系：首选(金)/核心(蓝)/弹性(青)/主板(橙)
  - 新增中报预期标签：高增(红)/改善(金)
  - 报告结构从8章(标题区/竞争格局/产业链/投资逻辑/估值分析/风险/结论/免责)改为8章(行业概览/竞争格局/核心标的深度/客户订单/同行对比/投资逻辑/风险提示/核心结论)
  - 恢复"行业概览"章节(含KV数据卡+三大催化+产业链结构图)
  - 新增"核心标的深度"章节(每个标的独立KV卡+文字分析)
  - 新增"客户订单信息"独立章节
  - 新增"同行核心指标对比"独立章节
  - 投资逻辑从11列紧凑表改为弹性排序表+板块轮动表+配置建议面板
  - 风险提示从4-5条扩展为6-8条
  - 核心结论从3个数据节点扩展为4-6个KV数据卡
  - 移除主板优先限制，科创板/创业板标的正常展示和推荐
  - 移除估值分析独立章节(机构预测PE/目标价)，相关数据整合到核心标的深度和同行对比中
  - 产业链结构图从pipeline竖排改为cf横排卡片+箭头
  - 折叠交互从无改为全部章节/子章节可折叠

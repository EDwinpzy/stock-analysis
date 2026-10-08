---
name: stock-market-board
description: '生成A股个股K线、分时、竞价与盘口数据的报刊风格行情看板HTML页面；用户提出看行情图时优先触发，深度分析报告则转入个股分析。'
metadata:
  original_name: 个股行情版面
---

# 个股行情版面

> 输入股票名称或代码，生成一份报刊风格（浅色新闻纸 + 金色装饰 + 红涨绿跌）的完整行情看板 HTML。
> 基于 thsdk 免费数据源，纯 Python 脚本流水线：拉数据 → 生成数据JS → 套模板出 HTML。

## 第0步：解析股票代码（用户只给名称时）

```python
with THS() as ths:
    resp = ths.search_symbols('贵州茅台')
    a = [r for r in resp.data if any(m in r.get('MarketDisplay','') for m in ['沪A','深A','北A'])]
    # 取 a[0]['THSCODE'][4:] 得6位代码，a[0]['Name'] 得名称
```

## 工作流（3 步顺序执行）

```bash
# 1. 拉取基础数据（约10秒）
python scripts/fetch_data.py <股票代码6位> <股票名称>

# 2. 拉取近一年250天分时+竞价段（约4分钟，后台跑）
python scripts/fetch_trends.py <股票代码6位>

# 3. 生成数据JS + 组装HTML（约10秒）
python scripts/build_page.py <股票代码6位> <股票名称> <所属行业>
```

输出在工作目录 `<代码>_<名称>/` 下：`行情版面.html` + `page_data.js`（HTML 需与 page_data.js 同目录打开）。

## 数据源（thsdk，游客模式可用）

| 数据 | 接口 | 说明 |
|------|------|------|
| 历史日K（前复权） | `klines(code, interval='day', adjust='forward')` | 上市至今全量 |
| 今日分时 | `intraday_data(code)` | 241 条分钟级，含累计量/额 |
| 今日集合竞价 | `call_auction(code)` | 9:15-9:25 秒级 |
| 历史集合竞价 | `tick_super_level1(code, date='YYYYMMDD')` | ⚠️ 见坑1 |
| 历史分时 | `min_snapshot(code, date='YYYYMMDD')` | 241 条分钟级 |
| 五档盘口 | `depth(code)` | 买卖各5档 |
| 关键数据 | `market_data_cn(code, '汇总')` + `market_data_cn(code, '扩展2')` | 涨停价/市值/量比等 |
| 行业 | `wencai_nlp('XX所属行业')` | 返回所属同花顺行业 |
| 实际换手率 | `wencai_nlp('XX实际换手率')` | 自由流通口径 |

## 页面功能（template.html 已实现）

- **报头一行**：名称+代码+行业标签 ｜ 大号现价+涨跌（报刊双线+金色短线装饰）
- **集合竞价条**：竞价价/量/涨跌幅；进入分时视图额外显示 早盘竞价金额/昨日成交额/自由流通市值
- **左侧图表**：日K/分时 Tab 切换（ECharts 5.5）
  - 日K：蜡烛+MA5/10/20+成交量，dataZoom 缩放，tooltip 含成交额
  - 分时：蓝价格线+黄均价线+昨收灰虚线，**Y轴固定跌停-涨停(±10%)**，竞价段橙色虚线曲线+9:20不可撤单线+竞价高亮区，竞价量能三区（上=未匹配净量、中=匹配累计量、下=盘中量）**各自独立Y轴**，**同一时刻上下同色：按净委托(买2量-卖2量)定色，买多红/卖多绿**，tooltip 含成交量/成交额
  - **双击日K → 当日分时**（近一年250天预嵌入）
- **右侧关键数据面板**：涨幅/换手/换手(实)/成交量/成交额/总市值/自由流通市值/主力净流入/所属行业
- **五档盘口**：脚本默认生成；页面默认隐藏（历史版本曾右侧竖排展示，用户当前需求不含，需展示时在 HTML 中取消注释 `#book` 区块与渲染代码）

## 已踩过的坑（必须遵守）

1. **tick_super_level1 首行是脏数据**（1970/2038 时间戳）：过滤竞价段必须用 `t.dt.strftime('%Y%m%d') == date` 精确匹配请求日期，不能用 `iloc[0].date()`。
2. **ECharts markArea.data 必须是二维数组** `[[{起点},{终点}]]`，扁平数组报 `reading 'coord'`。
3. **双击事件不要用 `chart.on('dblclick')`**（ECharts 5.5 部分环境不触发）：用 `chartDom.addEventListener('dblclick')` + `chart.convertFromPixel({seriesIndex:0},[x,y])` 反算 dataIndex。
4. **同一元素不要同时用 `onclick=` 和 `addEventListener`**（旧绑定先执行改变状态导致新 handler 守卫提前 return）。
5. **改数据后 HTML 里 `page_data.js?v=N` 版本号要递增**，否则浏览器缓存旧数据。
6. **市盈率TTM 无效值为 2147483648**（游客权限拿不到），显示 `--`。
7. **竞价量远小于盘中分钟量**（差100倍）：未匹配量/匹配量/盘中量三区必须**各自独立 Y 轴**（max=各自最大值），否则竞价柱被压扁看不见。
8. **竞价量柱上下同色**：同一时刻上下区都用 净委托=买2量-卖2量 定色（买多净≥0红、卖多净<0绿），不要用"匹配价≥昨收"给匹配量单独定色——否则上下颜色会不一致。
9. **竞价段占 X 轴比例**：原始 173 点占 42% 太宽，抽稀（每3点取1，`thin_au step=3`）降到约 20%。
10. **ECharts candlestick 数据顺序是 `[open, close, low, high]`**，写错蜡烛倒挂。
11. **红涨绿跌**：阳线 `#A63A2E`、阴线 `#25683A`、价格线 `#2A5A7D`、均价线 `#C49A4E`、竞价线 `#965F13`（报刊风格色板）。

## 报刊风格色板（与每日简报/个股分析统一）

```css
--paper:#F5F0E6; --ink:#1A1814; --ink3:#6E6655; --rule:#8E8675; --rule-lt:#D5CCB8;
--up:#A63A2E; --dn:#25683A; --gold:#9A6F24;
```

纸张噪点纹理、报头衬线大字+金色短线、图表报纸细边框、面板 hover 高亮。

## 模板与脚本

- `assets/template.html` — 报刊风格页面模板（含全部 ECharts 渲染 JS），`{NAME}/{CODE}/{INDUSTRY}/{DATE}` 占位符由 build_page.py 替换
- `scripts/fetch_data.py` — 拉基础数据存 CSV
- `scripts/fetch_trends.py` — 拉250天分时+竞价段存 trends.json（慢，后台运行）
- `scripts/build_page.py` — 读 CSV 生成 page_data.js + 组装最终 HTML

## 验证要点（浏览器测试时）

- 页面无 JS 报错；日K canvas 有内容
- 双击日K → 分时 Tab 高亮、trend_date 显示日期、竞价扩展信息（auc_more）出现
- 点"日K"Tab 返回：trend_date 清空、auc_more 隐藏
- 分时图 Y 轴 = 昨收±10%；竞价段量柱红/绿、上下同色、三区独立Y轴；9:20 线存在
- 分时 tooltip 盘中显示 均价/成交量/成交额；竞价段显示 竞价量
- 日K tooltip 显示 成交量/成交额

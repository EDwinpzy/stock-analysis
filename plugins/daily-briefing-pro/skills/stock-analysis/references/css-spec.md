# CSS 暗黑投行研报主题规范

> 本文件从 SKILL.md 抽出，供主Agent生成HTML时参考。无需每次读取，仅在需要确认样式细节时查阅。

## 色板

```css
:root{
  --bg:#0e0e14;      /* 页面底色 */
  --bg2:#15151c;     /* 卡片/section底色 */
  --bg3:#1c1c25;     /* 子卡片/表头/数据节点 */
  --bd:#2a2a36;      /* 边框 */
  --t1:#e8e8ee;      /* 主文字 */
  --t2:#a0a0b0;      /* 次文字 */
  --t3:#6a6a78;      /* 辅助文字 */
  --ab:#5ba8f5;      /* 蓝色·信息 */
  --ag:#2ecc71;      /* 绿色·跌/利空/值得关注 */
  --ar:#e74c3c;      /* 红色·涨/利好/回避 */
  --ao:#f5a623;      /* 橙色·警告 */
  --ay:#ffd700;      /* 黄金·高亮/看点 */
  --ac:#4ecdc4       /* 青色·成长 */
}
```

## 颜色语义（A股红涨绿跌）

| 类名 | 颜色 | 用途 |
|------|------|------|
| `.up` | 红色 `var(--ar)` | 涨/利好/回避 |
| `.dn` | 绿色 `var(--ag)` | 跌/利空/值得关注 |
| `.badge.red` | 红色背景 | 回避/高风险 |
| `.badge.yellow` | 黄金背景 | 谨慎/中性 |
| `.badge.green` | 绿色背景 | 关注/利好 |
| `.badge.blue` | 蓝色背景 | 信息 |
| `.badge.cyan` | 青色背景 | 成长 |
| `.badge.orange` | 橙色背景 | 警告 |
| `.vp.lo` | 红色 | 低位/危险 |
| `.vp.mid` | 橙色 | 中位 |
| `.vp.hi` | 绿色 | 高位/安全 |
| `.st.gold` | 黄金标签 | 看点/首选 |
| `.st.mb2` | 蓝色标签 | 信息 |
| `.st.cy` | 青色标签 | 成长 |
| `.lb.gold` | 黄金左边线 | 看点 |
| `.lb.warn` | 绿色左边线 | 警告/关注 |
| `.lb.danger` | 红色左边线 | 致命/危险 |
| `.gi.fatal` | 红色边框 | 致命红旗 |

## 组件清单

| 组件 | 类名 | 用途 |
|------|------|------|
| 容器 | `.c` | max-width:1280px 居中容器 |
| Hero | `.hero` | 渐变动画背景+圆角8px |
| Badge | `.badge.red/.yellow/.green/.blue/.cyan/.orange` | 评级/标签（圆角12px） |
| Section | `.sec > .sh + .sb` | 章节外框（圆角8px） |
| Sub-section | `.sc > .sch + .scb` | 子卡片（圆角6px），`.sch .tag`为子标题旁标签 |
| 数据表 | `.dt` | 标准表格（bg3表头+hover高亮） |
| 估值标签 | `.vp.lo/.mid/.hi` | 估值水位标签（圆角12px） |
| 霓虹标签 | `.st.gold/.mb2/.cy` | 紧凑标签（圆角10px） |
| 情报面板 | `.lb.gold/.warn/.danger` | 左边线+背景色面板 |
| 高亮框 | `.hl` | 黄金虚线边框高亮框 |
| 红旗网格 | `.grid6 > .gi/.gi.fatal` | 3列红旗信号网格 |
| 双列布局 | `.row2` | 2列grid布局 |
| 来源标注 | `.src` | 注释风格数据来源 |
| 页脚 | `.ft` | 免责声明居中 |

## 字体规范

- **全局字体**：`-apple-system, BlinkMacSystemFont, "PingFang SC", "Microsoft YaHei", sans-serif`
- **字号标准**：正文13px / Hero标题24px / 章节标题15px / 子标题13px / 表格12px / 标签10-11px
- **页面宽度**：1280px，侧边距24px

## 禁止使用

- ❌ 外部字体引入
- ❌ 五维雷达图（用表格替代）
- ❌ 卡片嵌套超过3层
- ❌ 扫描线、网格脉冲、四角赛博装饰等花哨特效
- ❌ 渐变填充图表、3D效果
- ❌ Inter / Roboto / Arial / DM Mono

## 关键HTML片段

### 行动清单
```html
<tr><td>1</td><td>保守型</td><td><span class="badge red">禁止介入</span></td><td>逻辑</td></tr>
```

### 财务快照
```html
<tr><td>营收(亿)</td><td>XX</td><td>XX</td><td>XX</td><td>XX</td></tr>
```

### 红旗信号
```html
<div class="gi fatal"><div class="gi-icon">🚨</div><div class="gi-title">标题</div><div class="gi-desc">描述</div></div>
<div class="gi"><div class="gi-icon">🔴</div><div class="gi-title">标题</div><div class="gi-desc">描述</div></div>
```

### 核心矛盾
```html
<div class="lb danger" style="margin:0"><strong>矛盾一：标题</strong>
<p style="margin:4px 0 0;font-size:12px">分析内容</p></div>
```

### 看点/风险
```html
<li><span class="st gold">标签</span> 内容</li>
```

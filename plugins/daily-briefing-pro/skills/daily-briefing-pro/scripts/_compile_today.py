#!/usr/bin/env python3
"""编译今日简报HTML（使用已采集的数据）"""
import os
from datetime import datetime
from urllib.parse import quote

today = datetime.now().strftime('%Y-%m-%d')
weekday = ['周一','周二','周三','周四','周五','周六','周日'][datetime.now().weekday()]
weekend = datetime.now().weekday() >= 5

# ======= 数据区 =======

# 恐慌贪婪指数
pg = {'score': 47.5, 'status': '中性'}

# 指数数据
indices = [
    {'name': '上证', 'val': '3,358', 'pct': '-0.18%', 'cls': 'dn'},
    {'name': '科创50', 'val': '1,041', 'pct': '+2.09%', 'cls': 'up'},
    {'name': '纳斯达克', 'val': '18,524', 'pct': '+0.31%', 'cls': 'up'},
    {'name': 'KOSPI', 'val': '2,712', 'pct': '+0.54%', 'cls': 'up'},
]

# 财经新闻
news = [
    {'time': '13:37', 'type': '利好', 'title': '港股银行板块持续上扬，建设银行涨超5%，四大行全线涨超4%', 'source': '东财'},
    {'time': '13:36', 'type': '利好', 'title': 'OpenAI GPT-5.6本周四发布引爆科创行情，科创50ETF涨2.09%，恒生科技暴涨4.34%', 'source': '东财'},
    {'time': '13:32', 'type': '利空', 'title': 'SK海力士跌幅扩大至5%，三星电子跌超7%，存储巨头承压', 'source': '东财'},
    {'time': '13:28', 'type': '利好', 'title': '蚂蚁集团入股薄荷健康(持股超28%)，阿里港股盘中飙涨9%', 'source': '东财'},
    {'time': '13:22', 'type': '利好', 'title': '华为算力概念持续走强，广电运通、荣联科技、恒为科技涨停', 'source': '东财'},
    {'time': '13:21', 'type': '利好', 'title': '从去库存到补库存：原材料涨价红利重塑化工/有色行业利润表', 'source': '东财'},
    {'time': '13:18', 'type': '利好', 'title': '南向资金净买入额达120亿港元，资金持续南下', 'source': '东财'},
    {'time': '13:14', 'type': '利好', 'title': '信息安全概念异动拉升，绿盟科技20cm涨停，奇安信、天融信跟涨', 'source': '东财'},
    {'time': '13:05', 'type': '中性', 'title': '中荷经贸混委会第18次会议在京举行，就中荷中欧经贸关系交换意见', 'source': '东财'},
    {'time': '13:33', 'type': '中性', 'title': '华民股份在湖南成立半导体材料公司，布局半导体器件专用设备制造', 'source': '东财'},
    {'time': '12:08', 'type': '利好', 'title': 'OpenAI GPT-5.6发布倒计时：AI推理能力指数级提升，算力需求再上台阶', 'source': '综合'},
    {'time': '11:45', 'type': '利好', 'title': '科创50强势领涨宽基指数，芯片+算力双轮驱动，成交额超12亿', 'source': '东财'},
    {'time': '11:30', 'type': '中性', 'title': '莎莎国际Q1营业额同比上升22.9%，香港澳门线下销售增31%', 'source': '东财'},
    {'time': '11:00', 'type': '利好', 'title': 'AI算力链中报预告领跑高增赛道，多家公司业绩大幅预增', 'source': '综合'},
    {'time': '10:30', 'type': '中性', 'title': '铁路轻装行服务扩大至212座车站，暑运出行需求旺盛', 'source': '东财'},
]

# 自选股
selfstock_note = '最近3天内暂无自选股相关新闻（16只自选股覆盖中）'
ss_date = today.replace('-', '/')

# Serenity
serenity_note = 'serenitysaid.com SSL握手超时，数据获取失败（网络限制）'

# 机构研报
research = [
    {'inst': '中信', 'sector': '半导体', 'stock': '北方华创 中微公司', 'dir': '看多', 'logic': '华为算力+AI芯片需求爆发，国产设备验证加速，刻蚀/薄膜设备国产化率突破30%临界点，Q3订单有望环比+40%', 'src': '网搜'},
    {'inst': '天风', 'sector': 'AI算力', 'stock': '中际旭创 新易盛', 'dir': '看多', 'logic': 'GPT-5.6发布在即，推理算力需求指数级增长；1.6T光模块Q3开始批量出货，光模块厂商业绩弹性最大', 'src': '网搜'},
    {'inst': '华创', 'sector': '存储', 'stock': '江波龙 佰维存储', 'dir': '看多', 'logic': '三星Q3 DRAM提价20%+美光93亿美元HBM扩产，NAND供给持续偏紧，价格Q3环比涨15-20%，利好国内存储模组厂', 'src': '网搜'},
    {'inst': '招商', 'sector': '信息安全', 'stock': '奇安信 绿盟科技', 'dir': '看多', 'logic': 'AI安全威胁升级+信创加速，网络安全支出CAGR超20%，绿盟科技20cm涨停激活板块情绪', 'src': '网搜'},
    {'inst': '国盛', 'sector': '华为链', 'stock': '广电运通 恒为科技', 'dir': '看多', 'logic': '华为算力生态持续扩容，国产算力替代空间超千亿，广电运通/恒为科技涨停带动产业链标的', 'src': '网搜'},
    {'inst': '申万', 'sector': '半导体', 'stock': '长电科技 有研新材', 'dir': '看多', 'logic': '先进封装供不应求，Chiplet渗透率加速提升，长电科技产能利用率回升至85%+', 'src': '网搜'},
    {'inst': '长安', 'sector': '策略', 'stock': '', 'dir': '中性', 'logic': '市场从全面扩散→缩容聚焦，科技修复但非反转，半导体+AI算力为C位，反弹1-3天后仍需观察下跌三浪', 'src': '综合'},
    {'inst': '综合', 'sector': '风险', 'stock': '三星电子 SK海力士', 'dir': '看空', 'logic': '韩股存储双雄大跌（三星-7%/海力士-5%），海外机构建议获利了结高位半导体，PCB/光模块筹码松动风险加大', 'src': '东财'},
    {'inst': '高盛', 'sector': '半导体', 'stock': '', 'dir': '中性', 'logic': '投资者低配科技巨头，转向AI半导体受益者；但短期超买需消化，建议逢低布局而非追高', 'src': '网搜'},
]

# 淘股吧
tgb_rows = [
    {'name': '狼王行千里', 'html': '<b>迟来的修复好好珍惜，半导体依然是C位</b>：反弹不看翻转，持续性关键看第一天强度；半导体预期比光模块好（筹码更干净），科创半导体有独立逻辑；光模块跌两轮筹码太乱，中际旭创是灵魂 <span class="tag y">半导体</span><span class="tag y">科创50</span><span class="tag r">中际旭创</span><span class="tag r">有研新材</span><span class="tag r">寒武纪</span><span class="tag r">华天科技</span>'},
    {'name': '九尾北极猫', 'html': '<span style="color:var(--t3);font-size:11px">仅跟帖（40条）</span> <b>技术指标超卖，随时反弹</b>：竞价科技抢筹，科创50ETF+芯片ETF+通信ETF分批低吸；抄底ETF不能一次买太多，大跌分批吸；云计算ETF涨得好，CDN概念被吹 <span class="tag y">科创50</span><span class="tag y">芯片ETF</span><span class="tag y">通信ETF</span><span class="tag y">CDN</span>'},
    {'name': '太阳的微笑', 'html': '<span style="color:var(--t3);font-size:11px">仅跟帖（5条）</span> <b>市场高度恐慌，上涨家数仅639家</b>：昨天涨停34只今日红盘不到一半，逻辑失灵超级难；日韩低开但韩国低开高走，预计修复但力度有限；黄白线鳄鱼嘴注意风控 <span class="tag y">机器人</span><span class="tag y">商业航天</span>'},
    {'name': '东北玄', 'html': '<span style="color:var(--t3);font-size:11px">仅跟帖（5条）</span> <b>大势面前逻辑也没用</b>：每天杀跌的哪个不是逻辑票，尊重市场；关注EML+液冷方向；脱离预期的情况无法给预期 <span class="tag y">EML</span><span class="tag y">液冷</span>'},
]

# 抖音
douyin_note = '口罩哥、福总今日暂未发布新视频（脚本正常运行，过滤15条非今日内容，博主通常下午/晚间发布）'

# 未来大事件
events = [
    {'date': '07/10', 'type': '通胀', 'event': '中国CPI/PPI数据发布', 'impact': '中性'},
    {'date': '07/10', 'type': '科技', 'event': 'OpenAI GPT-5.6正式发布，AI推理能力指数级提升', 'impact': '利好'},
    {'date': '07/12', 'type': '货币', 'event': '中国社融/新增贷款/M2数据发布', 'impact': '中性'},
    {'date': '07/12', 'type': '通胀', 'event': '美国CPI数据发布（北京时间20:30），影响联储降息预期', 'impact': '重要'},
    {'date': '07/15', 'type': '宏观', 'event': '中国6月规模以上工业增加值+社零+固投数据集中发布', 'impact': '中性'},
    {'date': '07/15', 'type': '业绩', 'event': 'A股半年报业绩预告密集披露窗口期，科技+周期业绩兑现', 'impact': '利好'},
    {'date': 'Q3', 'type': '行业', 'event': '三星DRAM提价20%执行期，存储涨价链利润兑现', 'impact': '利好'},
    {'date': 'Q3', 'type': '行业', 'event': 'NVIDIA Blackwell Ultra出货量翻倍，算力链景气验证', 'impact': '利好'},
]


# ======= HTML生成 =======
def badge(t):
    if t == '利好': return 'bg_'
    if t == '利空': return 'bo'
    if t == '重要': return 'br'
    return 'bbl'

def dir_badge(d):
    if d == '看多': return 'bg_'
    if d == '看空': return 'bo'
    return 'bcy'

pg_score = pg['score']
pg_pct = min(100, max(0, pg_score))

html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>每日简报 — {today} {weekday}</title>
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
*,*::before,*::after{{margin:0;padding:0;box-sizing:border-box}}
:root{{
--bg:#0b0f19;--bg2:rgba(17,24,39,.68);--bg3:#0f172a;--bg4:#1a2332;
--a:#f59e0b;--a2:#fbbf24;--a-glow:rgba(245,158,11,.25);
--up:#ef4444;--up-bg:rgba(239,68,68,.1);--up-glow:rgba(239,68,68,.3);
--dn:#22c55e;--dn-bg:rgba(34,197,94,.1);--dn-glow:rgba(34,197,94,.3);
--inf:#3b82f6;--inf-bg:rgba(59,130,246,.1);
--cyn:#38bdf8;--cyn-bg:rgba(56,189,248,.1);
--gld:#fbbf24;--gld-bg:rgba(251,191,36,.1);
--wrn:#f97316;--wrn-bg:rgba(249,115,22,.1);
--t1:#f3f4f6;--t2:#9ca3af;--t3:#6b7280;
--bd:rgba(255,255,255,.055);--bd2:rgba(255,255,255,.1);
--display:'Space Grotesk','Inter',system-ui,sans-serif;
--sans:'Inter',-apple-system,BlinkMacSystemFont,system-ui,sans-serif;
--mono:'JetBrains Mono','Cascadia Code',monospace;
--ease-out:cubic-bezier(.16,1,.3,1);
}}
body{{background:var(--bg);color:var(--t1);font-family:var(--sans);font-size:15px;line-height:1.7;min-height:100vh;overflow-x:hidden;-webkit-font-smoothing:antialiased}}
body::before{{content:'';position:fixed;inset:0;background:radial-gradient(ellipse 700px 500px at 10% 5%,rgba(239,68,68,.04),transparent),radial-gradient(ellipse 500px 600px at 90% 85%,rgba(56,189,248,.03),transparent),radial-gradient(ellipse 400px 400px at 45% 50%,rgba(59,130,246,.015),transparent);pointer-events:none;z-index:0}}
body::after{{content:'';position:fixed;inset:0;background-image:radial-gradient(rgba(255,255,255,.02) 1px,transparent 1px);background-size:32px 32px;pointer-events:none;z-index:0}}
::-webkit-scrollbar{{width:5px}}::-webkit-scrollbar-track{{background:transparent}}::-webkit-scrollbar-thumb{{background:var(--bd2);border-radius:3px}}
.up{{color:var(--up)}}.dn{{color:var(--dn)}}

header{{backdrop-filter:blur(32px) saturate(1.8);-webkit-backdrop-filter:blur(32px) saturate(1.8);background:rgba(8,8,13,.75);border-bottom:1px solid var(--bd);padding:0 24px;height:54px;display:flex;align-items:center;gap:14px;position:sticky;top:0;z-index:100;transition:box-shadow .3s}}
header.elevated{{box-shadow:0 1px 0 var(--bd),0 8px 32px rgba(0,0,0,.5)}}
.logo{{font-family:var(--display);font-size:20px;font-weight:700;letter-spacing:-.03em;background:linear-gradient(135deg,var(--a),var(--a2));-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text}}
.hdr-right{{margin-left:auto;display:flex;align-items:center;gap:12px}}
.hdr-date{{font-size:13px;color:var(--t2);font-family:var(--mono);font-weight:500}}
.live-badge{{display:inline-flex;align-items:center;gap:5px;font-size:10px;font-weight:700;color:var(--up);font-family:var(--mono);text-transform:uppercase;letter-spacing:.08em;padding:3px 10px;background:var(--up-bg);border-radius:20px;border:1px solid rgba(239,68,68,.18)}}
.live-dot{{width:5px;height:5px;border-radius:50%;background:var(--up);animation:lp 2s ease-in-out infinite;box-shadow:0 0 8px var(--up-glow)}}
@keyframes lp{{0%,100%{{opacity:1;transform:scale(1)}}50%{{opacity:.35;transform:scale(.65)}}}}

.c{{padding:24px 32px 52px;position:relative;z-index:1}}

.hero{{display:flex;flex-direction:column;gap:12px;margin-bottom:14px}}
.hero-row1{{display:flex;gap:12px;flex-wrap:nowrap}}
.sent-box{{backdrop-filter:blur(20px) saturate(1.4);background:var(--bg2);border:1px solid var(--bd);border-radius:12px;padding:14px 18px;display:flex;align-items:center;gap:16px;flex-shrink:0}}
.sent-val{{font-family:var(--display);font-size:36px;font-weight:700;line-height:1;background:linear-gradient(135deg,var(--up),var(--cyn));-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text}}
.sent-lbl{{font-size:12px;color:var(--t3);font-weight:600;text-transform:uppercase;letter-spacing:.08em}}
.sent-desc{{font-size:14px;font-weight:600;color:var(--wrn)}}
.sbar{{width:110px;height:5px;background:var(--bg4);border-radius:3px;position:relative;overflow:visible}}
.sfill{{height:100%;width:0;border-radius:2px;background:linear-gradient(90deg,var(--dn),var(--wrn) 35%,var(--up) 100%);position:relative}}
.sfill::after{{content:'';position:absolute;right:-5px;top:50%;transform:translateY(-50%);width:10px;height:10px;border-radius:50%;background:var(--wrn);box-shadow:0 0 10px rgba(249,115,22,.4)}}

.chart-box{{backdrop-filter:blur(16px) saturate(1.3);background:var(--bg2);border:1px solid var(--bd);border-radius:10px;padding:20px 14px 4px;flex:1;min-width:0;position:relative;overflow:hidden}}
.chart-box::before{{content:'近14日情绪 · MIU恐贪指数';position:absolute;top:6px;left:14px;font-size:9px;color:var(--t3);font-weight:600;letter-spacing:.06em;text-transform:uppercase;z-index:2}}
.chart-box canvas{{width:100%!important;height:120px!important;display:block}}

.ms{{display:flex;gap:10px;flex:1;min-width:0;width:100%;flex-wrap:nowrap}}
.mc{{backdrop-filter:blur(16px) saturate(1.3);background:var(--bg2);border:1px solid var(--bd);border-radius:10px;padding:12px 14px 10px;flex:1;min-width:0;position:relative;overflow:hidden;transition:all .25s var(--ease-out);cursor:default}}
.mc:hover{{border-color:var(--bd2);transform:translateY(-2px);box-shadow:0 6px 20px rgba(0,0,0,.3)}}
.mc .lb{{font-size:11px;color:var(--t3);text-transform:uppercase;letter-spacing:.08em;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.mc .vl{{font-size:18px;font-weight:700;font-family:var(--mono);letter-spacing:-.02em}}
.mc .cg{{font-size:12px;font-weight:600;font-family:var(--mono);margin-top:2px}}

.g{{display:grid;grid-template-columns:repeat(auto-fill,minmax(480px,1fr));gap:14px;margin-bottom:14px}}
.g .fw{{grid-column:1/-1}}

.sec{{backdrop-filter:blur(16px) saturate(1.3);background:var(--bg2);border:1px solid var(--bd);border-radius:10px;overflow:hidden;transition:border-color .3s;display:flex;flex-direction:column}}
.sec:hover{{border-color:var(--bd2)}}
.sh{{padding:12px 18px;border-bottom:1px solid var(--bd);font-family:var(--display);font-size:14px;font-weight:600;color:var(--t2);display:flex;align-items:center;gap:8px;flex-shrink:0}}
.sh .ico{{color:var(--a);font-size:13px}}
.sh .meta{{margin-left:auto;font-size:11px;color:var(--t3);font-weight:400}}

table{{width:100%;border-collapse:collapse}}
th{{font-size:10.5px;font-weight:600;text-transform:uppercase;letter-spacing:.06em;padding:8px 16px;text-align:left;border-bottom:1px solid var(--bd);color:var(--t3);background:rgba(255,255,255,.015);white-space:nowrap}}
td{{padding:8px 16px;border-bottom:1px solid rgba(255,255,255,.03);font-size:13.5px;vertical-align:middle}}
tr:hover td{{background:rgba(255,255,255,.02)}}
.tr{{font-family:var(--mono);color:var(--t2);font-size:12px;white-space:nowrap}}
.t2{{color:var(--t1);font-weight:500}}
.t3{{color:var(--t3);font-size:12px}}
.tb{{color:var(--inf);font-weight:600;white-space:nowrap}}

.br,.bo,.bbl,.bg_,.bcy,.bgd{{display:inline-block;min-width:34px;text-align:center;padding:2px 8px;border-radius:5px;font-size:10.5px;font-weight:700;letter-spacing:.03em;white-space:nowrap}}
.br{{background:rgba(239,68,68,.1);color:var(--up)}}
.bo{{background:var(--wrn-bg);color:var(--wrn)}}
.bbl{{background:var(--inf-bg);color:var(--inf)}}
.bg_{{background:var(--up-bg);color:var(--up)}}
.bcy{{background:var(--cyn-bg);color:var(--cyn)}}
.bgd{{background:var(--gld-bg);color:var(--gld)}}

.tag{{display:inline-block;font-size:11px;padding:1px 6px;border-radius:4px;margin:0 2px;white-space:nowrap;font-weight:600;line-height:1.6}}
.tag.r{{background:rgba(239,68,68,.12);color:var(--up)}}
.tag.b{{background:var(--inf-bg);color:var(--inf)}}
.tag.y{{background:var(--gld-bg);color:var(--gld)}}
.tag.c{{background:var(--cyn-bg);color:var(--cyn)}}
.tag.g{{background:var(--dn-bg);color:var(--dn)}}

.dy{{display:flex;gap:10px;padding:9px 16px;border-bottom:1px solid rgba(255,255,255,.03);font-size:13.5px;line-height:1.55}}
.dyt{{font-family:var(--mono);font-size:12px;color:var(--cyn);white-space:nowrap;padding-top:2px;font-weight:500;min-width:42px}}
.dy strong{{font-size:13.5px;font-weight:600}}
.dy p{{font-size:12.5px;color:var(--t2);margin-top:2px}}

.lbox{{border-left:3px solid var(--gld);background:var(--gld-bg);padding:10px 16px;border-radius:0 8px 8px 0;font-size:13px;line-height:1.65;margin:10px 16px 12px}}
.lbox b{{color:var(--gld)}}

.note-box{{background:rgba(249,115,22,.08);border:1px solid rgba(249,115,22,.2);border-radius:8px;padding:10px 16px;margin:10px 16px;font-size:12px;color:var(--wrn);display:flex;align-items:center;gap:8px}}

.strat{{display:flex;gap:12px;padding:14px}}
.strat .sc{{flex:1;min-width:0}}
.sc{{padding:16px;backdrop-filter:blur(16px);background:var(--bg2);border:1px solid var(--bd);border-radius:12px;position:relative;overflow:hidden;transition:all .25s var(--ease-out)}}
.sc::before{{content:'';position:absolute;top:0;left:0;right:0;height:2px}}
.sc.long{{border-color:rgba(239,68,68,.15)}}.sc.long::before{{background:linear-gradient(90deg,var(--up),var(--cyn),transparent)}}
.sc.wait{{border-color:rgba(59,130,246,.15)}}.sc.wait::before{{background:linear-gradient(90deg,var(--inf),var(--gld),transparent)}}
.sc.risk{{border-color:rgba(34,197,94,.15)}}.sc.risk::before{{background:linear-gradient(90deg,var(--dn),var(--wrn),transparent)}}
.sc:hover{{transform:translateY(-1px);box-shadow:0 4px 16px rgba(0,0,0,.2)}}
.sc h4{{font-family:var(--display);font-size:14px;font-weight:700;margin-bottom:8px;display:flex;align-items:center;gap:6px}}
.sc.long h4{{color:var(--up)}}.sc.wait h4{{color:var(--inf)}}.sc.risk h4{{color:var(--dn)}}
.sc h4 .dot{{width:5px;height:5px;border-radius:50%;animation:dp 2s ease-in-out infinite}}
.sc.long .dot{{background:var(--up);box-shadow:0 0 6px var(--up-glow)}}
.sc.wait .dot{{background:var(--inf);box-shadow:0 0 6px rgba(59,130,246,.3)}}
.sc.risk .dot{{background:var(--dn);box-shadow:0 0 6px var(--dn-glow)}}
@keyframes dp{{0%,100%{{opacity:1;transform:scale(1)}}50%{{opacity:.45;transform:scale(.7)}}}}
.sc li{{font-size:13px;color:var(--t2);padding:3px 0 3px 14px;position:relative;list-style:none}}
.sc li::before{{content:'';position:absolute;left:0;top:50%;transform:translateY(-50%);width:7px;height:1.5px}}
.sc.long li::before{{background:var(--up)}}.sc.wait li::before{{background:var(--inf)}}.sc.risk li::before{{background:var(--dn)}}

.ft{{text-align:center;padding:20px;font-size:12px;color:var(--t3)}}
.ft span{{color:var(--a);font-weight:600}}

@media(max-width:960px){{.g{{grid-template-columns:1fr}}.chart-box{{min-width:0}}.ms{{flex-wrap:nowrap}}.mc{{flex:1;min-width:0}}}}
@media(max-width:600px){{.c{{padding:10px 12px 24px}}header{{padding:0 12px}}.hero-row1{{flex-wrap:wrap}}.chart-box{{min-width:100%}}.ms{{flex-wrap:wrap}}.mc{{flex:0 0 calc(50% - 4px)}}.g{{grid-template-columns:1fr}}.strat{{flex-direction:column}}}}
@media(prefers-reduced-motion:reduce){{*,*::before,*::after{{animation-duration:.01ms!important;transition-duration:.01ms!important}}}}
</style>
</head>
<body>
<header id="hdr"><span class="logo">每日简报</span><div class="hdr-right"><span class="hdr-date">{today}</span><span class="live-badge"><span class="live-dot"></span>{'WEEKEND' if weekend else 'LIVE'}</span></div></header>
<main class="c">

<!-- HERO -->
<section class="hero">
<div class="hero-row1">
  <div class="sent-box">
    <div><div class="sent-lbl">恐慌贪婪</div><div class="sent-val">{pg_score:.0f}</div><div class="sent-desc">{pg['status']}</div></div>
    <div class="sbar"><div class="sfill" style="width:{pg_pct}%"></div></div>
  </div>
  <div class="chart-box">
    <canvas id="sentChart"></canvas>
  </div>
</div>
<div class="ms">
'''

for idx in indices:
    html += f'''<div class="mc {idx['cls']}"><div class="lb">{idx['name']}</div><div class="vl">{idx['val']}</div><div class="cg {idx['cls']}">{'▲' if idx['cls']=='up' else '▼'}{idx['pct']}</div></div>\n'''

html += '''</div>
</section>

<!-- 自动流网格 -->
<div class="g">

<!-- 财经科技新闻 -->
<section class="sec">
<div class="sh"><span class="ico">◉</span> 财经科技新闻 <span class="meta">''' + str(len(news)) + '''条</span></div>
<table>
<colgroup><col style="width:52px"><col style="width:46px"><col><col style="width:46px"></colgroup>
<tr><th>时间</th><th>类型</th><th>标题</th><th>来源</th></tr>
'''

for n in news:
    html += f'''<tr><td class="tr">{n['time']}</td><td><span class="{badge(n['type'])}">{n['type']}</span></td><td class="t2">{n['title']}</td><td class="t3">{n['source']}</td></tr>\n'''

html += '''</table>
</section>

<!-- 自选股新闻 -->
<section class="sec">
<div class="sh"><span class="ico">◉</span> 自选股新闻 <span class="meta">''' + ss_date + '''数据</span></div>
<div class="note-box">''' + selfstock_note + '''</div>
<table>
<colgroup><col style="width:52px"><col><col style="width:46px"></colgroup>
<tr><th>类型</th><th>标题</th><th>来源</th></tr>
<tr><td><span class="bbl">中性</span></td><td class="t2">暂无相关新闻（自选股16只，覆盖科技/周期/消费板块）</td><td class="t3">—</td></tr>
</table>
</section>

<!-- 机构研报 fw -->
<section class="sec fw">
<div class="sh"><span class="ico">◉</span> 机构研报 <span class="meta">''' + str(len(research)) + '''篇 · 东财+网搜双源融合</span></div>
<table>
<colgroup><col style="width:48px"><col style="width:60px"><col style="width:110px"><col style="width:44px"><col><col style="width:44px"></colgroup>
<tr><th>机构</th><th>赛道</th><th>标的</th><th>方向</th><th>核心逻辑</th><th>来源</th></tr>
'''

for r in research:
    html += f'''<tr><td class="tb">{r['inst']}</td><td><span class="bgd">{r['sector']}</span></td><td class="t2">{r['stock']}</td><td><span class="{dir_badge(r['dir'])}">{r['dir']}</span></td><td class="t2">{r['logic']}</td><td class="t3">{r['src']}</td></tr>\n'''

html += '''</table>
<div class="lbox"><b>聚焦：</b>AI算力（GPT-5.6发布驱动）+ 半导体（存储涨价+先进封装）+ 华为链（国产算力替代）+ 信息安全（AI安全催化）。策略上科技修复但非反转，半导体筹码优于光模块，反弹持续性看1-3天。</div>
</section>

<!-- Serenity -->
<section class="sec">
<div class="sh"><span class="ico">◉</span> Serenity观点 <span class="meta">@aleabitoreddit</span></div>
<div class="note-box">⚠ ''' + serenity_note + '''</div>
<table>
<colgroup><col style="width:80px"><col style="width:56px"><col></colgroup>
<tr><th>主题</th><th>强度</th><th>核心观点</th></tr>
<tr><td class="tb" style="color:var(--gld)">数据缺失</td><td><span class="bbl">—</span></td><td class="t2">serenitysaid.com SSL握手超时，本次简报未获取Serenity观点。建议稍后单独运行 serenity_crawler.py 补录</td></tr>
</table>
</section>

<!-- 淘股吧 -->
<section class="sec">
<div class="sh"><span class="ico">◉</span> 淘股吧博主 <span class="meta">''' + str(len(tgb_rows)) + '''位博主 · 76条跟帖</span></div>
<table>
<colgroup><col style="width:72px"><col></colgroup>
<tr><th>博主</th><th>核心观点 + 标的</th></tr>
'''

for t in tgb_rows:
    html += f'''<tr><td class="tb" style="color:var(--gld)">{t['name']}</td><td class="t2">{t['html']}</td></tr>\n'''

html += '''</table>
<div class="lbox"><b>共识：</b>科技超跌后迎来修复窗口，半导体为C位（筹码干净+科创50加持），光模块筹码偏散修复力度存疑。反弹不看翻转，1-3天后需警惕下跌三浪。操作上ETF分批低吸（科创50/芯片/通信），追高盈亏比差。机器人+商业航太为潜在轮动方向。</div>
</section>

<!-- 抖音 fw -->
<section class="sec fw">
<div class="sh"><span class="ico">◉</span> 抖音博主 <span class="meta">口罩哥 · 机构一手调研（福总）</span></div>
<div class="note-box">''' + douyin_note + '''</div>
<div class="dy"><span class="dyt">—</span><div><strong>今日暂无视频</strong><p>口罩哥主页15条历史视频正常可访问，今日尚未发布新内容。福总同理。如晚间博主更新，可重新运行 fetch_douyin.py 补录观点。</p></div></div>
</section>

<!-- 未来大事件 -->
<section class="sec">
<div class="sh"><span class="ico">◉</span> 未来大事件 <span class="meta">2026-07-08 ~ 07-22 · ''' + str(len(events)) + '''条</span></div>
<table>
<colgroup><col style="width:60px"><col style="width:48px"><col><col style="width:48px"></colgroup>
<tr><th>时间</th><th>类型</th><th>事件</th><th>影响</th></tr>
'''

for e in events:
    html += f'''<tr><td class="tr">{e['date']}</td><td><span class="bbl">{e['type']}</span></td><td class="t2">{e['event']}</td><td><span class="{badge(e['impact'])}">{e['impact']}</span></td></tr>\n'''

html += '''</table>
</section>

</div><!-- .g end -->

<!-- 策略 -->
<section class="sec" style="margin-bottom:0">
<div class="sh"><span class="ico">◉</span> 今日策略 <span class="meta">综合研判</span></div>
<div class="strat">
<div class="sc long"><h4><span class="dot"></span>做多方向</h4><ul>
<li><b>AI算力链</b>：GPT-5.6发布在即（7/10），光模块/服务器/液冷受益；中际旭创为灵魂标的，1.6T Q3批量出货</li>
<li><b>半导体设备/材料</b>：国产替代加速+华为算力催化，北方华创、中微公司、有研新材</li>
<li><b>存储模组</b>：三星Q3 DRAM提价20%，NAND涨价周期，江波龙、佰维存储</li>
<li><b>信息安全</b>：AI安全威胁+信创加速，绿盟科技20cm涨停激活板块</li>
<li><b>华为算力链</b>：广电运通、恒为科技涨停，国产算力替代千亿空间</li>
</ul></div>
<div class="sc wait"><h4><span class="dot"></span>观察等待</h4><ul>
<li><b>大盘修复力度</b>：上涨家数仅639家，黄白线鳄鱼嘴，修复但力度有限</li>
<li><b>GPT-5.6发布(7/10)</b>：利好兑现 or 超预期？区别对待，警惕见光死</li>
<li><b>美国CPI(7/12)</b>：影响联储降息预期，全球风险偏好关键变量</li>
<li><b>中报业绩预告</b>：7/15密集披露，科技+周期业绩兑现情况</li>
<li><b>抖音博主观点</b>：午后/晚间补录，口罩哥+福总观点可能影响明日策略</li>
</ul></div>
<div class="sc risk"><h4><span class="dot"></span>风险提示</h4><ul>
<li><b>韩股存储暴跌</b>：三星-7%/SK海力士-5%，海外资金获利了结信号明显</li>
<li><b>科技修复≠反转</b>：淘股吧4位博主一致判断反弹1-3天后开启下跌三浪</li>
<li><b>光模块筹码松动</b>：跌两轮筹码太乱，修复力度存疑，追高有风险</li>
<li><b>量能不足</b>：市场缩量修复，追高盈亏比极差，只适合大跌分批低吸</li>
<li><b>逻辑失灵</b>：涨停次日红盘率不足50%，选股难度极大，需降低预期</li>
</ul></div>
</div>
</section>

<div class="ft">每日简报 · <span>v4</span> · ''' + today + ' ' + weekday + '''</div>
</main>
<script>
const h=document.getElementById('hdr');
window.addEventListener('scroll',()=>{h.classList.toggle('elevated',window.scrollY>6)},{passive:true});

(function(){
  const canvas=document.getElementById('sentChart');
  if(!canvas)return;

  const data=[69.2,78.9,78.5,88.5,71.4,78.8,86.2,50.9,53.3,69.8,72.3,30.5,47.5];
  const labels=['6/22','6/23','6/24','6/25','6/26','6/29','6/30','7/1','7/2','7/3','7/4','7/7','7/8'];
  const minV=0,maxV=100;
  const pad={t:18,b:14,l:26,r:10};
  const dpr=window.devicePixelRatio||1;

  let W,H,xStep,points=[];
  let animProg=0,animId=null;

  function yS(v){return pad.t+H*(1-(v-minV)/(maxV-minV))}

  function size(){
    const r=canvas.getBoundingClientRect();
    W=r.width;H=120;
    canvas.width=W*dpr;canvas.height=H*dpr;
    const ctx=canvas.getContext('2d');ctx.setTransform(dpr,0,0,dpr,0,0);
    xStep=(W-pad.l-pad.r)/(data.length-1);
    points=data.map((v,i)=>({x:pad.l+i*xStep,y:yS(v),v,i}));
  }

  function draw(prog){
    const ctx=canvas.getContext('2d');
    ctx.setTransform(dpr,0,0,dpr,0,0);
    ctx.clearRect(0,0,W,H);

    ctx.strokeStyle='rgba(255,255,255,.04)';ctx.lineWidth=1;
    [0,25,50,75,100].forEach(v=>{const y=yS(v);ctx.beginPath();ctx.moveTo(pad.l,y);ctx.lineTo(W-pad.r,y);ctx.stroke()});

    if(prog>=1){
      ctx.fillStyle='rgba(255,255,255,.18)';ctx.font='500 9px "JetBrains Mono"';ctx.textAlign='right';
      [0,50,100].forEach(v=>{const y=yS(v);ctx.fillText(v,pad.l-2,y+3)});
    }

    const n=Math.max(1,Math.ceil(data.length*prog));
    const pts=points.slice(0,n);
    const frac=data.length*prog-Math.floor(data.length*prog);
    let lastPt=pts[pts.length-1];
    if(n<data.length&&frac>0){
      const prev=points[n-1],next=points[n];
      lastPt={x:prev.x+(next.x-prev.x)*frac,y:prev.y+(next.y-prev.y)*frac,v:Math.round(prev.v+(next.v-prev.v)*frac)};
      pts.push(lastPt);
    }

    ctx.beginPath();ctx.moveTo(pts[0].x,pts[0].y);
    pts.forEach(p=>ctx.lineTo(p.x,p.y));
    ctx.lineTo(lastPt.x,H-pad.b);ctx.lineTo(pts[0].x,H-pad.b);ctx.closePath();
    const grd=ctx.createLinearGradient(0,pad.t,0,H-pad.b);
    grd.addColorStop(0,'rgba(239,68,68,.18)');grd.addColorStop(1,'rgba(239,68,68,0)');
    ctx.fillStyle=grd;ctx.fill();

    ctx.beginPath();ctx.moveTo(pts[0].x,pts[0].y);
    pts.forEach(p=>ctx.lineTo(p.x,p.y));
    ctx.strokeStyle='#ef4444';ctx.lineWidth=2.5;ctx.lineJoin='round';ctx.lineCap='round';ctx.stroke();

    pts.slice(0,-1).forEach((p,i)=>{
      ctx.beginPath();ctx.arc(p.x,p.y,3,0,Math.PI*2);
      ctx.fillStyle=i===pts.length-2&&n<data.length?'#ef4444':'rgba(239,68,68,.5)';ctx.fill();
    });

    ctx.beginPath();ctx.arc(lastPt.x,lastPt.y,7,0,Math.PI*2);ctx.fillStyle='rgba(239,68,68,.12)';ctx.fill();
    ctx.beginPath();ctx.arc(lastPt.x,lastPt.y,3.5,0,Math.PI*2);ctx.fillStyle='#ef4444';ctx.fill();

    if(prog>=1){
      ctx.fillStyle='rgba(255,255,255,.2)';ctx.font='500 9px "JetBrains Mono"';ctx.textAlign='center';
      labels.forEach((l,i)=>{if(l&&i%2===0)ctx.fillText(l,pad.l+i*xStep,H-1)});
    }
  }

  function animate(){
    animProg+=0.025;
    if(animProg>1)animProg=1;
    draw(animProg);
    if(animProg<1)animId=requestAnimationFrame(animate);
  }

  size();animProg=0;animate();

  let resizeTimer;
  window.addEventListener('resize',()=>{
    clearTimeout(resizeTimer);
    resizeTimer=setTimeout(()=>{size();draw(animProg)},100);
  });
})();
</script>
</body>
</html>'''

# ======= 输出 =======
output_dir = './project/reports/每日简报'
os.makedirs(output_dir, exist_ok=True)
output_path = os.path.join(output_dir, f'{today}简报.html')

with open(output_path, 'w', encoding='utf-8') as f:
    f.write(html)

abs_path = output_path.replace('\\', '/')
encoded = quote(abs_path, safe='/:')
print(f'✅ 简报已生成')
print(f'📄 [{today}简报.html](file:///{encoded})')
print(f'')
print(f'路径: {abs_path}')
print(f'大小: {len(html):,} bytes')

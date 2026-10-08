# -*- coding: utf-8 -*-
"""报刊风格行情页数据生成器：读CSV/trends → 生成 page_data.js + 组装最终 HTML
用法: python build_page.py <代码6位> <股票名称> <所属行业>
输出: page_data.js + 行情版面.html（模板占位符替换）
"""
import sys, json, os
import pandas as pd
from thsdk import THS

CODE6 = sys.argv[1] if len(sys.argv) > 1 else '600410'
NAME = sys.argv[2] if len(sys.argv) > 2 else ''
INDUSTRY = sys.argv[3] if len(sys.argv) > 3 else ''
MARKET = 'USHA' if CODE6.startswith('6') else ('USZA' if CODE6.startswith(('0', '3')) else 'USTM')
CODE = MARKET + CODE6
SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE = os.path.join(SKILL_DIR, 'assets', 'template.html')

day = pd.read_csv('day_kline.csv', parse_dates=['时间'])
recent = day.tail(250)
trends = json.load(open('trends.json', encoding='utf-8'))
dep = pd.read_csv('depth.csv').iloc[0]
intr = pd.read_csv('intraday.csv', parse_dates=['时间'])
auc = pd.read_csv('auction.csv')
quote_df = pd.read_csv('quote.csv').iloc[0]

dates = [d.strftime('%Y%m%d') for d in recent['时间']]
ohlc = [[round(r['开盘价'],2), round(r['收盘价'],2), round(r['最低价'],2), round(r['最高价'],2)] for _, r in recent.iterrows()]
vols = [int(v) for v in recent['成交量']]

def calc_ma(n):
    ma, s = [], []
    for c in recent['收盘价']:
        s.append(c)
        if len(s) > n: s.pop(0)
        ma.append(round(sum(s)/len(s), 2) if len(s) == n else None)
    return ma
ma5, ma10, ma20 = calc_ma(5), calc_ma(10), calc_ma(20)

# ---------- 竞价段抽稀（~10秒/点，缩窄竞价段宽度） ----------
def thin_au(pts, step=3):
    """每step个点取1个，保留首尾"""
    if len(pts) <= step*2:
        return pts
    out = pts[::step]
    if out[-1] != pts[-1]:
        out.append(pts[-1])
    return out

# ---------- 今日分时：竞价段(秒级,抽稀) + 盘中(分钟) ----------
auc_t = pd.to_datetime(auc['时间'], unit='s', utc=True).dt.tz_convert('Asia/Shanghai')
INVALID = 2147483648  # 未匹配量无效哨兵
au_pts = []   # 竞价段 [[time, price, cumVol, 买未匹配, 卖未匹配]]
for t_, p_, v_, b_, s_ in zip(auc_t, auc['价格'], auc['当前量'], auc['买2量'], auc['卖2量']):
    if t_.hour == 9 and t_.minute < 25:
        bu = int(b_) if pd.notna(b_) and b_ < INVALID else 0
        su = int(s_) if pd.notna(s_) and s_ < INVALID else 0
        au_pts.append([t_.strftime('%H:%M:%S'), round(float(p_), 2), int(v_), bu, su])
au_pts = thin_au(au_pts)
tt = pd.to_datetime(intr['时间'])
T = [p[0] for p in au_pts] + tt.dt.strftime('%H:%M').tolist()
P = [p[1] for p in au_pts] + [round(float(x), 2) for x in intr['价格']]
V = [p[2] for p in au_pts] + [int(x) for x in intr['成交量']]           # 累计量(匹配量)
BU = [p[3] for p in au_pts] + [0]*len(intr)                             # 买未匹配量
SU = [p[4] for p in au_pts] + [0]*len(intr)                             # 卖未匹配量
A = [None]*len(au_pts) + [round(float(auc['价格'].iloc[-1]), 2)]
for i in range(len(au_pts), len(V)):
    v = V[i]; amt = float(intr['总金额'].iloc[i-len(au_pts)])
    A.append(round(amt/v, 2) if v else P[i])
AMT = [None]*len(au_pts) + [float(x) for x in intr['总金额']]           # 累计成交额(元)
today = {'T': T, 'P': P, 'V': V, 'A': A, 'AMT': AMT, 'BU': BU, 'SU': SU, 'nAuc': len(au_pts)}

# ---------- 历史 trends：竞价段抽稀 + 补 nAuc/累计成交额/BU/SU ----------
for dt, tr in trends.items():
    au = tr.get('AU', [])
    au_t = thin_au(au)
    n0, n1 = len(au), len(au_t)
    if n1 < n0:  # 用抽稀后的竞价段重建 T/P/V/BU/SU
        tail = slice(n0, None)
        tr['T'] = [p[0] for p in au_t] + tr['T'][tail]
        tr['P'] = [p[1] for p in au_t] + tr['P'][tail]
        tr['V'] = [p[2] for p in au_t] + tr['V'][tail]
        tr['BU'] = [p[3] for p in au_t] + tr['BU'][tail]
        tr['SU'] = [p[4] for p in au_t] + tr['SU'][tail]
        tr['A'] = [None]*n1 + tr['A'][tail]
    tr['nAuc'] = n1
    if 'BU' not in tr:
        tr['BU'] = [0]*len(tr['V'])
        tr['SU'] = [0]*len(tr['V'])
    # 累计成交额：均价×累计量（竞价段无均价→None）
    tr['AMT'] = [(tr['A'][i]*tr['V'][i] if tr['A'][i] is not None else None)
                 for i in range(len(tr['V']))]

prev_close = float(dep['昨收价'])
bids = [[float(dep[f'买{i}价']), int(dep[f'买{i}量'])] for i in range(1, 6)]
asks = [[float(dep[f'卖{i}价']), int(dep[f'卖{i}量'])] for i in range(1, 6)]

# ---------- 关键数据（汇总接口 + 问财） ----------
with THS() as ths:
    rk = ths.market_data_cn(CODE, '汇总')
    rowk = rk.df.iloc[0]
    # 实际换手率（自由流通口径）
    try:
        rw = ths.wencai_nlp(f'{NAME}实际换手率')
        if not rw.df.empty:
            real_turnover = float(rw.df.iloc[0][rw.df.columns[0]])
        else:
            real_turnover = float(rowk['换手率'])
    except Exception:
        real_turnover = float(rowk['换手率'])

def fmt_wan(x):
    return f"{x/1e6:.1f}万手" if x >= 1e6 else f"{x/1e4:.0f}万"

key = {
    '涨幅': f"{float(rowk['涨幅']):+.2f}%",
    '换手': f"{float(rowk['换手率']):.2f}%",
    '换手实': f"{real_turnover:.2f}%",
    '成交量': fmt_wan(float(rowk['成交量'])),
    '成交额': f"{float(rowk['总金额'])/1e8:.2f}亿",
    '总市值': f"{float(rowk['总市值'])/1e8:.2f}亿",
    '自由流通': f"{float(rowk['流通市值'])/1e8:.2f}亿",
    '行业': INDUSTRY or '',
}
# 市盈率TTM：2147483648 为无效值（游客权限），显示 --
pe = float(rowk['市盈率TTM'])
key['市盈动'] = '--' if pe > 1e9 else f"{pe:.2f}"
key['市净'] = f"{float(quote_df['市净率1']):.2f}"

# 名称（未传参时从汇总接口取）
name_final = NAME or str(rowk.get('名称', ''))

data = {'name': name_final, 'code': CODE6,
        'dates': dates, 'ohlc': ohlc, 'vols': vols, 'amts': [f"{a/1e8:.2f}亿" for a in recent['总金额']],
        'ma5': ma5, 'ma10': ma10, 'ma20': ma20,
        'prevClose': prev_close, 'today': today, 'trends': trends,
        'bids': bids, 'asks': asks,
        'quote': {'现价': round(float(intr['价格'].iloc[-1]),2), '涨跌': round(float(intr['价格'].iloc[-1])-prev_close,2),
                  '涨跌幅': round((float(intr['价格'].iloc[-1])-prev_close)/prev_close*100,2),
                  '成交额': f"{float(day.iloc[-1]['总金额'])/1e8:.2f}亿",
                  '量比': round(float(quote_df['量比']),2),
                  '换手率': round(float(quote_df['换手率']),2),
                  '主力净流入': round(float(quote_df['主力净流入'])/1e4,0)},
        'auc': {'price': round(float(auc['价格'].iloc[-1]),2), 'vol': int(auc['当前量'].iloc[-1]),
                'amt': f"{float(intr['总金额'].iloc[0])/1e4:.0f}万",
                'yestAmt': f"{float(day.iloc[-2]['总金额'])/1e8:.2f}亿",
                'freeFloat': f"{float(rowk['流通市值'])/1e8:.2f}亿"},
        'key': key}

with open('page_data.js', 'w', encoding='utf-8') as f:
    f.write('var PAGE_DATA=' + json.dumps(data, ensure_ascii=False) + ';')
print('page_data.js:', round(os.path.getsize('page_data.js')/1024), 'KB, 今日竞价点:', len(au_pts))

# ---------- 组装 HTML ----------
if os.path.exists(TEMPLATE):
    html = open(TEMPLATE, encoding='utf-8').read()
    import datetime
    today_str = datetime.date.today().strftime('%Y年%m月%d日')
    mkt_tag = {'USHA': '沪A', 'USZA': '深A', 'USTM': '北A'}.get(MARKET, 'A股')
    html = html.replace('{NAME}', name_final).replace('{CODE}', CODE6)\
               .replace('{INDUSTRY}', INDUSTRY or '沪深A股').replace('{DATE}', today_str)\
               .replace('沪深A ·', mkt_tag + ' ·')
    html = html.replace("page_data.js?v=0", "page_data.js?v=1")
    with open('行情版面.html', 'w', encoding='utf-8') as f:
        f.write(html)
    print('行情版面.html 已生成')

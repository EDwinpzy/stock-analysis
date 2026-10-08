# -*- coding: utf-8 -*-
"""拉取近一年(250交易日)每日分时：竞价段(9:15-9:25秒级) + 盘中(9:30-15:00分钟级)
用法: python fetch_trends.py <代码6位>    约4-6分钟，建议后台运行
输出: trends.json  { 'YYYYMMDD': {T,P,V,A,AU}, ... }
"""
import sys, json, time
import pandas as pd
from thsdk import THS

CODE6 = sys.argv[1] if len(sys.argv) > 1 else '600410'
MARKET = 'USHA' if CODE6.startswith('6') else ('USZA' if CODE6.startswith(('0', '3')) else 'USTM')
CODE = MARKET + CODE6

day = pd.read_csv('day_kline.csv', parse_dates=['时间'])
dates = [d.strftime('%Y%m%d') for d in day.tail(250)['时间']]

def to_ts(s):
    return pd.to_datetime(s, unit='s', utc=True).dt.tz_convert('Asia/Shanghai')

trends = {}
with THS() as ths:
    for i, dt in enumerate(dates):
        try:
            # 1) 盘中分时（分钟级）
            r = ths.min_snapshot(CODE, date=dt)
            df = r.df
            if df.empty:
                continue
            # 2) 竞价段（秒级 tick，取 9:15-9:25）
            # AU 每点: [time, 匹配价, 匹配量, 买未匹配量, 卖未匹配量]
            auction_pts = []
            try:
                r2 = ths.tick_super_level1(CODE, date=dt)
                t2 = to_ts(r2.df['时间'])
                p2 = pd.to_numeric(r2.df['价格'], errors='coerce')
                v2 = pd.to_numeric(r2.df['当前量'], errors='coerce')
                b2 = pd.to_numeric(r2.df.get('买2量'), errors='coerce')
                s2 = pd.to_numeric(r2.df.get('卖2量'), errors='coerce')
                # 坑：首行可能是脏数据(1970/2038时间戳)，必须用请求日期精确匹配
                mask = ((t2.dt.strftime('%Y%m%d') == dt) &
                        ((t2.dt.hour == 9) & (t2.dt.minute < 25)) &
                        p2.notna())
                INVALID = 2147483648  # 未匹配量无效哨兵值
                for t_, p_, v_, bu_, su_ in zip(t2[mask], p2[mask], v2[mask], b2[mask], s2[mask]):
                    bu = int(bu_) if pd.notna(bu_) and bu_ < INVALID else 0
                    su = int(su_) if pd.notna(su_) and su_ < INVALID else 0
                    auction_pts.append([t_.strftime('%H:%M:%S'), round(float(p_), 2),
                                        int(v_) if pd.notna(v_) else 0, bu, su])
            except Exception as e:
                print(f'{dt} 竞价段失败: {e}')
            # 合并：竞价段 + 盘中分钟（盘中无未匹配量，恒0）
            tt = to_ts(df['时间'])
            T = [p[0] for p in auction_pts] + tt.dt.strftime('%H:%M').tolist()
            P = [p[1] for p in auction_pts] + [round(float(x), 2) for x in df['价格']]
            V = [p[2] for p in auction_pts] + [int(x) for x in df['成交量']]
            BU = [p[3] for p in auction_pts] + [0]*len(df)
            SU = [p[4] for p in auction_pts] + [0]*len(df)
            A = [None]*len(auction_pts) + [round(float(df['价格'].iloc[0]), 2)]
            for j in range(1, len(V) - len(auction_pts)):
                v = V[len(auction_pts)+j]
                amt = float(df['总金额'].iloc[j])
                A.append(round(amt/v, 2) if v else P[len(auction_pts)+j])
            trends[dt] = {'T': T, 'P': P, 'V': V, 'A': A, 'BU': BU, 'SU': SU, 'AU': auction_pts}
        except Exception as e:
            print(f'{dt} 失败: {e}')
        if (i+1) % 50 == 0:
            print(f'进度 {i+1}/{len(dates)}')
        time.sleep(0.2)

with open('trends.json', 'w', encoding='utf-8') as f:
    json.dump(trends, f, ensure_ascii=False)
print('完成，共', len(trends), '个交易日')

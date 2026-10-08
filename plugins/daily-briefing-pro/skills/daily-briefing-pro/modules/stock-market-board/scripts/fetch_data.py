# -*- coding: utf-8 -*-
"""拉取个股全部基础数据：历史日K/今日分时/竞价/盘口/行情
用法: python fetch_data.py <代码6位> <股票名称>   (代码6位: 600410)
输出: day_kline.csv / intraday.csv / depth.csv / auction.csv / quote.csv
"""
import sys, time
from datetime import datetime
from zoneinfo import ZoneInfo
import pandas as pd
from thsdk import THS

CODE6 = sys.argv[1] if len(sys.argv) > 1 else '600410'
NAME = sys.argv[2] if len(sys.argv) > 2 else ''
MARKET = 'USHA' if CODE6.startswith('6') else ('USZA' if CODE6.startswith(('0', '3')) else 'USTM')
CODE = MARKET + CODE6

tz = ZoneInfo('Asia/Shanghai')
with THS() as ths:
    # 1. 全部历史日K（前复权）
    resp = ths.klines(CODE, interval='day',
                      start_time=datetime(1990, 1, 1, tzinfo=tz),
                      end_time=datetime(2026, 12, 31, tzinfo=tz), adjust='forward')
    resp.df.to_csv('day_kline.csv', index=False, encoding='utf-8-sig')
    print('日K:', len(resp.df), '根')

    # 2. 今日分时
    r2 = ths.intraday_data(CODE)
    r2.df.to_csv('intraday.csv', index=False, encoding='utf-8-sig')
    print('分时:', len(r2.df), '条')

    # 3. 五档盘口
    r3 = ths.depth(CODE)
    r3.df.to_csv('depth.csv', index=False, encoding='utf-8-sig')
    print('盘口:', len(r3.df), '行')

    # 4. 集合竞价（9:15-9:25 秒级）
    r4 = ths.call_auction(CODE)
    r4.df.to_csv('auction.csv', index=False, encoding='utf-8-sig')
    print('竞价:', len(r4.df), '条')

    # 5. 实时行情（扩展1：量比/换手/市净/主力净流入）
    r5 = ths.market_data_cn(CODE, '扩展1')
    r5.df.to_csv('quote.csv', index=False, encoding='utf-8-sig')
    print('行情:', r5.df.to_dict('records'))
print('DONE')

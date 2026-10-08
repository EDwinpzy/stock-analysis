#!/usr/bin/env python3
"""尝试从 aweme_id 解析发布时间"""
from datetime import datetime, timezone, timedelta

aweme_ids = [
    "7659870209783952070",
    "7659867898538110655",
    "7659773511329896319",
    "7659697634370827883",
    "7659395780729385572",
    "7659301513521145343",
    "7659015583938369215",
    "7658974394269669297",
    "7654802871703547045",  # 福总最新的
    "7648873308021157989",
]

epochs_ms = [
    ("Twitter", 1288834974657),
    ("Discord", 1609459200000),
    ("2018-01-01", 1514764800000),
    ("2018-02-01", 1517443200000),
    ("2016-09-20", 1474329600000),
    ("2020-01-01", 1577836800000),
    ("2021-01-01", 1609430400000),
]


def fmt(ts_ms):
    if ts_ms <= 0:
        return "invalid"
    try:
        dt = datetime.fromtimestamp(ts_ms / 1000, tz=timezone(timedelta(hours=8)))
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception as e:
        return str(e)


print("测试 aweme_id 右移22位 + 各 epoch\n")
for name, epoch in epochs_ms:
    print(f"--- epoch: {name} ({epoch}) ---")
    for aid in aweme_ids:
        try:
            ts = (int(aid) >> 22) + epoch
            print(f"  {aid} -> {fmt(ts)}")
        except Exception as e:
            print(f"  {aid} -> error: {e}")
    print()

# 也测试其他位移
print("\n测试不同右移位 + epoch 1609459200000 (Discord):")
for shift in [20, 21, 22, 23, 24, 25]:
    print(f"--- 右移 {shift} 位 ---")
    for aid in aweme_ids[:3]:
        ts = (int(aid) >> shift) + 1609459200000
        print(f"  {aid} -> {fmt(ts)}")
    print()

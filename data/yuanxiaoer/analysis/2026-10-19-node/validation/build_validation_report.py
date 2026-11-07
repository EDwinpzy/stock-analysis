"""Create the readable evidence report and perform targeted consistency checks."""
import csv
import datetime as dt
import hashlib
import json
import statistics
from pathlib import Path
import sys
sys.stdout.reconfigure(encoding='utf-8')
ROOT=Path(__file__).resolve().parent
TZ=dt.timezone(dt.timedelta(hours=8))
TARGET_DAYS=['2026-09-24','2026-09-28','2026-10-12','2026-10-15','2026-10-16','2026-10-19']
def day(row):return dt.datetime.fromtimestamp(row['date_ms']/1000,TZ).date().isoformat()
def show(x):return '未到期/缺失' if x is None else f'{x:+.2f}%'
def write_csv(name,rows):
    with (ROOT/name).open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)

def main():
    outcomes=json.loads((ROOT/'candidate_outcomes.json').read_text(encoding='utf-8'))
    stats=json.loads((ROOT/'cohort_stats.json').read_text(encoding='utf-8'))
    index=json.loads((ROOT/'calendar_index.json').read_text(encoding='utf-8'))['data']['item']
    market=[]
    for i,r in enumerate(index):
        if day(r) not in TARGET_DAYS:continue
        prev=index[i-1]
        market.append({'date':day(r),'close':r['close_price'],'pct':(r['close_price']/prev['close_price']-1)*100,'volume_shares':r['volume'],'volume_change_pct':(r['volume']/prev['volume']-1)*100,'turnover_yuan':r['turnover'],'turnover_change_pct':(r['turnover']/prev['turnover']-1)*100})
    write_csv('index_evidence.csv',market)
    case=[]
    for code in ['600127.SH','601086.SH','600664.SH','002242.SZ','600241.SH','002085.SZ','603197.SH','001318.SZ','002696.SZ','603186.SH','600825.SH','601811.SH']:
        j=json.loads((ROOT/'prices'/f'{code}.json').read_text(encoding='utf-8'));a=j['data']['item']
        for i,r in enumerate(a):
            if day(r) not in TARGET_DAYS:continue
            case.append({'date':day(r),'code':code,'name':j['requested_name'],'open':r['open_price'],'high':r['high_price'],'low':r['low_price'],'close':r['close_price'],'pct':(r['close_price']/a[i-1]['close_price']-1)*100 if i else None,'previous_observed_bar':day(a[i-1]) if i else None,'volume_shares':r['volume'],'turnover_yuan':r['turnover']})
    write_csv('case_evidence.csv',case)
    # Real data quality checks, not synthetic implementation-mirroring tests.
    assert len([r for r in outcomes if r['signal_day']=='2026-09-28'])==31
    nonst=[r for r in outcomes if r['signal_day']=='2026-09-28' and not r['is_st'] and not r['is_new']]
    assert len(nonst)==29
    assert {r['name'] for r in nonst if r['continuous_run_peak_by_1019']>=6}=={'九阳股份','时代万恒'}
    assert next(r for r in nonst if r['name']=='时代万恒')['entry_one_price']
    assert not next(r for r in nonst if r['name']=='九阳股份')['entry_open_at_limit']
    assert all(r['exit_day_T10']=='2026-10-19' for r in nonst)
    for f in (ROOT/'prices').glob('*.json'):
        j=json.loads(f.read_text(encoding='utf-8'));a=j['data'].get('item',[])
        assert j['ok'] and all(day(r)<='2026-10-19' for r in a)
        assert len({day(r) for r in a})==len(a)
        assert all(r['low_price']<=min(r['open_price'],r['close_price'])<=max(r['open_price'],r['close_price'])<=r['high_price'] for r in a)
    for f in (ROOT/'pools').glob('*.json'):
        j=json.loads(f.read_text(encoding='utf-8'))
        assert j['count']==len(j['items'])==len({r['thscode'] for r in j['items']})
        assert all(e.get('ok') for e in j['envelopes'])
    checked=dt.datetime.now(TZ).isoformat()
    s=['# 节点票实际数据验证（2026-10-19）',f'\n核验时间：{checked}。价格/涨停池截止：2026-10-19收盘。数据源：同花顺 hithink-finance 0.1.12 remote；OHLC均未复权。',
       '\n本报告只验证可由日线、涨停池直接核对的事实。节点日期由本次语料人工选取，9/24、9/28、9/29是人工挑选的描述性样本，不能当成随机对照或独立周期回测。未读取任何10/19之后的数据，未为了结果调整数值阈值。',
       '\n## 统一价格与成交口径',
       '\n信号T日收盘后才能确认；次一市场交易日T+1开盘为参考入价。T+3/5/10分别在T后的第3/5/10个市场交易日收盘退出，包含入场日。例：9/28信号→9/29开盘→10/8、10/12、10/19收盘。每笔10万元，买卖佣金0.025%且最低5元、过户费双边0.001%、印花税卖出0.05%。每只等权独立交易，不是组合资金曲线。',
       '\n主表排除ST、新股及次日开盘价达到涨停价的票；整日一字排除口径作为敏感性。无法由日线证明剩余股票的集合竞价排队成交、实际滑点和跌停收盘卖出成功，故这里是保守参考价格情景，不能称真实成交回测。T+1开盘至T+1收盘只算浮动盈亏，受A股T+1制度限制，不作为可交易收益。',
       '\n## 本期全体候选分母',
       '\n9/28涨停池35只，其中首板28只、二板3只，共31只低位候选；剔除2只ST后29只。29只中8只次日继续涨停，5只在本段连续走到至少3板，2只到6板。九阳/时代只是29只中的2只（6.9%），不能用两只事后赢家代替全体胜率。',
       '\n|信号日|全部首/二板|非ST/新股|排次日开盘涨停后|T+3净均值 / 中位数 / 胜率|T+5净均值 / 中位数 / 胜率|T+10净均值 / 中位数 / 胜率|',
       '|---|---:|---:|---:|---|---|---|']
    for d in ['2026-09-24','2026-09-28','2026-09-29','2026-10-16']:
        allr=[r for r in outcomes if r['signal_day']==d];ns=[r for r in allr if not r['is_st'] and not r['is_new']];eligible=[r for r in ns if not r['entry_open_at_limit']]
        vals=[]
        for h in [3,5,10]:
            v=[r[f'net_pct_T{h}'] for r in eligible if r[f'net_pct_T{h}'] is not None]
            vals.append(f'{statistics.mean(v):+.2f}% / {statistics.median(v):+.2f}% / {sum(x>0 for x in v)/len(v)*100:.1f}% (n={len(v)})' if v else '未到期')
        s.append(f'|{d}|{len(allr)}|{len(ns)}|{len(eligible)}|'+'|'.join(vals)+'|')
    s.extend(['\n9/29筛后46只中路畅科技缺少T+1开盘数据，收益分母45只。10/16信号截至10/19仅过一个交易日，无法验证T+3/5/10；56只候选11只晋级，其中5只10/19整日一字。',
              '\n敏感性：9/28仅排除整日一字时27只，T+3净均值+2.30%、中位-2.36%、胜率33.3%；T+5 +2.38%、中位-3.62%、胜率33.3%；T+10 -1.56%、中位-6.86%、胜率29.6%。正均值由少数强票抬高；主表更严格的开盘涨停排除口径不改变多数样本亏损的事实。',
              '\n不能给“策略已显著有效”的置信区间：几个信号日共享同一市场冲击，同一天的29只票不能当29个独立节点周期；还缺跨周期、事前固定的节点事件定义和同股同期随机/非节点配对。',
              '\n## 9/28全部非ST候选（赢家与失败票同表）',
              '\n连续最高板只统计从信号日起不间断的本段，截止10/19；后续最高只作结果，不参与入选。收益为未因开盘涨停排除前的理论参考，列“开盘涨停”者不得纳入主表。',
              '\n|股票|T日板数/首封|本段最高|T+1开盘|开盘涨停|T+3净|T+5净|T+10净|',
              '|---|---|---:|---:|---|---:|---:|---:|'])
    for r in sorted(nonst,key=lambda r:(-r['continuous_run_peak_by_1019'],r['first_seal'])):
        s.append(f"|{r['name']} {r['code']}|{r['signal_streak']} / {r['first_seal']}|{r['continuous_run_peak_by_1019']}|{r['entry_open']}|{'是（一字）' if r['entry_one_price'] else ('是' if r['entry_open_at_limit'] else '否')}|{show(r['net_pct_T3'])}|{show(r['net_pct_T5'])}|{show(r['net_pct_T10'])}|")
    s.extend(['\n## 上证指数证据', '\n成交量、成交额为上证指数接口自身口径，不代表两市成交额。涨跌幅及量额变化均较前一个市场交易日。', '\n|日期|收盘|涨跌幅|成交量（亿股）|量较前日|成交额（亿元）|额较前日|','|---|---:|---:|---:|---:|---:|---:|'])
    for r in market:s.append(f"|{r['date']}|{r['close']:.2f}|{r['pct']:+.2f}%|{r['volume_shares']/1e8:.2f}|{r['volume_change_pct']:+.2f}%|{r['turnover_yuan']/1e8:.2f}|{r['turnover_change_pct']:+.2f}%|")
    s.extend(['\n10/15日内低点3674.82、收盘3707.48，存在从低点回升，但全日仍下跌，不能把“探底回升”写成收涨。10/19收涨但上证指数自身成交量/额较10/16均缩小，不能据此声称已满足“指数放量回暖”，两市口径仍需另核。',
              '\n## 关键股票明确数值', '\n|日期|股票|开/高/低/收|较前有效K线收盘涨跌|', '|---|---|---|---:|'])
    for r in case:s.append(f"|{r['date']}|{r['name']} {r['code']}|{r['open']:.2f} / {r['high']:.2f} / {r['low']:.2f} / {r['close']:.2f}|{show(r['pct'])}|")
    s.extend(['\n## 可验证事实与未验证条件',
              '\n- 9/24金健高17.05、收16.49，国芳/哈药分别收跌9.99%/9.96%；9/28九阳与时代均首板，随后连续6板到10/12。支持“旧核心负反馈后出现低位新领涨”的个案时间关系，未证明完整因果或可预测性。',
              '- 10/12九阳开16.64/低14.85/收16.64，时代开12.48/低12.13/收12.94，日内有波动后收板；日线无法核验分时反复卡位、买盘主动性与换手承接质量。',
              '- 10/19时代跌停-9.96%，九阳+5.06%，即使同日启动、同样六连板也不能保证同时穿越。阳光/百洋10/16和10/19连续跌停，符合风险条件被触发的价格事实。',
              '- 10/16万丰首板09:44、保隆首板09:30，10/19均晋级二板；保隆10/19整日一字，不能按32.33假设所有人可买；万丰10/19开10.89/收10.90，后续持有结果尚未来。',
              '- 华正新材10/19收186.74、跌1.71%，不是涨停。',
              '- 首封时间只适合比较同组主动性，不能强设“09:40前”硬门槛：九阳09:31、时代10:08均六板；最早的博纳影业09:25当天首板却未连续晋级；善水13:47后续三板。封单大小、封板时间也不是充分条件。',
              '- 板块跟随、盘中弱转强、异动监管和两市放量确认不在本次日线完整验证范围。没有为这些条件编造阈值。',
              '\n## 对旧回测数字的审计',
              '\n旧《节点规则回测验证》的+3.00%、旧《全市场终版》的+1.83%使用信号日收盘入场，后续已修正；-0.21%/-0.56pp只是历史文档结论，本次未找到其5221只原始baostock目录，未重新复现。当前 scripts/rules.py 的 nodemark 定义为“任意≥3连板股断板日的首/二板”，不等于昨日真实龙头或作者的整套节点判定。不能拿它直接否定本次完整条件。',
              '\n另有可复现代码窗口问题：ashare_backtest.net_return(entry="next",hold=3)用ei=i+1、si=ei+hold，实际退出T+4，而market_return(3)用T至T+3收盘，时间错位；日线推导也未严格处理ST、停复牌、涨跌停价及可成交性。本次没有沿用旧脚本收益。',
              '\n新华传媒代码为600825（002264新华都是连通性探针，未纳入任何对照）。新华传媒10/13—15无K线及涨停池记录属于停牌，不得判作断板；10/16复牌11板。文轩为新华文轩601811：9/24五板、9/28断板-8.99%，和新华传媒不同。停牌公告由主任务另核： https://static.cninfo.com.cn/finalpage/2026-10-16/1225607741.PDF 。',
              '\n## 复现与检查', '\n运行 fetch_validation_data.py、validate_cohorts.py、build_validation_report.py。原始行情 prices/、涨停池 pools/、完整逐票结果 candidate_outcomes.csv、汇总 cohort_stats.json、指数表 index_evidence.csv、案例表 case_evidence.csv 均在此目录。仅该分析目录有写入，不修改采集状态、历史成功边界、安装缓存或共享插件。',
              f'\n数据检查通过：175份个股价格响应、16日全量涨停池；OHLC区间关系、日期唯一、无10/19之后价格、池记录ID去重、31/29候选分母、九阳/时代六板与时代次日一字均核对。检查时间：{checked}。'])
    (ROOT/'validation_report.md').write_text('\n'.join(s),encoding='utf-8')
    manifest={'checked_at':checked,'data_cutoff':'2026-10-19','price_files':len(list((ROOT/'prices').glob('*.json'))),'pool_days':len(list((ROOT/'pools').glob('*.json'))),'checks':'passed','files':{str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for sub in ['prices','pools'] for f in sorted((ROOT/sub).glob('*.json'))}}
    (ROOT/'validation_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    print('PASS',json.dumps({k:v for k,v in manifest.items() if k!='files'},ensure_ascii=False))
    print('\n'.join(s[0:8]));print(market)

if __name__=='__main__':main()

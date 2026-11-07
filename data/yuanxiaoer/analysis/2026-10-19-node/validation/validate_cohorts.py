"""Descriptive, time-stamped evidence; no fitted parameters or success-state writes."""
import concurrent.futures
import csv
import datetime as dt
import json
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
import sys

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0,str(Path(__file__).resolve().parent))
from fetch_validation_data import ROOT,TZ,cli,stamp

SIGNAL_DAYS=['2026-09-24','2026-09-28','2026-09-29','2026-10-16']

def pool(day):
    return json.loads((ROOT/'pools'/f'{day}.json').read_text(encoding='utf-8'))['items']

def fetch(kv):
    code,name=kv
    path=ROOT/'prices'/f'{code}.json'
    if not path.exists():
        j=cli(['market','history','--thscode',code,'--start-ms',stamp('2026-09-01'),'--end-ms',stamp('2026-10-20'),'--adjust','none'])
        j.update(requested_code=code,requested_name=name,adjust='none')
        path.write_text(json.dumps(j,ensure_ascii=False,indent=2),encoding='utf-8')
    return code

def main():
    stocks={x['thscode']:x['name'] for d in SIGNAL_DAYS for x in pool(d) if x['continue_day_cnt'] in (1,2)}
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex: list(ex.map(fetch,stocks.items()))
    allp={}
    for f in (ROOT/'pools').glob('*.json'):
        j=json.loads(f.read_text(encoding='utf-8'));allp[j['date']]=j['items']
    days=sorted(allp)
    rows=[]
    for day in SIGNAL_DAYS:
        di=days.index(day)
        for item in pool(day):
            if item['continue_day_cnt'] not in (1,2):continue
            code=item['thscode']
            j=json.loads((ROOT/'prices'/f'{code}.json').read_text(encoding='utf-8'))
            prices={dt.datetime.fromtimestamp(r['date_ms']/1000,TZ).date().isoformat():r for r in j['data'].get('item',[])}
            r={'signal_day':day,'code':code,'name':item['name'],'is_st':bool(item.get('is_st')),'is_new':bool(item.get('is_new')),'signal_streak':item['continue_day_cnt'],'first_seal':item['limit_up_time'],'seal_money':item['seal_money'],'reason':item['limit_up_reason']}
            current=prices.get(day)
            nextday=days[di+1] if di+1<len(days) else None
            nxt=prices.get(nextday)
            r['entry_day']=nextday
            r['entry_open']=nxt['open_price'] if nxt else None
            r['next_day_limit_up']=any(x['thscode']==code for x in allp.get(nextday,[]))
            r['next_day_streak']=next((x['continue_day_cnt'] for x in allp.get(nextday,[]) if x['thscode']==code),0)
            # Exclude only observed one-price bars; also flag open-at-limit separately.
            r['entry_one_price']=bool(nxt and nxt['open_price']==nxt['high_price']==nxt['low_price']==nxt['close_price'])
            lim=Decimal('1.20') if code.startswith(('30','68')) else Decimal('1.10')
            upper=float((Decimal(str(current['close_price']))*lim).quantize(Decimal('.01'),rounding=ROUND_HALF_UP)) if current else None
            r['entry_open_at_limit']=bool(nxt and upper and abs(nxt['open_price']-upper)<0.005)
            run=item['continue_day_cnt']
            for future in days[di+1:]:
                q=next((x for x in allp[future] if x['thscode']==code),None)
                if q and q['continue_day_cnt']==run+1:run+=1
                else:break
            r['continuous_run_peak_by_1019']=run
            for h in [1,3,5,10]:
                exitday=days[di+h] if di+h<len(days) else None
                exitbar=prices.get(exitday)
                r[f'exit_day_T{h}']=exitday
                r[f'exit_close_T{h}']=exitbar['close_price'] if exitbar else None
                ret=(exitbar['close_price']/nxt['open_price']-1)*100 if exitbar and nxt and nxt['open_price']>0 else None
                # T+1 open to T+1 close is an intraday mark, NOT a permitted
                # round trip in the A-share T+1 settlement system.
                r[f'gross_pct_T{h}']=ret
                if ret is not None:
                    capital=100000
                    sell=capital*(1+ret/100)
                    r[f'net_pct_T{h}']=((sell-max(sell*.00025,5)-sell*.00051)/(capital+max(capital*.00025,5)+capital*.00001)-1)*100
                else:r[f'net_pct_T{h}']=None
            rows.append(r)
    with (ROOT/'candidate_outcomes.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    (ROOT/'candidate_outcomes.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
    stats=[]
    for day in SIGNAL_DAYS:
        cohort=[r for r in rows if r['signal_day']==day]
        nonst=[r for r in cohort if not r['is_st'] and not r['is_new']]
        for label,eligible in [('all',cohort),('nonst',nonst),('nonst_exclude_one_price',[r for r in nonst if not r['entry_one_price']]),('nonst_exclude_open_at_limit',[r for r in nonst if not r['entry_open_at_limit']])]:
            s={'day':day,'filter':label,'n':len(eligible),'next_day_limit_up':sum(r['next_day_limit_up'] for r in eligible),'peak_ge3':sum(r['continuous_run_peak_by_1019']>=3 for r in eligible),'peak_ge6':sum(r['continuous_run_peak_by_1019']>=6 for r in eligible)}
            for h in [1,3,5,10]:
                vals=[r[f'net_pct_T{h}'] for r in eligible if r[f'net_pct_T{h}'] is not None]
                s[f'n_T{h}']=len(vals);s[f'mean_net_T{h}']=sum(vals)/len(vals) if vals else None;s[f'win_pct_T{h}']=sum(x>0 for x in vals)/len(vals)*100 if vals else None
            stats.append(s)
    (ROOT/'cohort_stats.json').write_text(json.dumps(stats,ensure_ascii=False,indent=2),encoding='utf-8')
    for s in stats:print(json.dumps(s,ensure_ascii=False))

if __name__=='__main__':main()

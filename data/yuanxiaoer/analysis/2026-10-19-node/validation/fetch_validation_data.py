"""Fetch read-only market evidence into this analysis folder only."""
import concurrent.futures
import datetime as dt
import json
import pathlib
import subprocess
import sys

sys.stdout.reconfigure(encoding='utf-8')
ROOT = pathlib.Path(__file__).resolve().parent
TZ = dt.timezone(dt.timedelta(hours=8))

def stamp(day):
    return str(int(dt.datetime.fromisoformat(day).replace(tzinfo=TZ).timestamp() * 1000))

def cli(args):
    p = subprocess.run(['cmd', '/c', 'hithink-finance', *args, '--format', 'json'], capture_output=True)
    j = json.loads(p.stdout.decode('utf-8-sig'))
    if not j.get('ok'):
        raise RuntimeError(str(j.get('error')))
    return j

def fetch_pool(day):
    items=[]
    page=1
    envelopes=[]
    while True:
        j=cli(['special','limit-up-pool','--date-ms',stamp(day),'--page',str(page),'--size','200'])
        envelopes.append(j)
        data=j['data']
        items.extend(data.get('item') or [])
        if page >= int((data.get('pagination') or {}).get('pages') or 1): break
        page+=1
    out={'date':day,'count':len(items),'items':items,'source':'hithink-finance special.limit-up-pool','fetched_at':dt.datetime.now(TZ).isoformat(),'envelopes':envelopes}
    (ROOT/'pools').mkdir(exist_ok=True)
    (ROOT/'pools'/f'{day}.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
    return day,len(items)

if __name__=='__main__':
    j=cli(['index','history','--thscode','000001.SH','--start-ms',stamp('2026-09-18'),'--end-ms',stamp('2026-10-20')])
    (ROOT/'calendar_index.json').write_text(json.dumps(j,ensure_ascii=False,indent=2),encoding='utf-8')
    days=[]
    for row in j['data'].get('item',[]):
        raw=row.get('date_ms')
        if raw: days.append(dt.datetime.fromtimestamp(raw/1000,TZ).date().isoformat())
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
        for result in ex.map(fetch_pool, sorted(set(days))): print(result)

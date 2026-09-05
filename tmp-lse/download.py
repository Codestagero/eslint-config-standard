"""Read-only index research downloader. Credential from environment, never saved."""
import os,json,time,pathlib,hashlib,datetime as dt,threading,concurrent.futures
import requests,pandas as pd
OUT=pathlib.Path('market-data');OUT.mkdir(exist_ok=True)
BASE='https://api.londonstrategicedge.com/vault';KEY=os.environ['LSE_API_KEY']
lock=threading.Lock();last=[0.0];audit=[]
def get(path,params=None):
    for retry in range(8):
        with lock:
            time.sleep(max(0,.45-(time.monotonic()-last[0])));last[0]=time.monotonic()
        r=requests.get(BASE+path,params=params,headers={'x-api-key':KEY,'User-Agent':'lse-data-sdk fixed-index-strategy-research'},timeout=100)
        with lock:audit.append({'path':path,'params':params,'status':r.status_code,'bytes':len(r.content)})
        if r.status_code==429:
            time.sleep(float(r.headers.get('Retry-After',30)));continue
        if r.status_code>=500:time.sleep(3*(retry+1));continue
        if r.status_code in [401,402,403]:raise RuntimeError('Access or quota denied: '+str(r.status_code))
        r.raise_for_status();return r.json()
    raise RuntimeError('Repeated request failures '+path)
cat=get('/catalog');ind=[x for x in cat if x['dataset']=='index']
(OUT/'index_catalog.json').write_text(json.dumps(ind,indent=2))
(OUT/'usage_before.json').write_text(json.dumps(get('/usage'),indent=2))
for path,params,name in [('/preview',{'dataset':'index','symbol':'DE30/EUR','limit':5},'tick_preview_DE30'),('/candles',{'dataset':'index','symbol':'DE30/EUR','timeframe':'1m','start':'2026-09-01','limit':5},'candle_preview_DE30')]:
    try:(OUT/(name+'.json')).write_text(json.dumps(get(path,params),indent=2))
    except Exception as e:(OUT/(name+'.json')).write_text(json.dumps({'error_type':type(e).__name__}))
def fetch_symbol(meta):
    sym=meta['symbol'];parts=[];cursor='2023-06-01T00:00:00';end='2026-09-05T00:00:00';pages=0
    while cursor<end:
        params={'dataset':'index','symbol':sym,'timeframe':'1m','start':cursor,'end':end,'order':'asc','limit':5000}
        rows=get('/candles',params)
        if not isinstance(rows,list):raise ValueError('Non-list candles for '+sym)
        if not rows:break
        frame=pd.DataFrame(rows);col='ts' if 'ts' in frame.columns else 'timestamp'
        dates=pd.to_datetime(frame[col],utc=True,format='mixed')
        if not dates.is_monotonic_increasing:raise ValueError('Unordered data '+sym)
        frame['timestamp_ms']=dates.astype('int64')//1000000 if dates.dtype.unit=='ns' else dates.as_unit('ms').astype('int64')
        parts.append(frame);new=(dates.max()+pd.Timedelta(microseconds=1)).strftime('%Y-%m-%dT%H:%M:%S.%f')
        if new<=cursor:raise ValueError('Pagination stalled '+sym)
        cursor=new;pages+=1
        if pages%35==0:print(sym,'pages',pages,'rows',sum(len(x) for x in parts),'through',cursor,flush=True)
        if pages>600:raise RuntimeError('Bounded request budget exceeded '+sym)
        if len(rows)<5000:break
    if not parts:return {'symbol':sym,'rows':0}
    f=pd.concat(parts,ignore_index=True);dups=int(f.timestamp_ms.duplicated().sum());f=f.drop_duplicates('timestamp_ms').sort_values('timestamp_ms')
    name=sym.replace('/','_')+'_1m.parquet';f.to_parquet(OUT/name,index=False)
    info={'symbol':sym,'rows':len(f),'pages':pages,'duplicates':dups,'first':str(pd.to_datetime(f.timestamp_ms.min(),unit='ms',utc=True)),'last':str(pd.to_datetime(f.timestamp_ms.max(),unit='ms',utc=True)),'columns':list(f.columns),'bytes':(OUT/name).stat().st_size,'sha256':hashlib.sha256((OUT/name).read_bytes()).hexdigest()}
    print('DONE',json.dumps(info),flush=True);return info
summaries=[]
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
    futures={pool.submit(fetch_symbol,m):m['symbol'] for m in ind}
    for task in concurrent.futures.as_completed(futures):
        sym=futures[task]
        try:summaries.append(task.result())
        except Exception as e:summaries.append({'symbol':sym,'error_type':type(e).__name__,'error':str(e).replace(KEY,'[REDACTED]')});print('FAILED',sym,type(e).__name__,flush=True)
        (OUT/'download_manifest.json').write_text(json.dumps(summaries,indent=2))
# Fetch public native venue instrument metadata to flag market availability; no private account calls.
try:
    r=requests.get('https://api.toobit.com/api/v1/exchangeInfo',timeout=40);r.raise_for_status()
    (OUT/'toobit_exchangeInfo.json').write_text(r.text)
except Exception as e:print('venue metadata',type(e).__name__,flush=True)
(OUT/'usage_after.json').write_text(json.dumps(get('/usage'),indent=2))
(OUT/'request_audit.json').write_text(json.dumps(audit))
print('COMPLETE symbols',len(summaries),'total rows',sum(x.get('rows',0) for x in summaries),flush=True)

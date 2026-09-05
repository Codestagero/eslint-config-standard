"""Credential stays in environment; private data and account endpoints are not used."""
import os,json,time,pathlib,hashlib,datetime as dt,concurrent.futures
import requests,numpy as np,pandas as pd
from lse_auth3 import read_repo
O=pathlib.Path('validation-data');O.mkdir(exist_ok=True);(O/'reference').mkdir(exist_ok=True)
KEY=os.environ['LSE_API_KEY'];BASE='https://api.londonstrategicedge.com/vault';H={'x-api-key':KEY,'User-Agent':'lse-data-sdk fixed-rule-market-validation'}
logs=[]
def request(url,**kw):
 for a in range(7):
  r=requests.get(url,timeout=100,**kw)
  if r.status_code==429:time.sleep(float(r.headers.get('Retry-After',10*(a+1))));continue
  if r.status_code>=500:time.sleep(3*(a+1));continue
  r.raise_for_status();time.sleep(.11);return r
 raise RuntimeError('Request budget exhausted')
def decode(p):
 if not p.get('times'):return None
 m=float(p['multiplier']);t=np.int64(p['timestamp'])+np.cumsum(p['times'],dtype=np.int64)*int(p['shift'])
 z={'timestamp_ms':t}
 for k in ['open','high','low','close']:z[k]=(round(p[k]/m)+np.cumsum(p[k+'s'],dtype=np.int64))*m
 return z
# Independent provider reference data. No LSE credential is sent to these hosts.
metaurl='https://raw.githubusercontent.com/Leo4815162342/dukascopy-node/master/src/utils/instrument-meta-data/generated/instrument-meta-data.json'
try:
 meta=request(metaurl).json();selected={k:v for k,v in meta.items() if '.IDX-' in v.get('code','')}
 (O/'reference/instrument_metadata.json').write_text(json.dumps(selected,indent=2))
 wanted=['deuidxeur','gbridxgbp','eusidxeur','fraidxeur','itaidxeur','espidxeur','cheidxchf','nldidxeur','usa500idxusd','usatechidxusd','usa30idxusd','usasc2000idxusd','jpnidxjpy','hkgidxhkd','ausidxaud','chiidxusd']
 for name in wanted:
  if name not in meta:continue
  code=meta[name]['code'];pieces=[]
  for y in range(2023,2027):
   url=f'https://jetta.dukascopy.com/v1/candles/day/{code}/BID/{y}'
   try:
    r=request(url);d=decode(r.json());logs.append({'source':'Dukascopy','url':url,'rows':0 if d is None else len(d['timestamp_ms'])})
    if d is not None:pieces.append(d)
   except Exception as e:logs.append({'source':'Dukascopy','url':url,'error':type(e).__name__})
  if pieces:np.savez_compressed(O/'reference'/f'{name}_daily.npz',**{k:np.concatenate([a[k] for a in pieces]) for k in pieces[0]})
  for date in ['2024-04-10','2025-09-01','2026-02-02','2026-05-04','2026-08-03']:
   day=dt.date.fromisoformat(date);url=f'https://jetta.dukascopy.com/v1/candles/minute/{code}/BID/{day.year}/{day.month}/{day.day}'
   try:
    r=request(url);d=decode(r.json())
    if d is not None:np.savez_compressed(O/'reference'/f'{name}_{date}_m1.npz',**d)
    logs.append({'source':'Dukascopy','url':url,'rows':0 if d is None else len(d['timestamp_ms'])})
   except Exception as e:logs.append({'source':'Dukascopy','url':url,'error':type(e).__name__})
  print('Independent reference',name,flush=True)
except Exception as e:logs.append({'source':'reference','error':str(e).replace(KEY,'[REDACTED]')})
usage=request(BASE+'/usage',headers=H).json();(O/'usage_before_ticks.json').write_text(json.dumps(usage,indent=2))
# Targets are research selections from train/validation only. Max three exports.
plan=json.loads(read_repo('tmp-lse/tick-targets.json',wait=1800));(O/'tick_plan.json').write_text(json.dumps(plan,indent=2))
targets=plan.get('symbols',[])[:3]
remaining=int(usage.get('exports_cap_hour',5))-int(usage.get('exports_this_hour',0));targets=targets[:max(remaining,0)]

def export(sym):
 result={'symbol':sym,'requested_start':'2026-03-01','requested_end':'2026-09-01'}
 try:
  body={'dataset':'index','symbol':sym,'timeframe':'tick','start':'2026-03-01','end':'2026-09-01','format':'parquet'}
  r=requests.post(BASE+'/export',json=body,headers=H,timeout=120)
  if r.status_code>=400:result['error']=r.text[:500].replace(KEY,'[REDACTED]');result['http_status']=r.status_code;return result
  job=r.json()['job_id'];result['job_id']=job;deadline=time.monotonic()+1500
  while True:
   info=request(BASE+'/export/'+job,headers=H).json()
   if info.get('status')=='ready':break
   if info.get('status') in ['failed','expired']:raise RuntimeError(str(info))
   if time.monotonic()>deadline:raise TimeoutError('Export did not complete in bounded wait')
   time.sleep(3)
  result['job_info']=info
  if int(info.get('bytes',0))>2_000_000_000:raise RuntimeError('Export exceeds local 2GB safety budget')
  path=O/(sym.replace('/','_')+'_ticks.parquet');r=request(BASE+'/export/'+job+'/download',headers=H,stream=True)
  with path.open('wb') as f:
   for block in r.iter_content(1024*1024):f.write(block)
  if info.get('bytes') and path.stat().st_size!=int(info['bytes']):raise RuntimeError('Export byte count mismatch')
  f=pd.read_parquet(path);result['columns']=list(f.columns);result['rows']=len(f);result['sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
  if len(f):
   tc=next(k for k in ['ts','timestamp','datetime','time'] if k in f)
   if pd.api.types.is_numeric_dtype(f[tc]):
    value=float(f[tc].iloc[0]);unit='ns' if value>1e17 else 'us' if value>1e14 else 'ms' if value>1e11 else 's';times=pd.to_datetime(f[tc],unit=unit,utc=True)
   else:times=pd.to_datetime(f[tc],utc=True,format='mixed')
   z={'timestamp_ms':times.astype('datetime64[ns, UTC]').astype('int64').to_numpy()//1000000}
   for col in f.columns:
    if col!=tc and pd.api.types.is_numeric_dtype(f[col]):z[col]=f[col].to_numpy()
   np.savez_compressed(path.with_suffix('.npz'),**z)
   result['first']=str(times.min());result['last']=str(times.max());result['sample_rows']=json.loads(f.head(3).to_json(orient='records',date_format='iso'))
  print('EXPORTED',sym,result['rows'],result.get('first'),result.get('last'),flush=True)
 except Exception as e:result['error']=str(e).replace(KEY,'[REDACTED]')
 return result
results=[]
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
 for item in pool.map(export,targets):results.append(item);(O/'tick_export_manifest.json').write_text(json.dumps(results,indent=2))
(O/'reference_request_audit.json').write_text(json.dumps(logs,indent=2));(O/'usage_after_ticks.json').write_text(json.dumps(request(BASE+'/usage',headers=H).json(),indent=2))
print('VALIDATION DOWNLOAD COMPLETE',json.dumps(results),flush=True)

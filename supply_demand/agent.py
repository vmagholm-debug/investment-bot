"""Independent deterministic Supply & Demand paper agent; no broker integration."""
import argparse
import csv
import copy
import hashlib
import json
import math
from functools import lru_cache
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

PROTOCOL = 'supply-demand-v1'
POLICY = {
 'protocol': PROTOCOL, 'mode': 'paper only',
 'universe': {'QQQ': {'currency':'USD','zone':'America/New_York','open':570,'close':960},
              'EXS1.DE': {'currency':'EUR','zone':'Europe/Berlin','open':540,'close':1050}},
 'zones': '1h/4h single base candle range <=0.8 preceding ATR14, followed by departure body >=1.5 ATR and close beyond the base. Zone known only at departure close.',
 'entry': 'First later 5m touch of fresh zone, with directional candle closing beyond proximal boundary. No gamma, options flow or LSTM requirement. No historical signal backfill.',
 'stop': 'Outer low for LONG / high for SHORT of latest completed session-anchored 1h and 4h bars known at decision.',
 'risk_fraction': .005, 'notional_equity_cap': .95, 'cost_per_side': .001,
 'target_R': 2., 'pending_expiry_hours': 6, 'zone_expiry_days': 7,
 'same_bar_stop_and_target': 'Stop first, conservatively; intrabar order unknown.',
 'accounts': 'Separate 100000 USD QQQ and 100000 EUR EXS1.DE paper subaccounts. Never sum native currencies.',
 'limits': 'Experimental fixed rules, unvalidated profitability. Yahoo can be delayed. OHLC fills are illustrative; no spread, borrow fee, dividend liability or real short availability model.'}


def dt(s):
 d=datetime.fromisoformat(s.replace('Z','+00:00')) if isinstance(s,str) else s
 if d.tzinfo is None: raise ValueError('Timezone required')
 return d.astimezone(timezone.utc)


def iso(d):return dt(d).isoformat()
def uid(*parts):return hashlib.sha256(json.dumps(parts,sort_keys=True).encode()).hexdigest()[:24]


@lru_cache(maxsize=128)
def sessions(ticker,start_date,end_date):
 import pandas_market_calendars as mcal
 calendar=mcal.get_calendar('NASDAQ' if ticker=='QQQ' else 'XETR')
 schedule=calendar.schedule(start_date=start_date,end_date=end_date)
 return tuple((row.market_open.to_pydatetime(),row.market_close.to_pydatetime()) for row in schedule.itertuples())


def initialize(now):
 return {'protocol':PROTOCOL,'created_at':iso(now),'policy':POLICY,
         'accounts':{t:{'currency':v['currency'],'initial_cash':100000.,'cash':100000.,'position':None,'pending':None,'used_zones':[],'last_seen':None,'equity_history':[]} for t,v in POLICY['universe'].items()},'trades':[]}


def validate_state(s):
 if s.get('protocol')!=PROTOCOL or s.get('policy')!=POLICY:raise ValueError('Protocol/policy mismatch; no automatic migration or reset')
 if set(s.get('accounts',{}))!=set(POLICY['universe']):raise ValueError('Missing accounts')
 if not isinstance(s.get('trades'),list):raise ValueError('Missing trade history')
 for t,a in s['accounts'].items():
  if a.get('currency')!=POLICY['universe'][t]['currency'] or not math.isfinite(a['cash']):raise ValueError('Invalid account/currency')
  for k in ('position','pending','used_zones','last_seen','initial_cash'):
   if k not in a:raise ValueError('Missing persistent account field: '+k)
 for a in s['accounts'].values():
  for row in [a['position'],a['pending']]:
   if row is not None:
    if row.get('side') not in ('LONG','SHORT'):raise ValueError('Invalid saved direction')
    for k in ('entry','qty','stop','target'):
     if k in row and (not math.isfinite(row[k]) or row[k]<=0):raise ValueError('Invalid saved position value')
    for k in (('entry','qty','stop','target','entry_at','last_checked','zone_id','entry_cost') if row is a['position'] else ('created_at','stop','zone','anchors')):
     if k not in row:raise ValueError('Missing saved position/order field')
 return s


def session_bars(bars,ticker,now):
 cfg=POLICY['universe'][ticker];z=ZoneInfo(cfg['zone']);out=[]
 if not bars:return out
 dates=[dt(b['start']).astimezone(z).date().isoformat() for b in bars]
 calendar={op.astimezone(z).date().isoformat():(op,cl) for op,cl in sessions(ticker,min(dates),max(dates))}
 for b in sorted(bars,key=lambda x:dt(x['start'])):
  start,end=dt(b['start']),dt(b['end']);local=start.astimezone(z);minute=local.hour*60+local.minute
  bounds=calendar.get(local.date().isoformat())
  if end>now or end-start!=timedelta(minutes=5) or not bounds or start<bounds[0] or end>bounds[1] or (start-bounds[0]).total_seconds()%300:continue
  if any(not math.isfinite(float(b[k])) or b[k]<=0 for k in ('open','high','low','close')):raise ValueError('Invalid price')
  if not b['low']<=min(b['open'],b['close'])<=max(b['open'],b['close'])<=b['high']:raise ValueError('Invalid OHLC')
  out.append(dict(b,session=local.date().isoformat(),offset=minute-cfg['open']))
 if len({b['start'] for b in out})!=len(out):raise ValueError('Duplicate price bars')
 return out


def aggregate(bars,hours):
 groups={}
 for b in bars:groups.setdefault((b['session'],b['offset']//(60*hours)),[]).append(b)
 out=[]
 for rows in groups.values():
  if len(rows)!=hours*12 or any(dt(b['start'])!=dt(rows[0]['start'])+timedelta(minutes=5*i) for i,b in enumerate(rows)):continue
  out.append({'start':rows[0]['start'],'end':rows[-1]['end'],'open':rows[0]['open'],'high':max(b['high'] for b in rows),'low':min(b['low'] for b in rows),'close':rows[-1]['close']})
 return out


def zones(candles,hours,ticker):
 out=[]
 for i in range(15,len(candles)):
  earlier=candles[i-14:i];tr=[max(c['high']-c['low'],abs(c['high']-candles[i-14+j-1]['close']),abs(c['low']-candles[i-14+j-1]['close'])) for j,c in enumerate(earlier)]
  atr=sum(tr)/14;base,departure=candles[i-1],candles[i]
  if atr<=0 or base['high']-base['low']>.8*atr or abs(departure['close']-departure['open'])<1.5*atr:continue
  side='LONG' if departure['close']>departure['open'] and departure['close']>base['high'] else 'SHORT' if departure['close']<departure['open'] and departure['close']<base['low'] else None
  if side:out.append({'id':uid(PROTOCOL,ticker,hours,base['start'],departure['end'],side),'side':side,'low':base['low'],'high':base['high'],'formed_at':departure['end'],'timeframe_hours':hours})
 return out


def overlaps(bar,zone):return bar['low']<=zone['high'] and bar['high']>=zone['low']


def signal(bars,zone,now):
 if not bars or dt(zone['formed_at'])>dt(bars[-1]['start']) or now-dt(zone['formed_at'])>timedelta(days=POLICY['zone_expiry_days']):return False
 after=[b for b in bars if dt(b['start'])>=dt(zone['formed_at'])]
 # Any earlier touch consumes freshness even if it did not result in an entry.
 if not after or any(overlaps(b,zone) for b in after[:-1]):return False
 b=after[-1]
 invalid=any(b['close']<zone['low'] if zone['side']=='LONG' else b['close']>zone['high'] for b in after[:-1])
 return not invalid and overlaps(b,zone) and (b['close']>zone['high'] and b['close']>b['open'] if zone['side']=='LONG' else b['close']<zone['low'] and b['close']<b['open'])


def stop_level(side,hourly,four_hourly,decision):
 anchors=[]
 for hours,rows in ((1,hourly),(4,four_hourly)):
  eligible=[b for b in rows if dt(b['end'])<=decision]
  if not eligible:raise ValueError('Missing completed '+str(hours)+'h anchor')
  anchors.append(eligible[-1])
 return (min(b['low'] for b in anchors) if side=='LONG' else max(b['high'] for b in anchors)),anchors


def trade(state,ticker,action,price,qty,at,zone_id,reason,**extra):
 a=state['accounts'][ticker];r={'id':uid(PROTOCOL,ticker,action,iso(at),zone_id),'time':iso(at),'ticker':ticker,'action':action,'price':price,'qty':qty,'amount':price*qty,'quote_currency':a['currency'],'cost':price*qty*POLICY['cost_per_side'],'zone_id':zone_id,'reason':reason,**extra}
 if any(x['id']==r['id'] for x in state['trades']):raise ValueError('Duplicate trade ID')
 state['trades'].append(r);return r


def coverage_check(bars,since,ticker):
 since=dt(since)
 if since<dt(bars[0]['start']):raise ValueError('Execution history gap: saved observation predates downloaded coverage')
 until=dt(bars[-1]['end']);available={dt(b['start']) for b in bars}
 for op,cl in sessions(ticker,since.date().isoformat(),until.date().isoformat()):
  start=op
  while start<cl and start<until:
   if start+timedelta(minutes=5)>since and start not in available:
    raise ValueError('Execution history gap at '+iso(start)+'; order/position preserved')
   start+=timedelta(minutes=5)


def manage(state,ticker,bars,now):
 a=state['accounts'][ticker];p=a['position'];order=a['pending'];notes=[]
 if p:coverage_check(bars,p['last_checked'] or p['entry_at'],ticker)
 if order:coverage_check(bars,order['created_at'],ticker)
 if order and now-dt(order['created_at'])>timedelta(hours=POLICY['pending_expiry_hours']):a['pending']=None;order=None;notes.append('Pending entry expired')
 for b in bars:
  if not p and order and dt(b['start'])>=dt(order['created_at']):
   entry=b['open'];stop=order['stop'];side=order['side'];sign=1 if side=='LONG' else -1
   if (entry-stop)*sign<=0:a['pending']=None;order=None;notes.append('Gap invalidated stop before entry');continue
   risk=abs(entry-stop);equity=a['cash']
   if not math.isfinite(equity) or equity<=0:raise ValueError('Nonpositive account equity; new entries blocked')
   qty=min(equity*POLICY['risk_fraction']/(risk+POLICY['cost_per_side']*(entry+stop)),equity*POLICY['notional_equity_cap']/entry)
   r=trade(state,ticker,'PAPER_LONG' if sign==1 else 'PAPER_SHORT',entry,qty,dt(b['start']),order['zone']['id'],'First future bar open after observed retest decision',decision_at=order['created_at'],stop=stop,target=entry+sign*risk*POLICY['target_R'],anchors=order['anchors'])
   a['cash']-=sign*r['amount']+r['cost'];p={'side':side,'entry':entry,'qty':qty,'entry_cost':r['cost'],'stop':stop,'target':r['target'],'zone_id':r['zone_id'],'entry_at':b['start'],'last_checked':None};a['position']=p;a['pending']=None;order=None
  if not p or dt(b['start'])<dt(p['entry_at']) or p['last_checked'] and dt(b['end'])<=dt(p['last_checked']):continue
  sign=1 if p['side']=='LONG' else -1;stop_hit=b['low']<=p['stop'] if sign==1 else b['high']>=p['stop'];target_hit=b['high']>=p['target'] if sign==1 else b['low']<=p['target'];exit_price=None
  if stop_hit:exit_price=min(b['open'],p['stop']) if sign==1 else max(b['open'],p['stop']);reason='Structural stop; stop first if intrabar order ambiguous'
  elif target_hit:exit_price=p['target'];reason='Fixed illustrative 2R target'
  if exit_price is not None:
   r=trade(state,ticker,'PAPER_CLOSE_LONG' if sign==1 else 'PAPER_COVER_SHORT',exit_price,p['qty'],dt(b['end']),p['zone_id'],reason,entry_at=p['entry_at'],realized_pnl=sign*(exit_price-p['entry'])*p['qty']-p['entry_cost']-exit_price*p['qty']*POLICY['cost_per_side'])
   a['cash']+=sign*r['amount']-r['cost'];a['position']=None;p=None
  else:p['last_checked']=b['end']
 return notes


def run(state,market,now):
 validate_state(state);now=dt(now);start_count=len(state['trades']);report={'protocol':PROTOCOL,'generated_at':iso(now),'policy':POLICY,'markets':{},'errors':{}}
 for ticker,a in state['accounts'].items():
  backup=copy.deepcopy(a);trade_count=len(state['trades'])
  try:
   if isinstance(market.get(ticker),dict) and 'error' in market[ticker]:raise ValueError(market[ticker]['error'])
   bars=session_bars(market[ticker],ticker,now)
   if not bars:raise ValueError('No completed regular-session bars')
   notes=manage(state,ticker,bars,now);last=bars[-1];h1,h4=aggregate(bars,1),aggregate(bars,4);zs=zones(h1,1,ticker)+zones(h4,4,ticker);age=(now-dt(last['end'])).total_seconds();decision='AVVAKTA'
   if a['position']:decision='BEHÅLL '+a['position']['side']
   elif a['pending']:decision='VÄNTANDE '+a['pending']['side']
   elif age>1800:notes.append('Stale/closed market: no new entry')
   elif a['last_seen']==last['end']:notes.append('Bar already processed')
   else:
    candidates=[z for z in zs if z['id'] not in a['used_zones'] and signal(bars,z,now)]
    if candidates:
     for candidate in candidates:coverage_check(bars,candidate['formed_at'],ticker)
     z=max(candidates,key=lambda z:(dt(z['formed_at']),z['timeframe_hours']));stop,anchors=stop_level(z['side'],h1,h4,now);sign=1 if z['side']=='LONG' else -1
     if (last['close']-stop)*sign>0:
      a['pending']={'created_at':iso(now),'signal_bar_end':last['end'],'side':z['side'],'stop':stop,'zone':z,'anchors':anchors};a['used_zones'].append(z['id']);decision='VÄNTANDE '+z['side']
     else:notes.append('Structural stop on wrong side of price; no entry')
    else:notes.append('No fresh first-retest rejection setup')
   a['last_seen']=last['end'];p=a['position'];equity=a['cash']+((1 if p['side']=='LONG' else -1)*p['qty']*last['close'] if p else 0)
   a.setdefault('equity_history',[]).append({'time':iso(now),'equity':equity})
   peak=a['initial_cash'];drawdown=0.
   for observation in a['equity_history']:
    peak=max(peak,observation['equity']);drawdown=min(drawdown,observation['equity']/peak-1)
   report['markets'][ticker]={'max_observed_drawdown':drawdown,'currency':a['currency'],'cash':a['cash'],'net_equity':equity,'return_since_start':equity/a['initial_cash']-1,'position':p,'pending':a['pending'],'decision':decision,'notes':notes,'quote_date':last['end'],'stale_valuation':age>1800,'zone_count':len(zs),'recent_zones':sorted(zs,key=lambda z:z['formed_at'],reverse=True)[:12]}
  except Exception as e:
   state['accounts'][ticker]=backup;del state['trades'][trade_count:];report['errors'][ticker]=str(e);report['markets'][ticker]={'currency':backup['currency'],'cash':backup['cash'],'position':backup['position'],'pending':backup['pending'],'decision':'DATAFEL – INGA NYA ORDER','net_equity':None,'stale_valuation':True}
 report['new_trades']=state['trades'][start_count:];report['trades']=state['trades'];report['started_at']=state['created_at'];return report


def download(now):
 import yfinance as yf
 from curl_cffi import requests
 market={}
 for ticker in POLICY['universe']:
  try:
   session=requests.Session(impersonate='chrome',timeout=15);info=yf.Ticker(ticker,session=session)
   frame=info.history(period='1mo',interval='5m',auto_adjust=False,prepost=False,timeout=20)
   currency=info.get_history_metadata().get('currency')
   if currency!=POLICY['universe'][ticker]['currency']:raise ValueError('Unexpected/missing quote currency')
   market[ticker]=[{'start':iso(t.to_pydatetime()),'end':iso(t.to_pydatetime()+timedelta(minutes=5)),'open':float(r.Open),'high':float(r.High),'low':float(r.Low),'close':float(r.Close),'volume':float(r.Volume)} for t,r in frame.iterrows() if t.to_pydatetime()+timedelta(minutes=5)<=now]
  except Exception as e:market[ticker]={'error':str(e)}
 return market


def write_outputs(state,report,folder):
 folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
 for name,value in [('state.json',state),('latest.json',report)]:
  p=folder/name;temp=p.with_suffix('.tmp');temp.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False));temp.replace(p)
 keys=['id','time','ticker','action','qty','price','amount','quote_currency','cost','realized_pnl','zone_id','reason']
 with (folder/'trades.csv').open('w') as f:
  writer=csv.DictWriter(f,fieldnames=keys,extrasaction='ignore');writer.writeheader();writer.writerows(state['trades'])
 text=['# Supply & Demand · PAPER',report['generated_at'],json.dumps(POLICY,ensure_ascii=False,indent=2),json.dumps(report['markets'],ensure_ascii=False,indent=2),'## New trades',json.dumps(report['new_trades'],ensure_ascii=False,indent=2),'## Errors',json.dumps(report['errors'],ensure_ascii=False)]
 (folder/'summary.md').write_text('\n\n'.join(text))


def main():
 p=argparse.ArgumentParser();p.add_argument('--state',required=True);p.add_argument('--output',required=True);args=p.parse_args();now=datetime.now(timezone.utc)
 state=validate_state(json.loads(Path(args.state).read_text()));report=run(state,download(now),now);write_outputs(state,report,args.output);print(json.dumps({'protocol':PROTOCOL,'new_trades':len(report['new_trades']),'errors':report['errors']}))
 if report['errors']:raise SystemExit(1)

if __name__=='__main__':main()

"""Read-only dashboard export. Never loads a model or executes trades."""
import argparse
import csv
import io
import json
import math
import shutil
import sys
import xml.etree.ElementTree as ET
from urllib.request import Request, urlopen
from urllib.parse import urlencode
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from market import CurrencyConverter
from industry_catalogue import analyze_catalogue
import yfinance as yf


def number(v):
    try:
        n=float(v)
        return n if math.isfinite(n) else None
    except (TypeError, ValueError): return None


def relevant_title(title, company):
    excluded={'group','holding','holdings','company','corp','corporation','incorporated','depositary','shares','solutions'}
    words=[w.lower().strip('.,()') for w in company.split() if len(w)>3 and w.lower().strip('.,()') not in excluded][:2]
    return any(w in title.lower() for w in words)


def basis(trades):
    lots={}
    for t in trades:
        symbol=t['ticker']; qty=number(t['qty']) or 0; price=number(t['price']) or 0
        q,c=lots.get(symbol,(0.,0.))
        if 'BUY' in t['action']: q,c=q+qty,c+qty*price
        elif 'SELL' in t['action']:
            if qty>q+1e-6: raise ValueError('Sale exceeds reconstructed position')
            c=c*(max(0,q-qty)/q) if q else 0.; q=max(0,q-qty)
        lots[symbol]=(q,c)
    return lots


def export(report, output, refresh=False, previous=None, run_url=None):
    output.mkdir(parents=True,exist_ok=True)
    watch={r['ticker']:r for r in report.get('watchlist',[])}
    selected=report.get('discovery',{}).get('selected',{})
    decisions={r['ticker']:r for r in report['results']}
    symbols=list(dict.fromkeys(list(report['portfolio'])+list(watch)+list(decisions)))
    fx=CurrencyConverter(); quotes={}; articles={}; issues=[]
    now=datetime.now(timezone.utc).isoformat()
    for symbol in symbols:
        old=report['valuation_prices'].get(symbol,{})
        q={**old,'quote_time':old.get('data_date'),'status':'bot_snapshot','history':[],'daily_change_pct':None}
        if refresh:
            try:
                ticker=yf.Ticker(symbol)
                frame=ticker.history(period='5d',interval='5m',auto_adjust=False,raise_errors=True)
                close=frame['Close'].dropna()
                if close.empty: raise ValueError('No quote history')
                price=float(close.iloc[-1]);stamp=close.index[-1]
                if (datetime.now(timezone.utc)-stamp.to_pydatetime()).total_seconds()>7*86400:
                    raise ValueError('Quote older than seven days')
                currency=fx.currency(symbol)
                converted=fx.convert(price,currency)
                dates=close.index.date;before=close[dates<dates[-1]]
                change=(price/float(before.iloc[-1])-1)*100 if len(before) else None
                q={**converted,'quote_time':stamp.isoformat(),'status':'provider_quote',
                   'daily_change_pct':change,'history':[[i.isoformat(),float(v)] for i,v in close.items()]}
            except Exception as exc:
                q['error']=str(exc);issues.append(symbol+': '+str(exc))
        quotes[symbol]=q
        research=report.get('company_research',{}).get(symbol,{})
        for a in research.get('news',[]):
            key=a.get('url') or a.get('title')
            if key:
                if key not in articles: articles[key]={**a,'tickers':[],'origin':'bot_research'}
                articles[key]['tickers'].append(symbol)
        # Fresh headlines only for holdings/watchlist; avoid unrelated provider stories.
        if refresh and (symbol in watch or symbol in report['portfolio']):
            try:
                name=watch.get(symbol,{}).get('name') or selected.get(symbol,{}).get('name','')
                for item in yf.Ticker(symbol).get_news(count=8):
                    c=item.get('content',item);title=c.get('title','');summary=c.get('summary','')
                    related=c.get('relatedTickers',item.get('relatedTickers',[]))
                    if symbol not in related and not relevant_title(title, name): continue
                    url=(c.get('canonicalUrl') or {}).get('url') or (c.get('clickThroughUrl') or {}).get('url')
                    if not url or not c.get('pubDate'): continue
                    if url not in articles:
                        articles[url]={'title':title,'summary':summary,'url':url,'published_at':c['pubDate'],
                          'provider':(c.get('provider') or {}).get('displayName','Yahoo'), 'tickers':[], 'origin':'headline_refresh'}
                    if symbol not in articles[url]['tickers']: articles[url]['tickers'].append(symbol)
            except Exception as exc: issues.append(symbol+' news: '+str(exc))
    if refresh:
        for symbol, company in watch.items():
            term=company['name'].split(' (')[0]
            try:
                url='https://news.google.com/rss/search?'+urlencode({'q':'"'+term+'" when:7d','hl':'sv' if company['region']=='Europe' else 'en-US','gl':'SE' if company['region']=='Europe' else 'US','ceid':'SE:sv' if company['region']=='Europe' else 'US:en'})
                with urlopen(Request(url,headers={'User-Agent':'Mozilla/5.0'}),timeout=20) as response:
                    tree=ET.fromstring(response.read())
                for item in tree.findall('./channel/item')[:30]:
                    title=item.findtext('title',''); link=item.findtext('link','');date=item.findtext('pubDate')
                    if not date or not link or not relevant_title(title,term): continue
                    stamp=parsedate_to_datetime(date)
                    if not 0 <= (datetime.now(timezone.utc)-stamp).total_seconds() <= 7*86400: continue
                    if link not in articles:
                        articles[link]={'title':title,'url':link,'published_at':stamp.isoformat(),
                          'provider':item.findtext('source','Google News'),'tickers':[symbol],
                          'origin':'headline_refresh','matching':'Google News exact company-name search; relevance not independently verified'}
            except Exception as exc:issues.append(symbol+' news feed: '+str(exc))
    lots=basis(report['trades']);positions=[];value=0.;complete=True
    for symbol,qty in report['portfolio'].items():
        q=quotes[symbol];price=q.get('price');cost=lots.get(symbol,(0,0))[1]
        if not price: complete=False
        marked=qty*price if price else None
        if marked is not None:value+=marked
        positions.append({'ticker':symbol,'qty':qty,'cost':cost,'value':marked,
                          'pnl':marked-cost if marked is not None else None})
    history=json.loads(Path(__file__).with_name('history-seed.json').read_text()) + (previous or {}).get('account_history',[])
    entry={'time':report['generated_at'],'value':report['total_account_value']}
    history={p['time']:p for p in history};history[entry['time']]=entry
    data={'updated_at':now,'report_time':report['generated_at'],'run_url':run_url,
      'cash':report['remaining_cash'],'starting_cash':report['starting_cash'],
      'account_value':report['remaining_cash']+value if complete else None,
      'report_account_value':report['total_account_value'],
      'valuation_mixed':any(quotes[s]['status']!='provider_quote' for s in report['portfolio']),
      'positions':positions,'quotes':quotes,'watchlist':list(watch.values()),
      'decisions':decisions,'research':report.get('company_research',{}),
      'names':{s:watch.get(s,{}).get('name') or selected.get(s,{}).get('name') or s for s in symbols},
      'long_term_analysis':report.get('long_term_analysis'),
      'industry_catalogue':analyze_catalogue(report.get('company_research',{})),
      'trades':report['trades'],'learning':report['learning'],'discovery':report.get('discovery',{}),
      'news':sorted(articles.values(),key=lambda a:a.get('published_at',''),reverse=True),
      'issues':issues,'account_history':sorted(history.values(),key=lambda p:p['time']),
      'strategy_policy':report.get('strategy_policy'),'model_validation':report.get('model_validation')}
    (output/'data.json').write_text(json.dumps(data,ensure_ascii=False,allow_nan=False))
    (output/'report.json').write_text(json.dumps(report,ensure_ascii=False,allow_nan=False))
    for name in ('index.html','style.css','app.js'):shutil.copy(Path(__file__).with_name(name),output/name)
    (output/'.nojekyll').touch()
    return data


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--report',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--previous',type=Path);p.add_argument('--refresh',action='store_true');p.add_argument('--run-url')
    a=p.parse_args();previous=json.loads(a.previous.read_text()) if a.previous and a.previous.exists() else None
    data=export(json.loads(a.report.read_text()),a.output,a.refresh,previous,a.run_url)
    for name in ('summary.md','trades.csv'):
        source=a.report.parent/name
        if source.exists():shutil.copy(source,a.output/name)
    print(json.dumps({'symbols':len(data['quotes']),'news':len(data['news']),'issues':data['issues']}))

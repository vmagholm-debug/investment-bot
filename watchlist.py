"""User-requested persistent review list, separate from dynamic discovery."""
import json
from pathlib import Path


def load_watchlist(path=None):
    rows = json.loads(Path(path or Path(__file__).with_name('watchlist.json')).read_text())
    if len({r['ticker'] for r in rows}) != len(rows):
        raise ValueError('Duplicate watchlist ticker')
    return rows


def include_watchlist(tickers, watchlist):
    return list(dict.fromkeys(list(tickers) + [r['ticker'] for r in watchlist]))


def summarize(watchlist, research, results):
    decisions = {r['ticker']: r for r in results}
    rows = []
    for company in watchlist:
        symbol = company['ticker']
        evidence = research.get(symbol, {})
        result = decisions.get(symbol, {})
        rows.append({**company, 'next_report_provider_date': evidence.get('earnings', {}).get('next_report'),
                     'date_status': 'Yahoo provider date; not independently confirmed and reporting quarter unspecified',
                     'financial_period': evidence.get('financials', {}).get('period_end'),
                     'research_approved': evidence.get('gate', {}).get('approved', False),
                     'research_reason': evidence.get('gate', {}).get('reason', 'Research unavailable'),
                     'decision': result.get('error') or result.get('action', 'Unavailable'),
                     'decision_reason': result.get('reason'),
                     'strategies': result.get('strategies', {}),
                     'research_errors': evidence.get('errors', {})})
    return rows

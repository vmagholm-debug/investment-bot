"""Dated research leads, never executable orders. Standard-library feed validation."""
from datetime import datetime, timezone, timedelta
import json
import math
from pathlib import Path
import re
from urllib.parse import urlparse

DEFAULT_PATH = Path(__file__).with_name('miljon_signals.json')
POLICY = ('MiljonBot supplies research candidates, not orders. No market-cap or minimum-price '
          'filter on these candidates. Existing strategy and research approval remain required. '
          'Positive, source-checked signals only for entries; at most one entry per signal. '
          'Below $5 USD/share uses 1% cash, otherwise 2%; capped at 1% of median 20-day '
          'USD turnover. Minimum median turnover $100000. Experimental daily-close simulation, '
          'not live execution; no spread/slippage model or Avanza availability verification.')


def stamp(value):
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None:
        raise ValueError('Timezone required')
    return result.astimezone(timezone.utc)


def validate(document):
    if not isinstance(document, dict) or document.get('version') != 1 or not isinstance(document.get('signals'), list):
        raise ValueError('Expected version 1 and signals array')
    if len(document['signals']) > 200:
        raise ValueError('Feed limited to 200 records; archive older records separately')
    stamp(document['updated_at'])
    seen = set()
    for row in document['signals']:
        if not isinstance(row, dict):
            raise ValueError('Signal records must be objects')
        for key in ('id', 'ticker', 'company', 'exchange', 'quote_currency', 'source_url',
                    'source_status', 'published_at', 'expires_at', 'status', 'bias', 'thesis', 'risk'):
            if not isinstance(row.get(key), str) or not row[key].strip():
                raise ValueError('Missing string field: ' + key)
        if not re.fullmatch(r'[A-Za-z0-9_.:-]{1,160}', row['id']) or row['id'] in seen:
            raise ValueError('Invalid or duplicate signal ID')
        seen.add(row['id'])
        if not re.fullmatch(r'[A-Z0-9][A-Z0-9.=-]{0,24}', row['ticker']):
            raise ValueError('Invalid Yahoo ticker')
        if row['source_status'] not in ('checked', 'unverified'):
            raise ValueError('Invalid source status')
        if row['status'] not in ('BEVAKA', 'DJUPRESEARCH', 'CANDIDATE', 'REJECTED'):
            raise ValueError('Invalid status')
        if row['bias'] not in ('positive', 'negative', 'uncertain'):
            raise ValueError('Invalid bias')
        url = urlparse(row['source_url'])
        if url.scheme != 'https' or not url.hostname or url.username or url.password:
            raise ValueError('Public HTTPS evidence URL required')
        start, end = stamp(row['published_at']), stamp(row['expires_at'])
        if not start < end <= start + timedelta(days=7):
            raise ValueError('Signals expire within seven days of original publication')
        if row['source_status'] == 'checked':
            checked = stamp(row['source_checked_at'])
            if checked < start:
                raise ValueError('Source check predates publication')
    return document


def load_feed(path=DEFAULT_PATH, now=None):
    now = now or datetime.now(timezone.utc)
    report = {'policy': POLICY, 'updated_at': None, 'signals': [], 'errors': []}
    try:
        doc = validate(json.loads(Path(path).read_text()))
        updated = stamp(doc['updated_at'])
        if updated > now + timedelta(minutes=5):
            raise ValueError('Future feed timestamp')
        report['updated_at'] = doc['updated_at']
        for row in doc['signals']:
            active = stamp(row['published_at']) <= now < stamp(row['expires_at']) and row['status'] != 'REJECTED'
            report['signals'].append({**row, 'active': active,
                                      'intake': 'candidate' if active else 'expired, future or rejected'})
        priority = sorted([r for r in report['signals'] if r['active']],
                          key=lambda r: (r['bias'] == 'positive', r['published_at']), reverse=True)
        selected = list(dict.fromkeys(r['ticker'] for r in priority))[:12]
        for row in report['signals']:
            row['selected'] = row['active'] and row['ticker'] in selected
            if row['active'] and not row['selected']:
                row['intake'] = 'deferred: twelve candidate symbols per run'
    except (ValueError, TypeError, KeyError, OSError) as exc:
        report['errors'].append(str(exc))
    return report


def candidates(report):
    return list(dict.fromkeys(r['ticker'] for r in report['signals'] if r.get('selected', r['active'])))


def entry_check(rows, quote, frame, research, cash, trades, now=None):
    """Fail closed only for MiljonBot entries; existing holdings can always exit."""
    now = now or datetime.now(timezone.utc)
    used = {sid for t in trades if t.get('action') == 'PAPER BUY' for sid in t.get('miljon_signal_ids', [])}
    eligible = [r for r in rows if r['bias'] == 'positive' and r['status'] != 'REJECTED'
                and r['source_status'] == 'checked' and r['id'] not in used
                and stamp(r['published_at']) <= now < stamp(r['expires_at'])
                and stamp(r['source_checked_at']) <= now]
    result = {'approved': False, 'reason': '', 'signal_ids': [], 'amount': 0.}
    if not eligible:
        result['reason'] = 'MiljonBot: no fresh, unused, positive source-checked signal'
        return result
    # Never simulate entry at an earlier close than when the signal was known.
    bar_date = frame.index[-1].date()
    eligible = [r for r in eligible if
                max(stamp(r['published_at']).date(), stamp(r['source_checked_at']).date()) < bar_date < now.date()]
    if not eligible:
        result['reason'] = 'MiljonBot: waiting for a completed daily close after signal publication and source check'
        return result
    instrument = research.get('instrument', {})
    eligible = [r for r in eligible if instrument.get('symbol') == r['ticker']
                and instrument.get('exchange') == r['exchange']
                and instrument.get('quote_type') == 'EQUITY'
                and instrument.get('currency') == r['quote_currency'] == quote.get('quote_currency')]
    if not eligible:
        result['reason'] = 'MiljonBot: instrument, exchange or currency not confirmed by Yahoo'
        return result
    conversion = quote.get('quote_unit_scale', 1.) * quote.get('fx_to_usd', 1.)
    turnover = float((frame.Close.tail(20) * frame.Volume.tail(20)).median()) * conversion
    penny = quote['price'] < 5.
    fraction = .01 if penny else .02
    result.update(penny_stock_proxy=penny, cash_fraction=fraction, median_turnover_usd=turnover if math.isfinite(turnover) else None)
    if len(frame) < 20 or not math.isfinite(turnover) or turnover < 100000:
        result['reason'] = 'MiljonBot: median daily USD turnover below $100000 or unavailable'
        return result
    amount = min(cash * fraction, turnover * .01)
    if amount < 1:
        result['reason'] = 'MiljonBot: insufficient fake cash'
        return result
    result.update(approved=True, signal_ids=[r['id'] for r in eligible], amount=amount,
                  reason='MiljonBot candidate checked; ' + ('penny-stock' if penny else 'standard') + ' sizing, capped at 1% of median daily turnover')
    return result


def summarize(report, results):
    decisions = {r['ticker']: r for r in results}
    return {**report, 'signals': [{**r, 'decision': decisions.get(r['ticker'], {}).get('action', 'NOT ANALYZED'),
            'decision_reason': decisions.get(r['ticker'], {}).get('error') or decisions.get(r['ticker'], {}).get('reason', r['intake']),
            'entry_check': decisions.get(r['ticker'], {}).get('miljon_entry_check')}
            for r in report['signals']]}


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Validate candidate feed; never places orders')
    parser.add_argument('path', nargs='?', type=Path, default=DEFAULT_PATH)
    args = parser.parse_args()
    doc = validate(json.loads(args.path.read_text()))
    print(f"Valid feed: {len(doc['signals'])} records")

"""Auditable US security directory. Identification is not price/research coverage."""
import argparse
import csv
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

NASDAQ = 'https://www.nasdaqtrader.com/dynamic/SymDir/'
FINRA = 'https://api.finra.org/'
FILES = ('nasdaqlisted.txt', 'otherlisted.txt', 'nasdaqtraded.txt')


def request(url, payload=None):
    req = Request(url, data=json.dumps(payload).encode() if payload else None,
                  headers={'Accept': 'application/json' if payload else '*/*', 'Content-Type': 'application/json'})
    with urlopen(req, timeout=45) as response:
        return response.read(), dict(response.headers)


def parse_nasdaq(text):
    lines = text.splitlines()
    if not lines or not lines[-1].startswith('File Creation Time:'):
        raise ValueError('Missing Nasdaq completeness footer')
    rows = list(csv.DictReader(lines[:-1], delimiter='|'))
    if not rows or any(r.get('Test Issue') not in ('Y', 'N') for r in rows):
        raise ValueError('Invalid Nasdaq directory')
    return [r for r in rows if r['Test Issue'] == 'N'], lines[-1].split('|')[0]


def fetch(raw):
    raw.mkdir(parents=True, exist_ok=True)
    for name in FILES:
        data, _ = request(NASDAQ + name)
        parse_nasdaq(data.decode())
        (raw / name).write_bytes(data)
    data, _ = request(FINRA + 'partitions/group/otcMarket/name/otcSecurityMaster')
    (raw / 'finra-partitions.json').write_bytes(data)
    date = max(p['partitions'][0] for p in json.loads(data)['availablePartitions'])
    offset, expected = 0, None
    while expected is None or offset < expected:
        query = {'limit': 5000, 'offset': offset, 'sortFields': ['+issueSymbolIdentifier'],
                 'compareFilters': [{'fieldName': 'asOfDate', 'fieldValue': date, 'compareType': 'EQUAL'}]}
        data, headers = request(FINRA + 'data/group/otcMarket/name/otcSecurityMaster', query)
        headers = {k.lower(): v for k, v in headers.items()}
        total = int(headers['record-total'])
        rows = json.loads(data)
        if not rows or (expected is not None and total != expected):
            raise ValueError('FINRA incomplete or changed during pagination; retry fresh snapshot')
        if int(headers['record-offset']) != offset or any(r['asOfDate'] != date for r in rows):
            raise ValueError('FINRA offset/date mismatch')
        expected = total
        (raw / f'finra-{offset}.json').write_bytes(data)
        (raw / f'finra-{offset}-metadata.json').write_text(json.dumps({'total': total, 'offset': offset, 'rows': len(rows)}))
        offset += len(rows)
    return date


def category(name, etf=False, issue_type=''):
    """Conservative labels only: retain every record, including uncertain types."""
    s = (issue_type or name).lower()
    if etf or 'exchange traded fund' in s or issue_type == 'ETFs': return 'fund_or_etp'
    if any(w in s for w in ('warrant', 'rights')): return 'warrant_or_right'
    if any(w in s for w in ('preferred', 'preference')): return 'preferred_stock'
    if any(w in s for w in ('note', 'bond', 'debenture', 'structured product')): return 'debt_or_structured'
    if any(w in s for w in ('depositary', 'adr', 'new york registry')): return 'depositary_receipt_or_share'
    if any(w in s for w in ('common stock', 'common shares', 'ordinary shares', 'reit')): return 'common_or_ordinary_stock'
    if 'unit' in s: return 'unit'
    return 'other_or_unclassified'


def build(raw, output):
    source_rows, dates = {}, {}
    for name in FILES:
        source_rows[name], dates[name] = parse_nasdaq((raw / name).read_text())
    listing = source_rows['nasdaqlisted.txt'] + source_rows['otherlisted.txt']
    def key(row): return row.get('NASDAQ Symbol') or row['Symbol']
    listed = {key(r) for r in listing}
    traded = {key(r) for r in source_rows['nasdaqtraded.txt']}
    if len(listed) != len(listing) or listed != traded:
        raise ValueError('Nasdaq directory duplicates or cross-file mismatch')
    frows, offset, expected = [], 0, None
    while expected is None or offset < expected:
        meta = json.loads((raw / f'finra-{offset}-metadata.json').read_text())
        rows = json.loads((raw / f'finra-{offset}.json').read_text())
        if meta['offset'] != offset or meta['rows'] != len(rows) or not rows:
            raise ValueError('FINRA page incomplete')
        if expected is not None and meta['total'] != expected: raise ValueError('FINRA total changed')
        expected = meta['total']; frows.extend(rows); offset += len(rows)
    fset = {r['issueSymbolIdentifier'] for r in frows}
    if len(frows) != expected or len(fset) != expected or len({r['asOfDate'] for r in frows}) != 1:
        raise ValueError('FINRA completeness/uniqueness/date failure')
    records = {}
    for r in listing:
        symbol = key(r)
        records[symbol] = {'symbol': symbol, 'name': r['Security Name'],
            'market': 'Nasdaq' if 'Symbol' in r else r['Exchange'],
            'security_type': category(r['Security Name'], r['ETF'] == 'Y'),
            'source_type': '', 'sources': 'Nasdaq Trader', 'as_of': dates['nasdaqlisted.txt' if 'Symbol' in r else 'otherlisted.txt']}
    for r in frows:
        symbol = r['issueSymbolIdentifier']
        if symbol in records:
            records[symbol]['sources'] += '; FINRA'
        else:
            records[symbol] = {'symbol': symbol, 'name': r['securityDescription'], 'market': 'OTC',
                'security_type': category(r['securityDescription'], issue_type=r['issueType']),
                'source_type': r['issueType'], 'sources': 'FINRA', 'as_of': r['asOfDate']}
    extra = []
    supplemental = raw / 'otcmarkets.csv'
    if supplemental.exists():
        for r in csv.DictReader(supplemental.open()):
            symbol = r['Symbol']
            if symbol in records:
                records[symbol]['sources'] += '; OTC Markets'
            else:
                extra.append(symbol)
                records[symbol] = {'symbol': symbol, 'name': r['Security Name'], 'market': 'OTC '+r['Tier'],
                    'security_type': category(r['Security Name'], issue_type=r['Sec Type']),
                    'source_type': r['Sec Type'], 'sources': 'OTC Markets supplemental export; current status needs reconciliation',
                    'as_of': 'Export retrieved 2026-09-29; source effective date not supplied'}
    output.mkdir(parents=True, exist_ok=True)
    values = sorted(records.values(), key=lambda r:r['symbol'])
    for filename, rows in [('all_securities.csv', values), ('stocks_and_depositary_receipts.csv', [r for r in values if r['security_type'] in ('common_or_ordinary_stock','preferred_stock','depositary_receipt_or_share')])]:
        with (output / filename).open('w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=list(values[0])); writer.writeheader();writer.writerows(rows)
    audit = {'retrieved_at': datetime.now(timezone.utc).isoformat(), 'nasdaq_source_dates': dates,
        'finra_as_of': frows[0]['asOfDate'], 'nasdaq_listed':len(source_rows['nasdaqlisted.txt']),
        'other_exchange_listed':len(source_rows['otherlisted.txt']), 'finra_otc':expected,
        'exchange_otc_overlap':len(listed & fset), 'supplemental_symbols':extra,
        'total_unique_securities':len(values), 'categories':dict(Counter(r['security_type'] for r in values)),
        'nasdaq_cross_file_missing':sorted(traded-listed),
        'official_directory_records_captured_pct':100.0,
        'coverage_denominator':'All non-test Nasdaq-listed and other-exchange listed directory records, plus every FINRA OTC security-master record for the stated dates. Not a claim about private companies or undocumented securities.',
        'price_history_coverage':'Not measured; identification does not mean analyzed or eligible for trading.',
        'classification':'Heuristic for exchange records; FINRA structured type for OTC. All uncertain instruments retained in all_securities.csv.',
        'sources':[NASDAQ+n for n in FILES]+[FINRA+'data/group/otcMarket/name/otcSecurityMaster','https://www.otcmarkets.com/research/stock-screener'],
        'raw_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in raw.iterdir() if p.suffix in ('.txt','.json','.csv') and 'headers' not in p.name}}
    (output/'coverage.json').write_text(json.dumps(audit,indent=2)+'\n')
    return audit


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raw',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--fetch',action='store_true')
    args=parser.parse_args()
    if args.fetch: fetch(args.raw)
    print(json.dumps(build(args.raw,args.output),indent=2))

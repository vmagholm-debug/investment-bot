"""Live Yahoo Finance screening; no hard-coded stock symbols."""
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import yfinance as yf

EUROPE_REGIONS = {'at', 'be', 'ch', 'cz', 'de', 'dk', 'ee', 'es', 'fi', 'fr',
                  'gb', 'gr', 'hu', 'ie', 'is', 'it', 'lt', 'lv', 'nl', 'no',
                  'pl', 'pt', 'ro', 'se'}
EUROPE_SUFFIXES = {'.AS', '.BR', '.DE', '.F', '.PA', '.L', '.CO', '.ST', '.HE',
                   '.OL', '.SW', '.MC', '.MI', '.LS', '.VI', '.WA', '.PR', '.AT',
                   '.IC', '.BD', '.IR', '.TL', '.RG', '.VS'}


def is_europe(symbol):
    return any(symbol.endswith(suffix) for suffix in EUROPE_SUFFIXES)


def discover(path, europe_count=24, global_count=8, day=None):
    path = Path(path)
    state = json.loads(path.read_text()) if path.exists() else {'last_selected': {}, 'offsets': {}}
    today = day or datetime.now(timezone.utc).date().isoformat()
    allowed = set(yf.EquityQuery('eq', ['region', 'us']).valid_values['region'])
    groups = [('Europe', sorted(EUROPE_REGIONS & allowed), europe_count),
              ('Other', sorted(allowed - EUROPE_REGIONS), global_count)]
    selected = []
    metadata = {}
    scans = []
    for name, regions, count in groups:
        query = yf.EquityQuery('and', [
            yf.EquityQuery('is-in', ['region', *regions]),
            yf.EquityQuery('gt', ['avgdailyvol3m', 100000]),
            yf.EquityQuery('gte', ['intradaymarketcap', 500000000]),
        ])
        # Current active leaders plus a rotating alphabetical page expose the
        # model to more than the same popular tickers every day.
        active = yf.screen(query, size=250, sortField='dayvolume', sortAsc=False)
        if not active or not active.get('quotes'):
            raise ValueError(f'Live {name} screener returned no candidates; no fixed-list fallback')
        total = int(active.get('total', len(active['quotes'])))
        offset = int(state['offsets'].get(name, 0))
        if offset >= total:
            offset = 0
        page = yf.screen(query, offset=offset, size=250, sortField='ticker', sortAsc=True)
        if not page or not page.get('quotes'):
            raise ValueError(f'Live {name} discovery page failed')
        candidates = {}
        for item in active['quotes'] + page['quotes']:
            symbol = item.get('symbol')
            if (symbol and item.get('quoteType', 'EQUITY') == 'EQUITY'
                    and not (name == 'Europe' and symbol.endswith('.IL'))):
                candidates[symbol] = item
        def ranking(symbol):
            # Least recently analyzed first, stable random exploration each day.
            return (state['last_selected'].get(symbol, ''),
                    hashlib.sha256((today + ':' + symbol).encode()).hexdigest())
        # Round-robin exchanges so one very large market does not fill every slot.
        by_exchange = {}
        for symbol in sorted(candidates, key=ranking):
            by_exchange.setdefault(candidates[symbol].get('exchange', 'unknown'), []).append(symbol)
        symbols = []
        while by_exchange and len(symbols) < count:
            for exchange in sorted(by_exchange, key=lambda e: ranking(by_exchange[e][0])):
                symbols.append(by_exchange[exchange].pop(0))
                if not by_exchange[exchange]:
                    del by_exchange[exchange]
                if len(symbols) == count:
                    break
        if not symbols:
            raise ValueError(f'No usable {name} candidates')
        for symbol in symbols:
            item = candidates[symbol]
            metadata[symbol] = {'region_group': name, 'name': item.get('shortName', symbol),
                                'currency': item.get('currency'), 'exchange': item.get('exchange'),
                                'source': 'Yahoo Finance live EquityQuery screener'}
            state['last_selected'][symbol] = today
        selected.extend(symbols)
        state['offsets'][name] = (offset + 250) if offset + 250 < total else 0
        scans.append({'group': name, 'matching_stocks': total,
                      'unique_candidates_fetched': len(candidates), 'page_offset': offset,
                      'selected': symbols, 'regions': regions})
    return selected, {'mode': 'live discovery', 'scans': scans, 'selected': metadata,
                      'filters': 'Average daily volume >100000; Yahoo intradaymarketcap >=500000000',
                      'selection': '24 Europe / 8 elsewhere; exchange diversification, least recently selected, daily seeded exploration; excludes London international-order-book secondary listings'}, state


def save_discovery(path, state):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(state, indent=2) + '\n')
    temporary.replace(path)

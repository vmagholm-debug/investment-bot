"""Prospective, separately persisted paper comparison. Never places real orders."""
from copy import deepcopy
from datetime import datetime, timezone
import json
import math
from pathlib import Path

import pandas as pd

from miljon_signals import stamp
from strategies import signals, NAMES

PROTOCOL = 'broad-paper-v1'
COST = .001  # Illustrative combined fee/slippage per side, not measured broker costs.
POLICY = {
    'protocol': PROTOCOL, 'candidate_cap': None, 'max_holdings': 20,
    'research': 'One supportive category OR a positive checked catalyst; negative news/earnings block. Missing coverage is disclosed.',
    'signal_sources': 'Feed entries require checked source and matching instrument; negative leads cannot fund entries.',
    'entry': 'Momentum percentile >=0.6 with positive 20/60-day returns; breakout volume >=1.2; mean reversion z<=-1, RSI<45 and rebound; other two strategies unchanged. Orders wait for a completed daily bar dated after the decision date.',
    'sizing': 'Below USD5: 0.5% cash; otherwise 2%; capped at 0.5% median 20-bar USD turnover; minimum turnover USD25000. No market-cap floor.',
    'exit': 'Same daily -5%, +10%, 21 trading-day and strategy exits as reference; thresholds are not guaranteed fills.',
    'cost_per_side': COST, 'limitations': 'Daily adjusted-close simulation; no live execution, dividends, calibrated probability or proven alpha. Bundled experiment cannot attribute effects to one rule.',
}


def snapshot(bot):
    return deepcopy({k: getattr(bot, k) for k in
                     ('cash', 'portfolio', 'trade_log', 'last_prices')})


def relaxed_signals(frame, research, rank, now):
    rules = signals(frame, research, rank, now)
    if len(frame) < 61:
        return rules
    close = frame.Close.astype(float)
    price = float(close.iloc[-1])
    sd = float(close.tail(20).std())
    z = (price - float(close.tail(20).mean())) / sd if sd else 0.
    r20, r60 = price / float(close.iloc[-21]) - 1, price / float(close.iloc[-61]) - 1
    volume = float(frame.Volume.iloc[-21:-1].mean())
    multiple = float(frame.Volume.iloc[-1]) / volume if volume > 0 else 0.
    for name, entry, reason in [
        ('momentum', rank is not None and rank >= .6 and r20 > 0 and r60 > 0,
         f'positive 20/60-day returns, peer percentile {rank} >=0.6'),
        ('mean_reversion', z <= -1 and float(frame.RSI.iloc[-1]) < 45 and price > float(close.iloc[-2]),
         f'z={z:.2f} <=-1, RSI<45 and rebound'),
        ('breakout', price > float(frame.High.iloc[-21:-1].max()) and multiple >= 1.2,
         f'prior 20-bar breakout, volume multiple {multiple:.2f} >=1.2')]:
        rules[name] = {**rules[name], 'entry': bool(entry), 'reason': reason}
    return rules


def value(account, quotes):
    return account['cash'] + sum(qty * quotes[t]['price'] for t, qty in account['portfolio'].items())


def drawdown(values):
    peak, worst = values[0], 0.
    for v in values:
        peak = max(peak, v)
        worst = min(worst, v / peak - 1)
    return worst


def run_comparison(bot, reference_before, feed, path, now=None):
    """Use this run's observed data; initialize BOTH arms at the same marked account."""
    now = pd.Timestamp(now or datetime.now(timezone.utc))
    path = Path(path)
    state = json.loads(path.read_text()) if path.exists() else None
    if state and state.get('protocol') != PROTOCOL:
        raise ValueError('Experiment protocol changed; use a new state file')
    leads = {}
    for row in feed.get('signals', []):
        if row.get('active'):
            leads.setdefault(row['ticker'], []).append(row)
    universe = list(dict.fromkeys(bot.tickers + list(leads) +
                                 (list(state['account']['portfolio']) + list(state.get('pending', {})) + list(state['seed_portfolio']) if state else [])))
    quotes = deepcopy(bot.last_prices)
    frames, results = {}, {}
    for t in universe:
        try:
            f = bot.fetch_data(t)
            # Yahoo may include today's incomplete daily candle. Analyze the last
            # completed date instead of excluding the whole instrument during market hours.
            f = f.loc[[pd.Timestamp(d).date() < now.date() for d in f.index]]
            if f.empty:
                raise ValueError('No completed daily prices available')
            bar = pd.Timestamp(f.index[-1]).date()
            if not 0 < (now.date() - bar).days <= 7:
                raise ValueError('Need a completed daily price no older than seven days')
            if len(f) < 61 or not all(math.isfinite(float(v)) for v in f[['Close', 'High', 'Volume', 'RSI']].tail(61).to_numpy().flat):
                raise ValueError('Insufficient or invalid strategy data')
            q = bot.price_quote(t, f)
            if not math.isfinite(q['price']) or q['price'] <= 0 or (f.Close.tail(61) <= 0).any():
                raise ValueError('Invalid converted price')
            quotes[t], frames[t] = q, f
        except Exception as exc:
            results[t] = {'ticker': t, 'action': 'NO TRADE', 'reason': str(exc)}
    # No reset after missing prices: postpone initial comparison until seed holdings are priced.
    if not state and any(t not in frames for t in reference_before['portfolio']):
        return {'protocol': PROTOCOL, 'status': 'waiting for valid seed holding prices', 'results': list(results.values())}
    if state is None:
        initial = value(reference_before, quotes)
        state = {'protocol': PROTOCOL, 'started_at': now.isoformat(), 'initial_equity': initial,
                 'account': deepcopy(reference_before), 'seed_portfolio': deepcopy(reference_before['portfolio']),
                 'seed_cash': reference_before['cash'], 'reference_trade_offset': len(reference_before['trade_log']),
                 'experiment_trade_offset': len(reference_before['trade_log']), 'fees': 0., 'history': [], 'pending': {}}
    account = state['account']
    quotes = {**account['last_prices'], **quotes}
    prior_trades = len(account['trade_log'])
    old_pending = state.get('pending', {})
    next_pending = {}
    returns = {t: float(f.Close.iloc[-1] / f.Close.iloc[-61] - 1) for t, f in frames.items()}
    ranks = pd.Series(returns).rank(pct=True).to_dict() if len(returns) >= 5 else {}
    entries = []
    for t, f in frames.items():
        research = bot.research_reports.get(t, {})
        rules = relaxed_signals(f, research, ranks.get(t), now)
        categories = research.get('gate', {}).get('categories', {})
        active = [name for name in NAMES if rules[name]['entry']]
        row = {'ticker': t, 'action': 'NO TRADE', 'strategies': rules,
               'missing_research': [k for k in ('fundamentals', 'earnings', 'analysts', 'news')
                                    if categories.get(k, 'unavailable') == 'unavailable'],
               'research_errors': research.get('errors', {}), 'research_categories': categories,
               'data_date': f.index[-1].isoformat()}
        results[t] = row
        previous = next((x for x in reversed(account['trade_log']) if x['ticker'] == t), None)
        if previous and previous.get('quote', {}).get('data_date') == row['data_date']:
            row['reason'] = 'Already traded on this price date'
            continue
        price = quotes[t]['price']
        if t in account['portfolio']:
            if not previous or previous['action'] != 'PAPER BUY':
                row['reason'] = 'Inherited holding without entry record'
                continue
            strategy = previous.get('strategy')
            # Exits use the original five-strategy thresholds, so relaxed entries do not loosen exits.
            exit_rules = signals(f, research, ranks.get(t), now)
            held = sum(pd.Timestamp(d).date() > pd.Timestamp(previous['quote']['data_date']).date() for d in f.index)
            change = price / previous['price'] - 1
            reason = ('Daily 5% loss exit' if change <= -.05 else 'Daily 10% profit exit' if change >= .10 else
                      '21 trading-day time exit' if held >= 21 else
                      'Strategy exit' if exit_rules.get(strategy, {}).get('exit') else None)
            row['reason'] = reason or 'Hold existing position'
            if reason:
                qty = account['portfolio'].pop(t)
                gross, fee = qty * price, qty * price * COST
                account['cash'] += gross - fee
                state['fees'] += fee
                trade = {'time': now.isoformat(), 'ticker': t, 'action': 'PAPER SELL', 'strategy': strategy,
                         'qty': qty, 'price': price, 'amount': gross, 'cost_usd': fee, 'quote': quotes[t],
                         'realized_pnl': gross - fee - qty * previous['price'] - previous.get('cost_usd', 0.),
                         'reason': reason, 'miljon_signal_ids': previous.get('miljon_signal_ids', [])}
                account['trade_log'].append(trade)
                row.update(action='PAPER SELL', strategy=strategy)
            continue
        eligible = []
        instrument = research.get('instrument', {})
        for lead in leads.get(t, []):
            if (lead['source_status'] == 'checked' and lead['bias'] != 'negative'
                    and stamp(lead['published_at']) <= now.to_pydatetime() < stamp(lead['expires_at'])
                    and max(stamp(lead['published_at']).date(), stamp(lead['source_checked_at']).date()) < pd.Timestamp(f.index[-1]).date()
                    and instrument.get('symbol') == t and instrument.get('quote_type') == 'EQUITY'
                    and instrument.get('exchange') == lead['exchange']
                    and instrument.get('currency') == lead['quote_currency'] == quotes[t].get('quote_currency')):
                eligible.append(lead)
        used = {sid for trade in account['trade_log'] if trade['action'] == 'PAPER BUY'
                for sid in trade.get('miljon_signal_ids', [])}
        eligible = [x for x in eligible if x['id'] not in used]
        catalyst = any(x['bias'] == 'positive' for x in eligible)
        supportive = sum(v == 'supportive' for v in categories.values())
        score = min(100, 10 * len(active) + 15 * supportive + 25 * catalyst)
        row.update(score=score, tier=1 if score >= 65 else 2 if score >= 40 else 3,
                   miljon_signal_ids=[x['id'] for x in eligible], entry_candidates=active,
                   signal_expiries={x['id']: x['expires_at'] for x in eligible})
        identity = (instrument.get('symbol') == t and instrument.get('quote_type') == 'EQUITY'
                    and bool(instrument.get('exchange')) and instrument.get('currency') == quotes[t].get('quote_currency'))
        reason = ('No technical entry rule' if not active else
                  'Instrument identity or quote currency unavailable' if not identity else
                  'No unused, checked, correctly dated instrument-matched feed signal' if t in leads and not eligible else
                  'Negative news or earnings evidence' if any(categories.get(k) == 'negative' for k in ('news', 'earnings')) else
                  'Need one supportive category or a positive checked catalyst' if not supportive and not catalyst else None)
        row['reason'] = reason or 'Eligible for ranked allocation'
        if not reason:
            next_pending[t] = {**row, 'decision_at': now.isoformat()}
            row['reason'] = 'Queued; wait for a completed daily bar after decision date'
    # Execute only decisions recorded on an earlier date, not today's research against yesterday's close.
    # Pending orders are valid for seven days; later research does not retroactively change that decision.
    for t, intent in old_pending.items():
        if t not in frames or t in account['portfolio']:
            if t not in frames and (now - pd.Timestamp(intent['decision_at'])).days < 7:
                next_pending.setdefault(t, intent)
            continue
        age = (now - pd.Timestamp(intent['decision_at'])).days
        if age >= 7:
            continue
        if intent.get('signal_expiries'):
            valid_ids = [sid for sid, expiry in intent['signal_expiries'].items() if now.to_pydatetime() < stamp(expiry)]
            if not valid_ids:
                continue
            intent = {**intent, 'miljon_signal_ids': valid_ids}
        if pd.Timestamp(frames[t].index[-1]).date() <= pd.Timestamp(intent['decision_at']).date():
            next_pending[t] = intent
            continue
        previous = next((x for x in reversed(account['trade_log']) if x['ticker'] == t), None)
        if previous and previous.get('quote', {}).get('data_date') == frames[t].index[-1].isoformat():
            continue
        entries.append((intent['score'], t, deepcopy(intent), frames[t]))
    # Rank before allocation; input file order cannot determine who consumes the cash first.
    for _, t, row, f in sorted(entries, key=lambda x: (-x[0], x[1])):
        q = quotes[t]
        row['decision_data_date'] = row['data_date']
        row['data_date'] = f.index[-1].isoformat()
        results[t] = row
        conversion = q.get('quote_unit_scale', 1.) * q.get('fx_to_usd', 1.)
        turnover = float((f.Close.tail(20) * f.Volume.tail(20)).median()) * conversion
        if not math.isfinite(turnover) or turnover < 25000:
            row['reason'] = 'Median 20-bar USD turnover below 25000 or unavailable'
            continue
        if len(account['portfolio']) >= 20:
            row['reason'] = 'Maximum twenty experiment holdings'
            continue
        budget = min(account['cash'] * (.005 if q['price'] < 5 else .02), turnover * .005)
        amount = budget / (1 + COST)
        if amount < 1:
            row['reason'] = 'Insufficient cash for USD1 position'
            continue
        fee, qty = amount * COST, amount / q['price']
        account['cash'] -= amount + fee
        state['fees'] += fee
        account['portfolio'][t] = qty
        strategy = row['entry_candidates'][0]
        account['trade_log'].append({'time': now.isoformat(), 'ticker': t, 'action': 'PAPER BUY',
                                    'strategy': strategy, 'qty': qty, 'price': q['price'], 'amount': amount,
                                    'cost_usd': fee, 'quote': q, 'miljon_signal_ids': row['miljon_signal_ids'],
                                    'reason': 'Experimental ranked entry; relaxed research and technical rules',
                                    'tier': row['tier'], 'score': row['score'],
                                    'decision_at': row['decision_at'],
                                    'missing_research': row['missing_research'], 'research_errors': row['research_errors']})
        row.update(action='PAPER BUY', strategy=strategy, reason='Experimental ranked entry')
        results[t] = row
        next_pending.pop(t, None)
    state['pending'] = next_pending
    account['last_prices'] = quotes
    reference = snapshot(bot)
    ref_cost = sum(t['amount'] * COST for t in reference['trade_log'][state['reference_trade_offset']:])
    ref_value, exp_value = value(reference, quotes) - ref_cost, value(account, quotes)
    frozen = state['seed_cash'] + sum(q * quotes[t]['price'] for t, q in state['seed_portfolio'].items())
    point = {'at': now.isoformat(), 'reference_net': ref_value, 'experiment_net': exp_value, 'hold_initial_positions': frozen}
    state['history'].append(point)
    metrics = {}
    for key in ('reference_net', 'experiment_net', 'hold_initial_positions'):
        values = [state['initial_equity']] + [h[key] for h in state['history']]
        metrics[key] = {'equity_usd': values[-1], 'return_since_start': values[-1] / values[0] - 1,
                        'max_observed_drawdown': drawdown(values)}
    reference_turnover = ref_cost / COST
    experimental_turnover = state['fees'] / COST
    sensitivity = [{'per_side': rate, 'reference_equity': ref_value + ref_cost - reference_turnover * rate,
                    'experiment_equity': exp_value + state['fees'] - experimental_turnover * rate}
                   for rate in (0., .001, .0025, .005)]
    stale = [t for t in set(reference['portfolio']) | set(account['portfolio']) | set(state['seed_portfolio']) if t not in frames]
    report = {'protocol': PROTOCOL, 'status': 'prospective experiment; no validated advantage', 'policy': POLICY,
              'started_at': state['started_at'], 'initial_equity': state['initial_equity'], 'metrics': metrics,
              'comparison': 'Same initial cash and positions; reference costs estimated on its recorded orders. Hold-initial-positions is a passive internal baseline, not a market index.',
              'cost_sensitivity': sensitivity, 'cost_sensitivity_limit': 'Fixed recorded quantities; not a full rerun of alternative-cost cash paths.',
              'stale_valuation_tickers': stale, 'drawdown_limit': 'Measured at run snapshots; intraday losses may be larger.',
              'remaining_cash': account['cash'], 'portfolio': account['portfolio'],
              'new_trades': account['trade_log'][prior_trades:],
              'trades': account['trade_log'][state['experiment_trade_offset']:],
              'inherited_history_excluded': state['experiment_trade_offset'], 'results': list(results.values()),
              'pending_orders': state['pending'],
              'analyzed': len(frames), 'requested': len(universe), 'history': state['history']}
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(state, indent=2, allow_nan=False))
    temporary.replace(path)
    return report

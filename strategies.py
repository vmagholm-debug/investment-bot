"""Experimental long-only daily rules. Scores are diagnostics, never probabilities."""
from datetime import datetime, timezone
import math
import pandas as pd

NAMES = ('mean_reversion', 'momentum', 'trend_following', 'breakout', 'earnings')


def signals(frame, research, momentum_rank=None, now=None):
    now = pd.Timestamp(now or datetime.now(timezone.utc))
    now = now.tz_localize('UTC') if now.tzinfo is None else now.tz_convert('UTC')
    if len(frame) < 61:
        return {name: {'entry': False, 'exit': False, 'reason': 'Need 61 price observations'} for name in NAMES}
    close = frame.Close.astype(float)
    price, previous = float(close.iloc[-1]), float(close.iloc[-2])
    sma20, sma50 = float(close.tail(20).mean()), float(close.tail(50).mean())
    sd = float(close.tail(20).std())
    z = (price - sma20) / sd if sd > 0 else 0.
    rsi = float(frame.RSI.iloc[-1])
    r20, r60 = price / close.iloc[-21] - 1, price / close.iloc[-61] - 1
    rising50 = sma50 > float(close.iloc[-55:-5].mean())
    high20 = float(frame.High.iloc[-21:-1].max())
    volume_mean = float(frame.Volume.iloc[-21:-1].mean())
    volume_ratio = float(frame.Volume.iloc[-1]) / volume_mean if volume_mean > 0 else 0.
    latest = research.get('earnings', {}).get('latest_report') or {}
    age, surprise = None, latest.get('surprise_fraction')
    if latest.get('date'):
        date = pd.Timestamp(latest['date'])
        date = date.tz_localize('UTC') if date.tzinfo is None else date.tz_convert('UTC')
        age = (now - date).total_seconds() / 86400
    # Do not trade a newly reported result against a close predating its release.
    bar_date = pd.Timestamp(frame.index[-1]).date()
    earnings_after_bar = bool(latest.get('date') and bar_date <= pd.Timestamp(latest['date']).date())
    def result(entry, exit_, reason):
        return {'entry': bool(entry), 'exit': bool(exit_), 'reason': reason}
    return {
        'mean_reversion': result(z <= -1.5 and rsi < 40 and price > previous, price >= sma20,
                                f'z20={z:.2f} (<=-1.5), RSI={rsi:.1f} (<40), rebound={price > previous}; exit at SMA20'),
        'momentum': result(momentum_rank is not None and momentum_rank >= .8 and r60 > .05 and r20 > 0,
                           r20 <= 0, f'60-day return={r60:.1%} (>5%), 20-day={r20:.1%} (>0), peer percentile={momentum_rank}; require >=0.8'),
        'trend_following': result(price > sma20 > sma50 and rising50, price < sma50,
                                 f'Price>SMA20>SMA50={price > sma20 > sma50}, SMA50 rising={rising50}; exit below SMA50'),
        'breakout': result(price > high20 and volume_ratio >= 1.5, price < sma20,
                          f'Close={price:.4f}, prior 20-day high={high20:.4f}, volume multiple={volume_ratio:.2f} (>=1.5); exit below SMA20'),
        'earnings': result(age is not None and 0 <= age <= 7 and not earnings_after_bar and
                           surprise is not None and math.isfinite(surprise) and surprise >= .05 and price > previous,
                           price < sma20, f'EPS surprise={surprise}, age days={age}, post-report bar={not earnings_after_bar}, positive daily reaction={price > previous}; require >=5%, <=7 days; exit below SMA20')}


class StrategyTrading:
    """One position per ticker. Attribution remains fixed until that position closes."""
    def run_once(self, refresh=True):
        if refresh:
            self.data.clear()
        results, frames, ranks = {}, {}, {}
        now = pd.Timestamp.now(tz='UTC')
        for ticker in self.tickers:
            try:
                frame = self.fetch_data(ticker)
                stamp = pd.Timestamp(frame.index[-1])
                stamp = stamp.tz_localize('UTC') if stamp.tzinfo is None else stamp.tz_convert('UTC')
                if not 0 <= (now - stamp).total_seconds() <= 7 * 86400:
                    raise ValueError('Price date is future or older than seven days')
                self.last_prices[ticker] = self.price_quote(ticker, frame)
                price = self.last_prices[ticker]['price']
                if not math.isfinite(price) or price <= 0:
                    raise ValueError('Invalid converted price')
                required = frame[['Close', 'High', 'Volume', 'RSI']].tail(61)
                if not all(math.isfinite(float(v)) for v in required.to_numpy().flat) or (required.Close <= 0).any():
                    raise ValueError('Invalid strategy inputs')
                frames[ticker] = frame
            except Exception as exc:
                results[ticker] = {'ticker': ticker, 'error': str(exc)}
        returns = {t: float(f.Close.iloc[-1] / f.Close.iloc[-61] - 1) for t, f in frames.items() if len(f) >= 61}
        if len(returns) >= 5:
            ranks = pd.Series(returns).rank(method='average', pct=True).to_dict()
        for ticker, frame in frames.items():
            research = self.research_reports.get(ticker, {})
            rules = signals(frame, research, ranks.get(ticker), now)
            try:
                score = self.predict(ticker)['confidence']
            except (ValueError, KeyError):
                score = None  # Learning failure must not prevent a risk exit.
            sig = {'ticker': ticker, 'confidence': score, 'accuracy': None,
                   'historical_mean_21d_return': None, 'strategies': rules,
                   'research_gate': research.get('gate', {'approved': False, 'reason': 'Research unavailable'}),
                   'data_date': frame.index[-1].isoformat(), 'action': 'NO TRADE'}
            results[ticker] = sig
            price = self.last_prices[ticker]['price']
            previous = next((t for t in reversed(self.trade_log) if t['ticker'] == ticker), None)
            if previous and previous.get('quote', {}).get('data_date') == sig['data_date']:
                sig['reason'] = 'Already traded on this price date'
                continue
            if self.portfolio.get(ticker, 0) > 0:
                entry = previous if previous and previous['action'] == 'PAPER BUY' else None
                if not entry:
                    sig['reason'] = 'Legacy holding has no entry record; manual review required'
                    continue
                strategy = entry.get('strategy', 'legacy')
                entry_date = pd.Timestamp(entry.get('quote', {}).get('data_date') or entry['time']).date()
                held = sum(pd.Timestamp(d).date() > entry_date for d in frame.index)
                change = price / entry['price'] - 1
                exit_reason = ('Daily 5% loss exit' if change <= -.05 else
                               'Daily 10% profit exit' if change >= .10 else
                               '21 trading-day time exit' if held >= 21 else
                               'Strategy exit: ' + rules[strategy]['reason'] if strategy in rules and rules[strategy]['exit'] else None)
                if exit_reason:
                    qty = self.portfolio.pop(ticker)
                    amount = qty * price
                    self.cash += amount
                    trade = self._strategy_trade(sig, 'PAPER SELL', strategy, qty, price, amount, exit_reason)
                    trade['realized_pnl'] = amount - qty * entry['price']
                    self.trade_log.append(trade)
                    sig.update(action='PAPER SELL', strategy=strategy, reason=exit_reason)
                else:
                    sig.update(strategy=strategy, reason=f'Hold existing position; return {change:.1%}, {held} trading days')
                continue
            active = [name for name in NAMES if rules[name]['entry']]
            sig['entry_candidates'] = active
            if not active:
                sig['reason'] = 'No strategy entry rule passed'
            elif not sig['research_gate']['approved']:
                sig['reason'] = sig['research_gate']['reason']
            elif len(self.portfolio) >= 10:
                sig['reason'] = 'Maximum ten holdings reached'
            elif self.cash * .02 < 1:
                sig['reason'] = 'Insufficient fake cash for minimum $1 position'
            else:
                # Deterministic priority; overlapping signals do not multiply size.
                strategy = active[0]
                amount = self.cash * .02
                qty = amount / price
                self.cash -= amount
                self.portfolio[ticker] = qty
                self.last_purchase_dates[ticker] = sig['data_date']
                reason = strategy + ': ' + rules[strategy]['reason'] + '; research passed; 2% of available fake cash'
                self.trade_log.append(self._strategy_trade(sig, 'PAPER BUY', strategy, qty, price, amount, reason))
                sig.update(action='PAPER BUY', strategy=strategy, reason=reason)
        return [results[t] for t in self.tickers]

    def _strategy_trade(self, sig, action, strategy, qty, price, amount, reason):
        return {'time': datetime.now(timezone.utc).isoformat(), 'ticker': sig['ticker'],
                'action': action, 'strategy': strategy, 'qty': qty, 'price': price,
                'amount': amount, 'currency': 'USD', 'quote': self.last_prices[sig['ticker']],
                'confidence': sig['confidence'], 'accuracy': None, 'historical_mean_21d_return': None,
                'reason': reason, 'research_gate': sig['research_gate'], 'strategies': sig['strategies']}

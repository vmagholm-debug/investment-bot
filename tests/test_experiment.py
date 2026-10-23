import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

import numpy as np
import pandas as pd

from experiment import run_comparison, snapshot


def bot_for(tickers=('SMALL',), currency='USD', price_scale=1.):
    f = pd.DataFrame({'Close': np.linspace(80, 100, 90), 'High': np.linspace(80, 100, 90) * 1.001,
                      'Volume': 100000., 'RSI': 55.}, index=pd.bdate_range(end='2026-10-20', periods=90, tz='UTC'))
    b = SimpleNamespace(tickers=list(tickers), cash=100000., portfolio={}, trade_log=[], last_prices={},
                        data={t: f.copy() for t in tickers}, research_reports={})
    b.fetch_data = lambda t: b.data[t]
    b.price_quote = lambda t, frame: {'price': float(frame.Close.iloc[-1]) * price_scale,
                                     'data_date': frame.index[-1].isoformat(), 'quote_currency': currency,
                                     'quote_unit_scale': price_scale, 'fx_to_usd': 1.}
    for t in tickers:
        b.research_reports[t] = {'instrument': {'symbol': t, 'exchange': 'LSE' if currency == 'GBp' else 'NMS',
                                               'currency': currency, 'quote_type': 'EQUITY'},
                                 'gate': {'approved': False, 'categories': {'fundamentals': 'unavailable', 'analysts': 'supportive'}},
                                 'errors': {'financials': 'coverage missing'}}
    return b


def advance(b, date='2026-10-21', price=100.):
    for t in b.data:
        f = b.data[t]
        f.loc[pd.Timestamp(date, tz='UTC')] = [price, price * 1.001, 100000., 55.]


def lead(t, **changes):
    return dict({'id': 'lead-' + t, 'ticker': t, 'active': True, 'source_status': 'checked', 'bias': 'positive',
                 'published_at': '2026-10-18T00:00:00Z', 'source_checked_at': '2026-10-19T00:00:00Z',
                 'expires_at': '2026-10-25T00:00:00Z', 'exchange': 'NMS', 'quote_currency': 'USD'}, **changes)


class ExperimentTests(unittest.TestCase):
    def test_relaxed_research_waits_for_future_bar_then_accounts_costs_and_restart(self):
        b = bot_for()
        before = snapshot(b)
        with TemporaryDirectory() as tmp:
            p = Path(tmp) / 'experiment.json'
            first = run_comparison(b, before, {}, p, pd.Timestamp('2026-10-21T08:00Z'))
            self.assertFalse(first['new_trades'])
            self.assertIn('SMALL', first['pending_orders'])
            self.assertEqual(first['metrics']['experiment_net']['return_since_start'], 0)
            repeat = run_comparison(b, before, {}, p, pd.Timestamp('2026-10-21T10:00Z'))
            self.assertFalse(repeat['new_trades'])
            advance(b, '2026-10-22')
            bought = run_comparison(b, before, {}, p, pd.Timestamp('2026-10-23T08:00Z'))
            trade = bought['new_trades'][0]
            self.assertEqual(trade['action'], 'PAPER BUY')
            self.assertLess(pd.Timestamp(trade['decision_at']).date(), pd.Timestamp(trade['quote']['data_date']).date())
            self.assertIn('fundamentals', trade['missing_research'])
            self.assertAlmostEqual(trade['amount'] + trade['cost_usd'], 2000.)
            self.assertAlmostEqual(bought['metrics']['experiment_net']['equity_usd'], 100000 - trade['cost_usd'])
            self.assertEqual(snapshot(b), before)  # Reference account was not mutated.
            again = run_comparison(b, before, {}, p, pd.Timestamp('2026-10-23T10:00Z'))
            self.assertFalse(again['new_trades'])
            advance(b, '2026-10-23', 92.)
            sold = run_comparison(b, before, {}, p, pd.Timestamp('2026-10-24T08:00Z'))
            sale = sold['new_trades'][0]
            self.assertEqual(sale['action'], 'PAPER SELL')
            self.assertAlmostEqual(sale['realized_pnl'], trade['qty'] * -8 - trade['cost_usd'] - sale['cost_usd'])
            self.assertLess(sold['metrics']['experiment_net']['max_observed_drawdown'], 0)

    def test_all_feed_symbols_are_analyzed_no_twelve_cap(self):
        tickers = [f'S{i:02}' for i in range(22)]
        b = bot_for(tickers)
        b.tickers = ['S00']
        with TemporaryDirectory() as tmp:
            report = run_comparison(b, snapshot(b), {'signals': [lead(t) for t in tickers]}, Path(tmp) / 'e.json', pd.Timestamp('2026-10-21T08:00Z'))
            self.assertEqual(report['analyzed'], 22)
            self.assertEqual(len(report['pending_orders']), 22)

    def test_unverified_negative_source_identity_and_news_rejections(self):
        for changes in ({'source_status': 'unverified'}, {'bias': 'negative'}, {'exchange': 'WRONG'},
                        {'source_checked_at': '2026-10-21T00:00:00Z'}):
            b = bot_for()
            with TemporaryDirectory() as tmp:
                r = run_comparison(b, snapshot(b), {'signals': [lead('SMALL', **changes)]}, Path(tmp) / 'e.json', pd.Timestamp('2026-10-21T08:00Z'))
                self.assertFalse(r['pending_orders'])
        b = bot_for()
        b.research_reports['SMALL']['gate']['categories']['news'] = 'negative'
        with TemporaryDirectory() as tmp:
            r = run_comparison(b, snapshot(b), {}, Path(tmp) / 'e.json', pd.Timestamp('2026-10-21T08:00Z'))
            self.assertFalse(r['pending_orders'])

    def test_pence_position_and_liquidity_converted_before_sizing(self):
        b = bot_for(currency='GBp', price_scale=.01)
        with TemporaryDirectory() as tmp:
            p = Path(tmp) / 'e.json'
            run_comparison(b, snapshot(b), {}, p, pd.Timestamp('2026-10-21T08:00Z'))
            advance(b, '2026-10-22')
            r = run_comparison(b, snapshot(b), {}, p, pd.Timestamp('2026-10-23T08:00Z'))
            t = r['new_trades'][0]
            self.assertEqual(t['price'], 1.)
            turnover = float((b.data['SMALL'].Close.tail(20) * b.data['SMALL'].Volume.tail(20)).median()) * .01
            self.assertAlmostEqual(t['amount'] + t['cost_usd'], min(100000 * .005, turnover * .005))

    def test_new_cohort_starts_from_same_positions_excludes_legacy_history(self):
        b = bot_for()
        b.cash = 90000.
        b.portfolio = {'SMALL': 100.}
        b.trade_log = [{'ticker': 'SMALL', 'action': 'PAPER BUY', 'strategy': 'trend_following', 'price': 100.,
                        'qty': 100., 'amount': 10000., 'quote': {'data_date': '2026-10-19T00:00:00+00:00'}}]
        with TemporaryDirectory() as tmp:
            r = run_comparison(b, snapshot(b), {}, Path(tmp) / 'e.json', pd.Timestamp('2026-10-21T08:00Z'))
            self.assertEqual(r['initial_equity'], 100000.)
            self.assertEqual(r['trades'], [])
            for metric in r['metrics'].values():
                self.assertEqual(metric['return_since_start'], 0)

    def test_protocol_mismatch_never_resets_account(self):
        with TemporaryDirectory() as tmp:
            p = Path(tmp) / 'e.json'
            p.write_text(json.dumps({'protocol': 'different'}))
            b = bot_for()
            with self.assertRaises(ValueError):
                run_comparison(b, snapshot(b), {}, p)
            self.assertEqual(json.loads(p.read_text()), {'protocol': 'different'})

    def test_twenty_holdings_cap_and_pending_instrument_stays_in_universe(self):
        tickers = [f'S{i:02}' for i in range(22)]
        b = bot_for(tickers)
        with TemporaryDirectory() as tmp:
            p = Path(tmp) / 'e.json'
            run_comparison(b, snapshot(b), {}, p, pd.Timestamp('2026-10-21T08:00Z'))
            b.tickers = []  # Next discovery page no longer contains yesterday's candidates.
            advance(b, '2026-10-22')
            r = run_comparison(b, snapshot(b), {}, p, pd.Timestamp('2026-10-23T08:00Z'))
            self.assertEqual(len(r['portfolio']), 20)
            self.assertEqual(len(r['new_trades']), 20)
            self.assertGreater(r['remaining_cash'], 0)

    def test_expired_pending_signal_and_missing_seed_price(self):
        b = bot_for()
        with TemporaryDirectory() as tmp:
            p = Path(tmp) / 'e.json'
            feed = {'signals': [lead('SMALL', expires_at='2026-10-22T00:00:00Z')]}
            run_comparison(b, snapshot(b), feed, p, pd.Timestamp('2026-10-21T08:00Z'))
            advance(b, '2026-10-22')
            r = run_comparison(b, snapshot(b), {}, p, pd.Timestamp('2026-10-23T08:00Z'))
            self.assertFalse(r['new_trades'])
        b.portfolio = {'MISSING': 1.}
        with TemporaryDirectory() as tmp:
            p = Path(tmp) / 'e.json'
            r = run_comparison(b, snapshot(b), {}, p, pd.Timestamp('2026-10-23T08:00Z'))
            self.assertIn('waiting', r['status'])
            self.assertFalse(p.exists())

    def test_reference_cost_comparison_from_common_start(self):
        b = bot_for()
        before = snapshot(b)
        b.cash = 98000.
        b.portfolio = {'SMALL': 20.}
        b.trade_log = [{'ticker': 'SMALL', 'action': 'PAPER BUY', 'amount': 2000.}]
        with TemporaryDirectory() as tmp:
            r = run_comparison(b, before, {}, Path(tmp) / 'e.json', pd.Timestamp('2026-10-21T08:00Z'))
            self.assertEqual(r['metrics']['reference_net']['equity_usd'], 99998.)
            self.assertEqual(r['metrics']['experiment_net']['equity_usd'], 100000.)

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
import pandas as pd
from lstm_bot import ContinuousLearner
from strategies import signals, NAMES


def frame(values=None):
    values = np.linspace(80, 100, 90) if values is None else np.asarray(values)
    end = pd.Timestamp.now(tz='UTC').normalize() - pd.Timedelta(days=1)
    f = pd.DataFrame({'Close': values, 'High': values * 1.001, 'Volume': 100., 'RSI': 55.},
                     index=pd.bdate_range(end=end, periods=len(values)))
    return f


class StrategyTests(unittest.TestCase):
    def test_five_entries_and_thresholds(self):
        f = frame()
        f.iloc[-1, f.columns.get_loc('Volume')] = 200
        earnings = {'earnings': {'latest_report': {'date': (f.index[-1] - pd.Timedelta(days=1)).isoformat(), 'surprise_fraction': .1}}}
        s = signals(f, earnings, .9, f.index[-1] + pd.Timedelta(hours=20))
        self.assertEqual(set(s), set(NAMES))
        for name in ('momentum', 'trend_following', 'breakout', 'earnings'):
            self.assertTrue(s[name]['entry'], name)
        self.assertFalse(s['mean_reversion']['entry'])
        f = frame(np.r_[np.full(85, 100.), 94., 91., 88., 85., 86.])
        f['RSI'] = 25.
        self.assertTrue(signals(f, {})['mean_reversion']['entry'])
        self.assertFalse(signals(frame(), {}, .5)['momentum']['entry'])
        self.assertFalse(signals(frame(), {})['breakout']['entry'])
        earnings['earnings']['latest_report']['date'] = f.index[-1].isoformat()
        self.assertFalse(signals(f, earnings, now=f.index[-1] + pd.Timedelta(hours=20))['earnings']['entry'])

    def test_buy_restart_dedup_sell_and_no_same_bar_reentry(self):
        with tempfile.TemporaryDirectory() as tmp:
            bot = ContinuousLearner(['TEST'], Path(tmp) / 'model.pt')
            bot.data['TEST'] = frame()
            bot.research_reports['TEST'] = {'gate': {'approved': True, 'reason': 'Pass'}}
            with patch.object(bot, 'predict', return_value={'confidence': .49}), patch.object(bot, 'price_quote', side_effect=lambda t,f: {'price': float(f.Close.iloc[-1]), 'data_date': f.index[-1].isoformat(), 'quote_currency': 'USD'}):
                bot.run_once(False)
                self.assertEqual(bot.trade_log[-1]['action'], 'PAPER BUY')
                self.assertEqual(bot.cash, 98000.)
                self.assertEqual(bot.trade_log[-1]['strategy'], 'trend_following')
                bot.run_once(False)
                self.assertEqual(len(bot.trade_log), 1)
                path = Path(tmp) / 'state.json'
                bot.save_state(path)
                bot.load_state(path)
                bot.run_once(False)
                self.assertEqual(len(bot.trade_log), 1)
                # Price falls by 8%; execute observed close, not fictional -5% fill.
                f = bot.data['TEST'].copy()
                f.index = f.index - pd.Timedelta(days=1)
                bot.trade_log[-1]['quote']['data_date'] = f.index[-1].isoformat()
                bot.data['TEST'].iloc[-1, bot.data['TEST'].columns.get_loc('Close')] = 92.
                bot.research_reports['TEST']['gate']['approved'] = False
                bot.run_once(False)
                self.assertEqual(bot.trade_log[-1]['action'], 'PAPER SELL')
                self.assertAlmostEqual(bot.trade_log[-1]['realized_pnl'], -160.)
                self.assertEqual(bot.cash, 99840.)
                self.assertFalse(bot.portfolio)
                bot.run_once(False)
                self.assertEqual(len(bot.trade_log), 2)

    def test_research_blocks_and_missing_model_does_not_block_exit(self):
        with tempfile.TemporaryDirectory() as tmp:
            bot = ContinuousLearner(['TEST'], Path(tmp) / 'model.pt')
            bot.data['TEST'] = frame()
            bot.research_reports['TEST'] = {'gate': {'approved': False, 'reason': 'Negative news'}}
            with patch.object(bot, 'price_quote', side_effect=lambda t,f: {'price': float(f.Close.iloc[-1]), 'data_date': f.index[-1].isoformat()}), patch.object(bot, 'predict', side_effect=ValueError('No model')):
                bot.run_once(False)
                self.assertFalse(bot.trade_log)
                bot.research_reports['TEST']['gate']['approved'] = True
                bot.run_once(False)
                self.assertEqual(len(bot.trade_log), 1)
                bot.trade_log[-1]['quote']['data_date'] = bot.data['TEST'].index[-30].isoformat()
                bot.run_once(False)
                self.assertEqual(bot.trade_log[-1]['action'], 'PAPER SELL')
                self.assertIn('21 trading-day', bot.trade_log[-1]['reason'])

    def test_stale_quotes_block_and_portfolio_cap(self):
        with tempfile.TemporaryDirectory() as tmp:
            bot = ContinuousLearner(['TEST'], Path(tmp) / 'model.pt')
            bot.data['TEST'] = frame()
            bot.data['TEST'].index -= pd.Timedelta(days=20)
            self.assertIn('error', bot.run_once(False)[0])
            self.assertFalse(bot.trade_log)
            bot.data['TEST'] = frame()
            bot.portfolio = {str(i): 1 for i in range(10)}
            bot.research_reports['TEST'] = {'gate': {'approved': True, 'reason': 'Pass'}}
            with patch.object(bot, 'price_quote', return_value={'price':100.}), patch.object(bot, 'predict', return_value={'confidence':.99}):
                self.assertIn('ten holdings', bot.run_once(False)[0]['reason'])
                self.assertFalse(bot.trade_log)

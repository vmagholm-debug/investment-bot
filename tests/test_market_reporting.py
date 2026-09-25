import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import pandas as pd
from market import CurrencyConverter
from lstm_bot import ContinuousLearner
from reporting import write_reports


class MarketTests(unittest.TestCase):
    def test_pence_and_euros_convert_to_usd(self):
        converter = CurrencyConverter()
        converter.rates['GBP'] = {'rate': 1.3, 'data_date': '2026-09-25'}
        converter.rates['EUR'] = {'rate': 1.1, 'data_date': '2026-09-25'}
        self.assertAlmostEqual(converter.convert(1000, 'GBp')['price'], 13)
        self.assertAlmostEqual(converter.convert(100, 'EUR')['price'], 110)

    def test_missing_fx_does_not_assume_usd(self):
        with patch('market.yf.download', return_value=pd.DataFrame()):
            with self.assertRaises(ValueError):
                CurrencyConverter().convert(100, 'EUR')

    def test_fake_purchase_uses_converted_price(self):
        with tempfile.TemporaryDirectory() as folder:
            bot = ContinuousLearner(['ASML.AS'], Path(folder) / 'model.pt')
            frame = pd.DataFrame({'Close': [100.]}, index=[pd.Timestamp('2026-09-24')])
            bot.data['ASML.AS'] = frame
            bot.fx.currencies['ASML.AS'] = 'EUR'
            bot.fx.rates['EUR'] = {'rate': 1.1, 'data_date': '2026-09-24'}
            signal = {'ticker': 'ASML.AS', 'direction': 'BUY', 'confidence': .9,
                      'accuracy': None, 'historical_mean_21d_return': .1,
                      'data_date': frame.index[-1].isoformat()}
            with patch.object(bot, 'predict', return_value=signal):
                bot.run_once(refresh=False)
            self.assertAlmostEqual(bot.portfolio['ASML.AS'], 10000 / 110)
            self.assertEqual(bot.cash, 90000)
            self.assertEqual(bot.trade_log[0]['currency'], 'USD')
            self.assertEqual(bot.trade_log[0]['quote']['quote_currency'], 'EUR')

    def test_summary_and_complete_ledger_are_written(self):
        report = {'generated_at': 'today', 'total_account_value': 100000.,
                  'remaining_cash': 100000., 'holdings_value': 0., 'profit_loss': 0.,
                  'coverage': {'europe': 24, 'other': 8}, 'new_trades': [], 'trades': [],
                  'results': [], 'portfolio': {}, 'valuation_prices': {},
                  'training_errors': {}, 'replay_samples': 64,
                  'learning': {'new_samples': 0, 'steps_this_run': 0,
                               'fixed_batch_loss_before': .6, 'fixed_batch_loss_after': .6,
                               'scores_before_update': {}, 'samples_by_ticker': {}}}
        with tempfile.TemporaryDirectory() as folder:
            write_reports(report, folder)
            text = (Path(folder) / 'summary.md').read_text()
            self.assertIn('No model update occurred', text)
            self.assertIn('No simulated purchases', text)
            self.assertTrue((Path(folder) / 'trades.csv').read_text().startswith('time,ticker'))


if __name__ == '__main__':
    unittest.main()

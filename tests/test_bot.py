import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
from bot import TenPercentMonthlyBot


class PaperAccountTests(unittest.TestCase):
    def test_purchase_survives_restart_and_is_not_duplicated(self):
        bot = TenPercentMonthlyBot(['TEST'])
        date = pd.Timestamp('2026-09-24')
        data = pd.DataFrame({'Close': [100.]}, index=[date])
        signal = {'ticker': 'TEST', 'direction': 'BUY', 'confidence': .9,
                  'accuracy': .9, 'historical_mean_21d_return': .2,
                  'data_date': date.isoformat()}
        def fetch(ticker):
            bot.data[ticker] = data
            return data
        with patch.object(bot, 'fetch_data', side_effect=fetch), patch.object(bot, 'predict', return_value=signal):
            self.assertEqual(bot.run_once()[0]['action'], 'PAPER BUY')
        self.assertEqual(bot.cash, 90000.)
        self.assertEqual(bot.portfolio['TEST'], 100.)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'state.json'
            bot.save_state(path)
            restored = TenPercentMonthlyBot(['TEST'])
            restored.load_state(path)
            with patch.object(restored, 'fetch_data', return_value=data), patch.object(restored, 'predict', return_value=signal):
                self.assertEqual(restored.run_once()[0]['reason'], 'Already purchased on this price date')
            self.assertEqual(restored.cash, 90000.)
            self.assertEqual(len(restored.trade_log), 1)

    def test_latest_rows_are_available_without_future_labels(self):
        close = 100 + np.arange(300) * .1
        raw = pd.DataFrame({'Close': close, 'High': close + 1,
                            'Low': close - 1, 'Volume': np.full(300, 1000)},
                           index=pd.bdate_range('2025-01-01', periods=300))
        with patch('bot.yf.download', return_value=raw):
            df = TenPercentMonthlyBot(['TEST']).fetch_data('TEST')
        self.assertEqual(df.index[-1], raw.index[-1])
        self.assertTrue(df['Target'].tail(21).isna().all())
        self.assertFalse(df['Target'].iloc[:-21].isna().any())

    def test_overspending_is_rejected(self):
        bot = TenPercentMonthlyBot(['TEST'])
        with self.assertRaises(ValueError):
            bot.execute({'ticker': 'TEST', 'amount': 100001}, 100)
        self.assertEqual(bot.cash, 100000)
        self.assertEqual(bot.portfolio, {})


if __name__ == '__main__':
    unittest.main()

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
import torch
from lstm_bot import ContinuousLearner


class LSTMTests(unittest.TestCase):
    def test_training_checkpoint_and_new_label_deduplication(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'model.pt'
            bot = ContinuousLearner(['TEST'], path, steps=1)
            rng = np.random.default_rng(42)
            frame = pd.DataFrame(rng.normal(size=(150, 10)), columns=bot.features,
                                 index=pd.bdate_range('2025-01-01', periods=150))
            frame['Target'] = np.arange(150) % 2
            frame.loc[frame.index[-21:], 'Target'] = np.nan
            frame['Forward_Return_21d'] = .12
            with patch.object(bot, 'fetch_data', return_value=frame):
                self.assertEqual(bot.learn(), {})
                first = bot.predict('TEST')['confidence']
                samples = len(bot.buffer)
                bot.learn()
                self.assertEqual(len(bot.buffer), samples)
                self.assertEqual(bot.training_steps, 1)
            self.assertEqual(samples, 100)
            bot.save_model()
            restored = ContinuousLearner(['TEST'], path, steps=1)
            self.assertEqual(restored.training_steps, 1)
            self.assertEqual(len(restored.buffer), samples)
            with patch.object(restored, 'fetch_data', return_value=frame):
                self.assertAlmostEqual(restored.predict('TEST')['confidence'], first)
            self.assertTrue(restored.optimizer.state_dict()['state'])

    def test_constant_features_remain_finite(self):
        values = ContinuousLearner.normalize(np.ones((30, 10)))
        self.assertTrue(np.isfinite(values).all())



if __name__ == '__main__':
    unittest.main()

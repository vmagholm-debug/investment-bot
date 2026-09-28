import tempfile
import unittest
from pathlib import Path
import numpy as np
import pandas as pd
from patterns import PatternLibrary, describe, summarize


def frame(n=300):
    dates=pd.bdate_range('2024-01-01',periods=n)
    return pd.DataFrame({'Close':100*np.exp(np.arange(n)*.001), 'Volume':np.full(n,1000.)},index=dates)


class PatternTests(unittest.TestCase):
    def test_shape_uses_only_past_and_is_price_scale_invariant(self):
        f=frame(); original=describe(f.iloc[:100])
        f.iloc[100:,0]*=100
        self.assertEqual(original,describe(f.iloc[:100]))
        scaled=f.iloc[:100].copy();scaled.Close*=100
        np.testing.assert_allclose(original['vector'],describe(scaled)['vector'],atol=1e-10)

    def test_excludes_same_stock_future_labels_and_overlapping_outcomes(self):
        with tempfile.TemporaryDirectory() as tmp:
            lib=PatternLibrary(Path(tmp)/'patterns.json')
            f=frame();lib.update({'A':f,'B':f,'C':f})
            query=describe(f.iloc[:180]);r=lib.compare('A',query)
            for e in r['examples']:
                self.assertNotEqual(e['ticker'],'A')
                self.assertLess(e['label_end'],query['date'])
            self.assertEqual(r['assessment'],'insufficient_evidence')
            self.assertEqual(lib.update({'A':f,'B':f,'C':f}),0)
            lib.save();self.assertEqual(len(lib.state['records']),len(PatternLibrary(lib.path).state['records']))

    def test_prospective_outcomes_require_future_prices_and_next_close(self):
        with tempfile.TemporaryDirectory() as tmp:
            lib=PatternLibrary(Path(tmp)/'p.json'); f=frame()
            first=lib.analyze({'A':f.iloc[:240],'B':f.iloc[:240]}, {}, now=f.index[239])
            self.assertEqual(first['validation']['settled'],0)
            self.assertEqual(first['validation']['pending'],2)
            lib.analyze({'A':f.iloc[:245],'B':f.iloc[:245]}, {}, now=f.index[244])
            self.assertEqual(len(lib.state['forecasts']),2)
            lib.mature({'A':f,'B':f})
            self.assertEqual(lib.validation()['settled'],2)
            event=lib.state['forecasts'][0]
            self.assertEqual(event['entry_date'],str(f.index[240].date()))
            self.assertEqual(event['outcome_date'],str(f.index[261].date()))
            self.assertAlmostEqual(event['actual_net_return'],float(f.Close.iloc[261]/f.Close.iloc[240]-1-.002))

    def test_missing_stale_and_no_matches_are_not_positive_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            lib=PatternLibrary(Path(tmp)/'p.json');f=frame()
            r=lib.analyze({'A':f.iloc[:5]}, {}, now='2026-01-01')
            self.assertIn('A',r['errors'])
            r=lib.analyze({'A':f}, {}, now='2026-01-01')
            self.assertIn('A',r['errors'])
            r=lib.analyze({'A':f}, {}, now=f.index[-1])
            self.assertEqual(r['results']['A']['matches']['count'],0)
            self.assertEqual(r['results']['A']['combined_assessment'],'research_blocks_purchase')

    def test_extreme_outcomes_are_flagged_not_hidden(self):
        rows=[{'ticker':'A','date':'2024-01-01','returns':{'5':.1,'10':.1,'21':.1},'worst_interim_close_return':-.2},
              {'ticker':'B','date':'2024-02-01','returns':{'5':.1,'10':30.,'21':30.},'worst_interim_close_return':-.2},
              {'ticker':'C','date':'2024-03-01','returns':{'5':.1,'10':.1,'21':.1},'worst_interim_close_return':-.2}]
        s=summarize(rows)
        self.assertEqual(s['count'],3)
        self.assertEqual(s['outcomes']['21']['extreme_outcomes'],1)
        self.assertAlmostEqual(s['outcomes']['21']['median_net_return'],.098)

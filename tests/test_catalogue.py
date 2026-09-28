import unittest
import tempfile
from pathlib import Path
import numpy as np
from catalogue import CATALOGUE, features, assess, PROTOCOL_ID
from patterns import PatternLibrary, summarize
from test_patterns import frame

class CatalogueTests(unittest.TestCase):
    def test_complete_registry_and_evidence_is_not_deployment(self):
        rows=CATALOGUE['families']
        self.assertEqual(len(rows),94)
        self.assertEqual(len({r['id'] for r in rows}),94)
        counts={k:sum(r['literature_evidence']==k for r in rows) for k in ['relatively_strong','mixed','weak','folklore_data_mining']}
        self.assertEqual(list(counts.values()),[30,52,10,2])
        self.assertTrue(all(not r['validated_alpha'] and r['deployment']=='diagnostic_only' for r in rows))

    def test_momentum_skips_recent_month_and_requires_full_lookback(self):
        f=frame(300)
        before=features(f,{})['P1']['values']['momentum_12_minus_1']
        f.iloc[-21:,0]*=2
        self.assertEqual(before,features(f,{})['P1']['values']['momentum_12_minus_1'])
        self.assertNotIn('P1',features(f.iloc[:252],{}))

    def test_missing_data_and_weak_proxies_never_become_votes(self):
        r=assess({'A':frame()}, {})
        self.assertEqual(r['validation_status'],'not_validated')
        self.assertIn('E4',r['results']['A']['unavailable_ids'])
        self.assertNotIn('F2',r['results']['A']['features'])
        self.assertTrue(all(v=='not_demonstrated' for v in r['prerequisites'].values()))
        f=features(frame(),{'fundamentals':{'trailingPE':-3,'priceToBook':2},'financials':{'fresh':False,'net_margin':.2}})
        self.assertNotIn('F2',f);self.assertNotIn('F7',f)
        self.assertEqual(f['F1']['values']['book_to_price'],.5)

    def test_cost_stress_preserves_gross_observation(self):
        row={'ticker':'A','date':'2020-01-01','returns':{'5':.004,'10':.004,'21':.004},'worst_interim_close_return':-.03}
        s=summarize([row])['outcomes']['21']['cost_sensitivity']
        self.assertAlmostEqual(s['0.0']['median_net_return'],.004)
        self.assertAlmostEqual(s['0.01']['median_net_return'],-.006)
        self.assertEqual(row['returns']['21'],.004)

    def test_changed_protocol_cannot_claim_legacy_oos(self):
        with tempfile.TemporaryDirectory() as d:
            p=PatternLibrary(Path(d)/'p.json')
            p.state['forecasts']=[{'ticker':'A','issued_date':'2020-01-01','actual_net_return':.1,'mean_prediction':.1}]
            v=p.validation()
            self.assertEqual(v['settled'],0);self.assertEqual(v['legacy_excluded'],1)
            self.assertEqual(v['protocol_id'],PROTOCOL_ID)

import unittest
from industry_catalogue import analyze_catalogue

class IndustryCatalogueTests(unittest.TestCase):
    def test_all_assumptions_preserved_but_unverified(self):
        r = analyze_catalogue({})
        self.assertEqual(r['coverage']['registered'],351)
        self.assertEqual(r['coverage']['verified_growth_rates'],0)
        ai = next(e for e in r['entries'] if e['name']=='Artificial Intelligence')
        self.assertEqual(ai['supplied_growth_assumption'],.25)
        self.assertIsNone(ai['period'])
        self.assertTrue(all(e['source'] is None for e in r['entries']))

    def test_phrases_and_missing_profiles(self):
        r=analyze_catalogue({'X':{'business_profile':{'summary':'Cloud computing software for boiler maintenance.'}},'Y':{}})
        names={m['industry'] for m in r['matches']}
        self.assertIn('Cloud Computing',names)
        self.assertNotIn('Oil',names)
        self.assertEqual(r['coverage']['with_profile'],1)
        self.assertTrue(all(m['ticker']=='X' for m in r['matches']))

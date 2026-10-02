import unittest
from datetime import datetime,timezone
from investment_analysis import analyze

class InvestmentAnalysisTests(unittest.TestCase):
    def report(self):
        return {'generated_at':'2026-10-02T08:00:00Z','total_account_value':1000,'portfolio':{'A':2},'valuation_prices':{'A':{'price':100,'quote_currency':'SEK'}},'company_research':{'A':{'observed_at':'2026-10-02T08:00:00Z','financials':{'period_end':'2026-06-30T00:00:00Z','revenue_yoy_growth':.2,'net_margin':.1},'fundamentals':{'freeCashflow':-5,'forwardPE':20},'sources':{},'business_profile':{}}}}
    def test_growth_is_not_undervaluation_and_missing_engines_are_visible(self):
        a=analyze(self.report(),datetime(2026,10,2,9,tzinfo=timezone.utc));r=a['companies']['A']
        self.assertIn('Undervärdering är inte visad',r['assessment'])
        self.assertEqual(len(r['engines']),9)
        self.assertEqual(r['engines'][0]['status'],'missing')
        self.assertEqual(r['confidence'],'LOW')
        self.assertEqual([s['value'] for s in r['scenarios']],[None]*3)
        self.assertTrue(any('negativt fritt kassaflöde' in x for x in r['counterarguments']))
        self.assertEqual(a['portfolio']['exposures']['sector']['Okänd sektor'],.2)
    def test_stale_data_cannot_support_current_fundamental_claim(self):
        r=analyze(self.report(),datetime(2027,10,2,tzinfo=timezone.utc))['companies']['A']
        self.assertIn('Insufficient evidence',r['assessment'])
        self.assertFalse(r['evidence_fresh'])
    def test_missing_market_prices_are_not_treated_as_zero_risk(self):
        r=self.report();r['valuation_prices']={}
        a=analyze(r,datetime(2026,10,2,9,tzinfo=timezone.utc))
        self.assertEqual(a['portfolio']['missing_valuations'],['A'])
        self.assertIsNone(a['portfolio']['positions']['A']['weight_of_account'])
    def test_no_input_mutation(self):
        import copy
        r=self.report();before=copy.deepcopy(r);analyze(r)
        self.assertEqual(r,before)

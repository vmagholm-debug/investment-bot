from copy import deepcopy
from datetime import datetime, timezone, timedelta
import tempfile
from pathlib import Path
import unittest
import pandas as pd
from research import evaluate, select_news, statement_metrics, earnings_metrics
from lstm_bot import ContinuousLearner

NOW = datetime(2026, 9, 26, tzinfo=timezone.utc)


def evidence():
    return {'financials': {'fresh': True, 'net_margin': .2,
                           'revenue_yoy_growth': .1, 'net_income_yoy_growth': .15},
            'fundamentals': {'operatingCashflow': 100000,
                             'mostRecentQuarter': datetime(2026, 6, 30, tzinfo=timezone.utc).timestamp()},
            'earnings': {'latest_report': {'surprise_fraction': .1}, 'next_report': None},
            'analysts': {'analyst_count': 10, 'recommendation_mean': 2., 'target_upside': .2},
            'news': [{'sentiment': {'score': .4}}], 'errors': {}}


class ResearchTests(unittest.TestCase):
    def test_strong_technical_signal_cannot_bypass_negative_news(self):
        data = evidence()
        data['news'][0]['sentiment']['score'] = -.6
        gate = evaluate(data, NOW)
        self.assertFalse(gate['approved'])
        self.assertIn('Negative news evidence', gate['blockers'])
        with tempfile.TemporaryDirectory() as folder:
            bot = ContinuousLearner(['TEST'], Path(folder) / 'model.pt')
            self.assertIsNone(bot.advise({'direction': 'BUY', 'confidence': .99, 'research_gate': gate}))

    def test_missing_data_is_not_positive_and_retrieval_errors_block(self):
        data = evidence()
        data['news'] = []
        data['analysts'] = {}
        gate = evaluate(data, NOW)
        self.assertTrue(gate['approved'])  # Dated fundamentals + earnings are supportive.
        self.assertEqual(gate['categories']['news'], 'unavailable')
        self.assertEqual(gate['categories']['analysts'], 'unavailable')
        data['errors']['news'] = 'Provider unavailable'
        self.assertFalse(evaluate(data, NOW)['approved'])
        data = evidence()
        data['financials']['fresh'] = False
        self.assertFalse(evaluate(data, NOW)['approved'])

    def test_imminent_earnings_block_new_purchase(self):
        data = evidence()
        data['earnings']['next_report'] = (NOW + timedelta(days=1)).isoformat()
        self.assertIn('Earnings scheduled within two days', evaluate(data, NOW)['blockers'])

    def test_news_relevance_dates_language_and_deduplication(self):
        def item(title, date, language='en-US', url='https://example.com/story'):
            return {'content': {'title': title, 'summary': 'Quarterly results.',
                                'pubDate': date.isoformat(), 'canonicalUrl': {'url': url, 'lang': language}}}
        items = [item('SAP earnings rise', NOW - timedelta(days=1)),
                 item('SAP earnings rise', NOW - timedelta(days=1)),
                 item('Unrelated company earnings rise', NOW - timedelta(days=1)),
                 item('SAP old story', NOW - timedelta(days=8)),
                 item('SAP future story', NOW + timedelta(days=1)),
                 item('SAP Nachricht', NOW - timedelta(days=1), 'de-DE')]
        result = select_news(items, 'SAP.DE', 'SAP SE', NOW)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['title'], 'SAP earnings rise')

    def test_statements_use_matching_prior_year_and_earnings_use_actuals(self):
        frame = pd.DataFrame({pd.Timestamp('2026-06-30'): [120., 20.],
                              pd.Timestamp('2026-03-31'): [99., 10.],
                              pd.Timestamp('2025-06-30'): [100., 10.]},
                             index=['TotalRevenue', 'NetIncome'])
        metrics = statement_metrics(frame, NOW)
        self.assertAlmostEqual(metrics['revenue_yoy_growth'], .2)
        self.assertAlmostEqual(metrics['net_income_yoy_growth'], 1.)
        dates = pd.DataFrame({'EPS Estimate': [1., 2.], 'Reported EPS': [1.2, float('nan')]},
                             index=[NOW - timedelta(days=30), NOW + timedelta(days=30)])
        earnings = earnings_metrics(dates, NOW)
        self.assertAlmostEqual(earnings['latest_report']['surprise_fraction'], .2)
        self.assertEqual(earnings['next_report'], (NOW + timedelta(days=30)).isoformat())


if __name__ == '__main__':
    unittest.main()

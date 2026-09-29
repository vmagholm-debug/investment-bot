import unittest
from dashboard.build import basis, relevant_title

class DashboardTests(unittest.TestCase):
    def test_remaining_cost_after_partial_sale_and_repurchase(self):
        trades=[{'ticker':'A','action':'PAPER BUY','qty':10,'price':5},
                {'ticker':'A','action':'PAPER SELL','qty':4,'price':8},
                {'ticker':'A','action':'PAPER BUY','qty':2,'price':9}]
        self.assertEqual(basis(trades)['A'],(8,48))
    def test_invalid_ledger_is_not_published_as_valid(self):
        with self.assertRaises(ValueError):
            basis([{'ticker':'A','action':'PAPER SELL','qty':2,'price':9}])

    def test_unrelated_rss_search_hits_are_not_company_news(self):
        self.assertFalse(relevant_title('Aixia Group erhåller order', 'Dynavox Group'))
        self.assertTrue(relevant_title('Dynavox växer på ny marknad', 'Dynavox Group'))

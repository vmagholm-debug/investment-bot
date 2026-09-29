import unittest
from watchlist import load_watchlist, include_watchlist, summarize


class WatchlistTests(unittest.TestCase):
    def test_adds_requested_stocks_without_losing_discovery_or_duplicates(self):
        watch = load_watchlist()
        selected = include_watchlist(['BIRK','NEW'], watch)
        self.assertEqual(set(selected), {'BIRK','NEW','HANZA.ST','DYVOX.ST','NOVT','SKHY'})
        self.assertEqual(selected.count('BIRK'), 1)

    def test_missing_history_and_earnings_not_presented_as_approval(self):
        row = summarize(load_watchlist(), {}, [{'ticker':'SKHY','error':'Insufficient history'}])[3]
        self.assertEqual(row['decision'], 'Insufficient history')
        self.assertIsNone(row['next_report_provider_date'])
        self.assertFalse(row['research_approved'])

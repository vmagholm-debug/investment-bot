import unittest
from market_universe import parse_nasdaq, category


class UniverseTests(unittest.TestCase):
    def test_test_issues_and_footer_not_securities(self):
        rows, stamp = parse_nasdaq('Symbol|Test Issue\nABC|N\nTEST|Y\nFile Creation Time: 0928202621:31|\n')
        self.assertEqual(rows, [{'Symbol': 'ABC', 'Test Issue': 'N'}])
        self.assertIn('09282026', stamp)

    def test_truncated_directory_rejected(self):
        with self.assertRaises(ValueError):
            parse_nasdaq('Symbol|Test Issue\nABC|N\n')

    def test_keep_distinct_instrument_types(self):
        self.assertEqual(category('Example Common Stock'), 'common_or_ordinary_stock')
        self.assertEqual(category('Example Common Stock ETF', True), 'fund_or_etp')
        self.assertEqual(category('Example', issue_type='Preferred Stock'), 'preferred_stock')
        self.assertEqual(category('Example', issue_type='Other'), 'other_or_unclassified')

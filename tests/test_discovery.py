import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from discovery import discover, save_discovery


class DiscoveryTests(unittest.TestCase):
    def test_discovers_new_symbols_and_rotates_previously_selected(self):
        def screen(query, **kwargs):
            europe = 'de' in str(query)
            prefix = 'NEW' if europe else 'WORLD'
            suffix = '.DE' if europe else ''
            return {'total': 500, 'quotes': [
                {'symbol': f'{prefix}{i}{suffix}', 'quoteType': 'EQUITY', 'currency': 'EUR' if europe else 'USD'}
                for i in range(60)]}
        with tempfile.TemporaryDirectory() as folder, patch('discovery.yf.screen', side_effect=screen):
            path = Path(folder) / 'discovery.json'
            first, report, state = discover(path, day='2026-09-25')
            save_discovery(path, state)
            second, _, _ = discover(path, day='2026-09-26')
            self.assertEqual(len(first), 32)
            self.assertEqual(len(report['scans'][0]['selected']), 24)
            self.assertEqual(report['scans'][0]['group'], 'US')
            self.assertEqual(report['scans'][0]['regions'], ['us'])
            self.assertEqual(len(report['scans'][1]['selected']), 8)
            self.assertNotIn('us', report['scans'][1]['regions'])
            self.assertIn('de', report['scans'][1]['regions'])
            self.assertTrue(all(not s.endswith('.DE') for s in report['scans'][0]['selected']))
            self.assertFalse(set(first) & set(second))
            self.assertEqual(state['offsets']['US'], 250)

    def test_failure_does_not_return_static_list(self):
        with tempfile.TemporaryDirectory() as folder, patch('discovery.yf.screen', return_value={}):
            with self.assertRaisesRegex(ValueError, 'no candidates'):
                discover(Path(folder) / 'discovery.json')


if __name__ == '__main__':
    unittest.main()

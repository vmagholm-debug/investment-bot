import unittest
from datetime import date
from themes import analyze_themes

class ThemesTest(unittest.TestCase):
    def test_missing_is_not_negative_evidence(self):
        c = analyze_themes({'X': {}}, date(2026, 9, 29))['companies']['X']
        self.assertFalse(c['profile_available'])
        self.assertEqual(c['matches'], [])
        self.assertIsNone(c['checks']['forward_pe'])

    def test_matching_never_approves_purchase(self):
        c = analyze_themes({'X': {'business_profile': {'summary': 'Produces robotic motion control components.'},
                                  'gate': {'approved': False}}})['companies']['X']
        self.assertEqual(c['matches'][0]['theme_id'], 'robotics')
        self.assertFalse(c['research_approved'])
        self.assertTrue(c['missing'])

    def test_outdated_sources_and_horizons(self):
        r = analyze_themes({}, date(2032, 1, 1))
        self.assertTrue(all(t['needs_source_review'] and t['forecast_expired'] for t in r['themes']))

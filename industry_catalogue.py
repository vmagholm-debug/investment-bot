"""Research leads from user assumptions; deliberately excluded from trade rules."""
import json
import re
from pathlib import Path


def normalized(text):
    return ' '.join(re.findall(r'\w+', str(text).casefold()))


def analyze_catalogue(research):
    catalogue = json.loads(Path(__file__).with_name('industry_catalogue.json').read_text())
    entries = catalogue['entries']
    matches = []
    profiles = 0
    for ticker, report in research.items():
        profile = report.get('business_profile') or {}
        industry, summary = profile.get('industry') or '', profile.get('summary') or ''
        profiles += bool(industry or summary)
        for entry in entries:
            term = normalized(entry['name'])
            fields = [field for field, value in [('industry', industry), ('summary', summary)]
                      if term and (' '+term+' ') in (' '+normalized(value)+' ')]
            if fields:
                matches.append({'ticker': ticker, 'industry': entry['name'], 'matched_fields': fields,
                    'status': 'Possible textual association; revenue exposure not verified',
                    'observed_at': report.get('observed_at'),
                    'next_checks': ['Source and date for market forecast', 'Metric, geography and forecast period',
                                    'Company segment revenue exposure', 'Competition, margins and valuation']})
    return {'provenance': catalogue['provenance'], 'entries': entries, 'matches': matches,
            'policy': 'Forskningskatalog från användaren. Alla tillväxttal är overifierade antaganden; period, mått, geografi och källa saknas. Ingen rangordning, köpregel eller avkastningsprognos använder talen. Överlappande områden räknas inte som oberoende bekräftelser. Textträffar är ledtrådar, inte verifierade intäkter eller bevis på en investerbar marknad.',
            'coverage': {'registered': len(entries), 'verified_growth_rates': 0,
                         'companies': len(research), 'with_profile': profiles, 'text_matches': len(matches)},
            'matching_policy': 'Normalized whole phrases in Yahoo industry/business summary; conservative, no inferred synonyms. No automatic source verification or full-market scan.'}

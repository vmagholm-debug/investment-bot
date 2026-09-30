"""Research leads from user assumptions; deliberately excluded from trade rules."""
import json
import re
from pathlib import Path


def normalized(text):
    return ' '.join(re.findall(r'\w+', str(text).casefold()))


def analyze_catalogue(research):
    catalogue = json.loads(Path(__file__).with_name('industry_catalogue.json').read_text())
    audit = json.loads(Path(__file__).with_name('industry_growth_audit.json').read_text())
    reviews = {e['name']: e for e in audit['entries']}
    entries = [{**e, **reviews[e['name']]} for e in catalogue['entries']]
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
            'audit': {k: v for k, v in audit.items() if k != 'entries'},
            'policy': 'Alla 351 områden har källsökts mot global marknadsomsättning, CAGR 2026–2031. Kandidatkällor är inte automatiskt godkända. Originaltal behålls som antaganden. Källbelagda prognoser är utgivarens uppskattningar, inte säker framtida tillväxt. Inga tal styr köp; överlappande områden är inte oberoende bekräftelser.',
            'coverage': {'registered': len(entries), 'verified_growth_rates': 0, 'source_searched': len(entries),
                         'sourced_forecasts': sum(e['review_status'] == 'sourced_forecast' for e in entries),
                         'companies': len(research), 'with_profile': profiles, 'text_matches': len(matches)},
            'matching_policy': 'Normalized whole phrases in Yahoo industry/business summary; conservative, no inferred synonyms. No automatic source verification or full-market scan.'}

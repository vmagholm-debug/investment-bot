"""Source-dated thematic diagnostics. Never an entry rule or return forecast."""
from datetime import date
from industry_catalogue import analyze_catalogue

THEMES = [
    {'id': 'robotics', 'name': 'Robotik och automation', 'reviewed': '2026-09-29',
     'source_date': '2026-09-24', 'publisher': 'IFR · World Robotics 2026',
     'url': 'https://ifr.org/ifr-press-releases/news/five-million-robots-now-operate-in-factories-globally',
     'observation': 'Över 600 000 industrirobotar installerades globalt 2025; ökningen var 11 %.',
     'forecast': 'IFR prognostiserar 655 000 installationer 2026 och 806 000 år 2029. Detta mäter antal robotar, inte börsavkastning.',
     'horizon_end': 2029,
     'terms': ['robotics', 'robotic', 'robots', 'motion control', 'machine vision', 'industrial automation'],
     'risks': 'Investeringscykler, prispress, konkurrens och regionala skillnader. Ingen källstödd prognos för hela perioden till 2031.'},
    {'id': 'ai_infrastructure', 'name': 'AI, datacenter och elinfrastruktur', 'reviewed': '2026-09-29',
     'source_date': '2026', 'publisher': 'IEA · Key Questions on Energy and AI 2026',
     'url': 'https://www.iea.org/reports/key-questions-on-energy-and-ai/executive-summary',
     'observation': 'Datacenters globala elanvändning ökade 17 % under 2025.',
     'forecast': 'IEA:s centrala prognos är cirka 950 TWh år 2030 mot 485 TWh 2025. Elbehov är inte en prognos för halvledarbolagens omsättning.',
     'horizon_end': 2030,
     'terms': ['data center', 'data centre', 'high-bandwidth memory', 'semiconductor', 'transformers', 'power electronics'],
     'risks': 'Elnäts- och chipbrist, finansiering, effektivare modeller, överinvestering och redan höga aktieförväntningar.'}
]


def analyze_themes(research, now=None):
    today = now or date.today()
    themes = [{**t, 'needs_source_review': (today-date.fromisoformat(t['reviewed'])).days > 180,
               'forecast_expired': today.year > t['horizon_end']} for t in THEMES]
    companies = {}
    for symbol, evidence in research.items():
        profile = evidence.get('business_profile', {})
        description = profile.get('summary') or ''
        text = ' '.join(str(profile.get(k) or '') for k in ['industry', 'summary']).lower()
        matches = []
        for theme in themes:
            hits = [term for term in theme['terms'] if term in text]
            if hits:
                matches.append({'theme_id': theme['id'], 'matched_terms': hits,
                                'status': 'Möjlig koppling i leverantörens bolagsbeskrivning; intäktsandel ej verifierad'})
        f = evidence.get('fundamentals', {})
        checks = {'forward_pe': f.get('forwardPE'), 'trailing_pe': f.get('trailingPE'),
                  'free_cash_flow': f.get('freeCashflow'), 'debt_to_equity': f.get('debtToEquity'),
                  'revenue_growth': f.get('revenueGrowth'), 'financial_currency': evidence.get('financial_currency')}
        companies[symbol] = {'matches': matches, 'profile_available': bool(description),
            'profile_observed_at': evidence.get('observed_at'), 'checks': checks,
            'research_approved': evidence.get('gate', {}).get('approved', False),
            'assessment': ('Utred segmentintäkter och konkurrensfördel innan långsiktig slutsats.' if matches else
                           'Ingen temakoppling hittad.' if description else 'Bolagsbeskrivning saknas; kan inte bedömas.'),
            'missing': ['Verifierad intäktsandel från temat', 'Flerårig segmentprognos',
                        'Värdering mot jämförbara bolag', 'Validerad femårig avkastningsmodell']}
    return {'policy': 'Diagnostisk omvärldsanalys, inte köpsignal. Marknadstillväxt är inte aktieavkastning. Den kortsiktiga boten behåller sina fem strategier och högst 21 handelsdagars innehav.',
            'horizon': '3–5 år; prognoser förlängs inte bortom källornas slutår.',
            'source_policy': 'Manuellt verifierat källregister; omprövning markeras efter 180 dagar. Bolagskoppling och finansiella mått uppdateras vid varje botkörning.',
            'themes': themes, 'companies': companies,
            'industry_catalogue': analyze_catalogue(research),
            'coverage': {'analyzed': len(companies), 'with_profile': sum(c['profile_available'] for c in companies.values()),
                         'possible_matches': sum(bool(c['matches']) for c in companies.values())}}

"""Evidence-led diagnostic analysis. Does not place orders or invent missing inputs.

Uses only each report's dated observations. No retrospective enrichment of history.
"""
from datetime import datetime, timezone
import math

ENGINE_NAMES = ['Makro', 'Bransch', 'Fundamenta', 'Värdering', 'Rapporter och förväntningar',
                'Kvantitativ analys', 'Nyheter och katalysatorer', 'Risk', 'Portfölj']


def numeric(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def age_days(stamp, now):
    try:
        date = datetime.fromisoformat(stamp.replace('Z', '+00:00'))
        if date.tzinfo is None: date = date.replace(tzinfo=timezone.utc)
        return (now-date).total_seconds()/86400
    except (ValueError, TypeError, AttributeError): return None


def analyze(report, now=None):
    now = now or datetime.now(timezone.utc)
    research = report.get('company_research', {})
    decisions = {r['ticker']: r for r in report.get('results', [])}
    total = report.get('total_account_value')
    positions, exposures = {}, {'sector': {}, 'listing_currency': {}}
    missing_values = []
    for ticker, qty in report.get('portfolio', {}).items():
        quote = report.get('valuation_prices', {}).get(ticker, {})
        price = quote.get('price')
        value = qty*price if numeric(qty) and numeric(price) and price > 0 else None
        weight = value/total if value is not None and numeric(total) and total > 0 else None
        positions[ticker] = {'value_usd': value, 'weight_of_account': weight, 'quote_date': quote.get('data_date')}
        if weight is None: missing_values.append(ticker);continue
        sector = research.get(ticker, {}).get('business_profile', {}).get('sector') or 'Okänd sektor'
        currency = quote.get('quote_currency') or 'Okänd valuta'
        for key, label in [('sector', sector), ('listing_currency', currency)]:
            exposures[key][label] = exposures[key].get(label, 0)+weight
    companies = {}
    for ticker, evidence in research.items():
        f=evidence.get('financials') or {}; info=evidence.get('fundamentals') or {}
        profile=evidence.get('business_profile') or {}; earnings=evidence.get('earnings') or {}
        analysts=evidence.get('analysts') or {}; decision=decisions.get(ticker, {})
        gate=evidence.get('gate') or {}; sources=evidence.get('sources') or {}
        observed=evidence.get('observed_at'); age=age_days(observed, now)
        usable = age is not None and 0 <= age <= 7
        period_age=age_days(f.get('period_end'),now)
        fresh_financials=usable and period_age is not None and 0 <= period_age <= 180
        facts=[]
        def fact(id, label, value, unit, source, period=None):
            if value is None: return
            if isinstance(value,(int,float)) and not numeric(value): return
            facts.append({'id':id,'label':label,'value':value,'unit':unit,
                          'observed_at':observed,'period':period,'source':sources.get(source),
                          'source_type':'Yahoo structured provider data; primary filing not checked',
                          'freshness':'stale_or_unknown' if not usable else 'observed_within_7_days'})
        for key,label,unit in [('revenue','Omsättning',evidence.get('financial_currency')),
                               ('net_income','Nettovinst',evidence.get('financial_currency')),
                               ('net_margin','Nettomarginal','fraction'),('revenue_yoy_growth','Omsättning år/år','fraction')]:
            fact(key,label,f.get(key),unit,'financials',f.get('period_end'))
        for key,label in [('trailingPE','P/E historisk'),('forwardPE','P/E framåtblickande'),('debtToEquity','Skuld/eget kapital enligt Yahoo')]:
            fact(key,label,info.get(key),'provider ratio','fundamentals')
        fact('freeCashflow','Fritt kassaflöde, leverantörssnapshot',info.get('freeCashflow'),evidence.get('financial_currency'),'fundamentals')
        latest=earnings.get('latest_report') or {}
        fact('eps_surprise','Senaste EPS-överraskning',latest.get('surprise_fraction'),'fraction','earnings',latest.get('date'))
        fact('analyst_target','Analytikernas genomsnittliga kursmål',analysts.get('mean_target'),analysts.get('quote_currency'),'analysts')
        fact('analyst_count','Antal analytiker',analysts.get('analyst_count'),'count','analysts')
        growth=f.get('revenue_yoy_growth');margin=f.get('net_margin');fcf=info.get('freeCashflow')
        observations=[];counter=[];monitor=[]
        if numeric(growth):
            observations.append(f"Rapporterad omsättning ändrades {growth:+.1%} år/år för perioden {f.get('period_end')}.")
            counter.append('Omsättningstillväxten kan bero på förvärv, valuta eller pris; organisk volymtillväxt är inte fastställd.')
            monitor.append({'metric':'revenue_yoy_growth','latest':growth,'review_trigger':'Negativ årstillväxt i en ny, jämförbar rapport försvagar tillväxthypotesen; kontrollera även organisk tillväxt.'})
        if numeric(margin):
            observations.append(f"Nettomarginalen för samma period var {margin:.1%}.")
            monitor.append({'metric':'net_margin','latest':margin,'review_trigger':'Fallande marginal i nästa jämförbara rapport kräver omprövning; negativ marginal motsäger lönsamhetshypotesen.'})
        if numeric(fcf) and fcf < 0:
            counter.append('Leverantören visar negativt fritt kassaflöde. Period, investeringar och rörelsekapital måste kontrolleras i kassaflödesrapporten.')
        counter += ['En bra verksamhet kan vara för dyr. Peer-värdering och marknadens implicita tillväxt är inte fastställda.',
                    'Kursmomentum kan vända utan att den långsiktiga verksamheten ändras.']
        supportive = fresh_financials and numeric(growth) and growth>0 and numeric(margin) and margin>0
        negative = fresh_financials and ((numeric(growth) and growth<0) or (numeric(margin) and margin<0))
        assessment = ('Preliminärt stöd för växande, lönsam verksamhet. Undervärdering är inte visad.' if supportive else
                      'Tillgänglig rapport visar svaghet i omsättning eller nettomarginal. En återhämtningstes behöver ytterligare stöd.' if negative else
                      'Insufficient evidence för en fundamental slutsats med tillräckligt färskt underlag.')
        confidence = 'LOW'  # One provider, no primary-source triangulation; never a probability.
        engines = [
            {'name':'Makro','status':'missing','observed':{},'missing':['Daterad inflation/tillväxt och regim','Fed/ECB/BoJ, realräntor och förväntad räntebana','Likviditet, kreditspreadar, råvaror och historiska regimjämförelser']},
            {'name':'Bransch','status':'partial' if profile else 'missing','observed':profile,'missing':['Verifierad segmentexponering och TAM','Minst tre relevanta konkurrenter','Marknadsandel, pricing power och värdekedja']},
            {'name':'Fundamenta','status':'partial' if f else 'missing','observed':f,'missing':['3/5/10-årshistorik','Kassaflöde och resultat för identiska perioder','ROIC/WACC, skuldens förfall, kapitalallokering och redovisningskontroller']},
            {'name':'Värdering','status':'partial' if any(numeric(info.get(k)) for k in ['trailingPE','forwardPE','priceToBook']) else 'missing',
             'observed':{k:info.get(k) for k in ['trailingPE','forwardPE','priceToBook']},'missing':['Historiska och relevanta peer-multiplar','DCF/reverse DCF med underbyggda kassaflöden, WACC och terminalantaganden']},
            {'name':'Rapporter och förväntningar','status':'partial' if latest else 'missing','observed':{'earnings':earnings,'analysts':analysts},
             'missing':['8–12 kvartal och datumkorrekta kursreaktioner','Omsättnings-/EBITDA-konsensus, guidance och estimatrevideringar 1/3/6 månader']},
            {'name':'Kvantitativ analys','status':'partial' if decision.get('strategies') else 'missing','observed':decision.get('strategies',{}),
             'missing':['Index-/sektorrelativ styrka','Bredd, optioner och positionering','Oberoende validerad prognosförmåga']},
            {'name':'Nyheter och katalysatorer','status':'partial' if evidence.get('news') or earnings.get('next_report') else 'missing',
             'observed':{'next_report_provider_date':earnings.get('next_report'),'news':evidence.get('news',[])},
             'missing':['Bolagsbekräftat rapportdatum','Verifierad ny information om kassaflöden eller förväntningar; sentiment räcker inte']},
            {'name':'Risk','status':'partial','observed':{'purchase_checks':gate,'counterarguments':counter},
             'missing':['Refinansiering, redovisning, kund-/leverantörskoncentration','Likviditets-/exekveringskostnad','Regulatoriska, geopolitiska och andra svansrisker']},
            {'name':'Portfölj','status':'partial','observed':positions.get(ticker,{'weight_of_account':0}),
             'missing':['Korrelation, beta och gemensamma faktorberoenden','Verksamhetens geografiska och ekonomiska valutaexponering; noteringsvaluta är inte samma sak']}]
        scenarios=[]
        for name,assumptions,trigger in [
            ('Bull','Tillväxt och marginaler blir bättre än framtida verifierad konsensus utan att kassakonverteringen försämras.','Ny jämförbar rapport och konsensusdata ger stöd för båda villkoren.'),
            ('Base','Senaste observerade verksamhetsnivå används som referens, inte som prognos. Inget förväntningsgap antas.','Nya rapporter avgör om nivån håller.'),
            ('Bear','Omsättning eller marginal försvagas samtidigt som kassaflöde eller finansiering försämras.','Negativ årstillväxt, negativ marginal eller belagd refinansieringsrisk.')]:
            scenarios.append({'name':name,'type':'conditional_research_scenario','assumptions':assumptions,'trigger':trigger,
                              'revenue':None,'margin':None,'eps_or_fcf':None,'valuation_multiple':None,'value':None,
                              'reason_unquantified':'Insufficient evidence: periodmatchad kassaflödesmodell, konsensus och värderingsantaganden saknas.'})
        companies[ticker]={'company':evidence.get('company',ticker),'as_of':observed,'confidence':confidence,
            'confidence_reason':'En leverantör; primärkällor och oberoende bekräftelser saknas. Kvalitetsbedömning, inte sannolikhet för vinst.',
            'assessment':assessment,'evidence_fresh':usable,'facts':facts,
            'chain':{'data':[x['id'] for x in facts],'observation':observations,
                     'interpretation':assessment,'hypothesis':'Testa om verksamheten kan överträffa de förväntningar som motiverar dagens pris.',
                     'scenario':'Villkorade bull/base/bear-scenarier nedan; inga målnivåer utan antaganden.',
                     'investment_consequence':'Behåll som forskningsunderlag. En avvikelse mot marknadens förväntningar är ännu inte belagd.'},
            'market_belief':'Insufficient evidence: analytikermål är inte ett mått på vad hela marknaden prisar.',
            'variant_perception':'Ej fastställd; ingen över-/undervärdering hävdas.',
            'engines':engines,'counterarguments':counter,'scenarios':scenarios,
            'invalidation':monitor or [{'metric':None,'review_trigger':'Definiera en mätbar bolagstes när aktuella finansiella rapporter finns.'}],
            'next_research':[{'priority':1,'question':'Vad måste dagens pris förutsätta om framtida kassaflöden?', 'decision_value':'Kan ändra slutsatsen om värdering; kräver periodmatchade kassaflöden och reverse DCF.'},
                             {'priority':2,'question':'Bekräftar primärrapporten organisk tillväxt, marginaler och kassakonvertering?', 'decision_value':'Kan bekräfta eller kullkasta verksamhetshypotesen.'},
                             {'priority':3,'question':'Vad förväntar sig konsensus inför nästa rapport och hur har det ändrats?', 'decision_value':'Avgör om utvecklingen avviker från förväntningar.'}],
            'horizons':{'0–3 månader':'Befintliga fem handelsstrategier och kommande rapport; daglig prövning.',
                        '3–18 månader':'Ej validerad prognos; kräver estimat och värderingsmodell.',
                        '2–10 år':'Branschhypoteser; kräver konkurrens- och segmentanalys. Ändrar inte botens korta innehavstid.'},
            'retrieval_errors':evidence.get('errors',{})}
    return {'version':1,'computed_at':now.isoformat(),'source_report_time':report.get('generated_at'),
            'policy':'Evidensbaserat diagnostiskt analyslager enligt användarens forskningspolicy. Delvis implementerat; inga nio fullständiga datamotorer utlovas. Påverkar inte order, strategi eller modellträning.',
            'source_policy':'Primärkällor prioriteras vid fortsatt research. Nuvarande fakta kommer från strukturerade Yahoo-data och rubriker/leverantörssammanfattningar; inga fullständiga rapporter eller artiklar har lästs.',
            'companies':companies,'portfolio':{'exposures':exposures,'positions':positions,'missing_valuations':missing_values,
                'basis':'Andel av hela rapportkontot i USD; kassa ingår i nämnaren. Noteringsvaluta mäter inte verksamhetens valutarisk. Okända sektorer redovisas separat.'}}

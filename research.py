"""Current public-company evidence and explicit experimental paper-trade gates.

This information is observed now, never injected into past LSTM training rows.
News analysis covers provider headlines/summaries, not full paywalled articles.
"""
from datetime import datetime, timezone
import math
from pathlib import Path
import re
from urllib.parse import quote, urlparse

import pandas as pd
import torch
import yfinance as yf

MODEL_ID = 'ProsusAI/finbert'
MODEL_REVISION = '4556d13015211d73dccd3fdd39d39232506f3e43'


def number(value):
    try:
        parsed = float(value)
        return parsed if math.isfinite(parsed) else None
    except (ValueError, TypeError):
        return None


def timestamp(value):
    try:
        date = pd.to_datetime(value, utc=True)
        return None if pd.isna(date) else date.to_pydatetime()
    except (ValueError, TypeError):
        return None


def safe_url(value):
    return value if isinstance(value, str) and urlparse(value).scheme in ('http', 'https') else None


class FinancialSentiment:
    def __init__(self, cache_dir):
        self.cache_dir = str(cache_dir)
        self.tokenizer = self.model = None

    def score(self, texts):
        if self.model is None:
            from transformers import AutoTokenizer, AutoModelForSequenceClassification
            self.tokenizer = AutoTokenizer.from_pretrained(MODEL_ID, revision=MODEL_REVISION,
                                                          cache_dir=self.cache_dir, trust_remote_code=False)
            self.model = AutoModelForSequenceClassification.from_pretrained(
                MODEL_ID, revision=MODEL_REVISION, cache_dir=self.cache_dir, trust_remote_code=False)
            self.model.eval()
        results = []
        for offset in range(0, len(texts), 8):
            encoded = self.tokenizer(texts[offset:offset + 8], padding=True, truncation=True,
                                     max_length=256, return_tensors='pt')
            with torch.no_grad():
                probabilities = self.model(**encoded).logits.softmax(dim=-1)
            for row in probabilities:
                values = {self.model.config.id2label[i].lower(): float(v) for i, v in enumerate(row)}
                results.append({**values, 'score': values['positive'] - values['negative']})
        return results


def select_news(items, symbol, company_name, now):
    # Require a ticker or company-name mention. A ticker-associated feed alone can
    # contain market-wide or unrelated stories; those must not drive this stock.
    base = symbol.split('.')[0]
    names = [re.sub(r'\b(SE|PLC|INC|CORPORATION|CORP|LTD|LIMITED|AG|AB|SA|NV)\b', '',
                    company_name, flags=re.I).strip()]
    terms = [name for name in names if len(name) >= 3]
    if len(base) >= 3 and not base.isdigit():
        terms.append(base)
    result, seen = [], set()
    for item in items or []:
        content = item.get('content', item)
        title = content.get('title', '')
        summary = content.get('summary', '') or content.get('description', '')
        text = title + '. ' + summary
        date = timestamp(content.get('pubDate') or content.get('displayTime'))
        if not date and item.get('providerPublishTime'):
            date = datetime.fromtimestamp(item['providerPublishTime'], timezone.utc)
        canonical = content.get('canonicalUrl') or {}
        url = safe_url(canonical.get('url') if isinstance(canonical, dict) else canonical)
        url = url or safe_url(content.get('link'))
        language = canonical.get('lang', '') if isinstance(canonical, dict) else ''
        if not date or not 0 <= (now - date).total_seconds() <= 7 * 86400:
            continue
        if not language.lower().startswith('en'):
            continue  # English FinBERT; do not pretend to analyze other languages.
        if not any(re.search(r'(?<!\w)' + re.escape(term) + r'(?!\w)', text, re.I) for term in terms):
            continue
        key = url or title.casefold()
        if key in seen or not title:
            continue
        seen.add(key)
        result.append({'title': title, 'summary': summary[:1500], 'url': url,
                       'published_at': date.isoformat(),
                       'provider': (content.get('provider') or {}).get('displayName', 'Yahoo Finance'),
                       'text_scope': 'headline and provider summary'})
    return result[:8]


def statement_metrics(frame, now):
    if frame is None or frame.empty:
        return {}
    columns = sorted([c for c in frame.columns if timestamp(c) and timestamp(c) <= now], reverse=True)
    if not columns:
        return {}
    latest = columns[0]
    def value(row, column):
        return number(frame.loc[row, column]) if row in frame.index else None
    revenue, income = value('TotalRevenue', latest), value('NetIncome', latest)
    previous_year = next((c for c in columns[1:] if 330 <= (timestamp(latest) - timestamp(c)).days <= 400), None)
    metrics = {'period_end': timestamp(latest).isoformat(),
               'fresh': 0 <= (now - timestamp(latest)).days <= 180,
               'revenue': revenue, 'net_income': income,
               'net_margin': income / revenue if income is not None and revenue and revenue > 0 else None}
    for row, key in [('TotalRevenue', 'revenue_yoy_growth'), ('NetIncome', 'net_income_yoy_growth')]:
        current = value(row, latest)
        prior = value(row, previous_year) if previous_year is not None else None
        metrics[key] = (current - prior) / abs(prior) if current is not None and prior is not None and prior != 0 else None
    return metrics


def earnings_metrics(frame, now):
    result = {'latest_report': None, 'next_report': None}
    if frame is None or frame.empty:
        return result
    for index, row in frame.iterrows():
        date = timestamp(index)
        if not date:
            continue
        if date > now:
            if not result['next_report'] or date < timestamp(result['next_report']):
                result['next_report'] = date.isoformat()
            continue
        estimate, actual = number(row.get('EPS Estimate')), number(row.get('Reported EPS'))
        if actual is None or (now - date).days > 180:
            continue
        if not result['latest_report'] or date > timestamp(result['latest_report']['date']):
            result['latest_report'] = {'date': date.isoformat(), 'eps_estimate': estimate,
                                       'reported_eps': actual,
                                       'surprise_fraction': (actual - estimate) / abs(estimate)
                                       if estimate is not None and estimate != 0 else None}
    return result


def evaluate(evidence, now):
    categories, reasons, blockers = {}, [], []
    statement = evidence['financials']
    info = evidence['fundamentals']
    # Use dated financial statements to establish recency of financial evidence.
    if statement.get('fresh'):
        values = [statement.get('net_margin'), statement.get('revenue_yoy_growth')]
        cashflow = info.get('operatingCashflow')
        quarter = info.get('mostRecentQuarter')
        if quarter and 0 <= (now - datetime.fromtimestamp(quarter, timezone.utc)).days <= 180:
            values.append(cashflow)
        known = [v for v in values if v is not None]
        positive, negative = sum(v > 0 for v in known), sum(v < 0 for v in known)
        categories['fundamentals'] = 'supportive' if positive >= 2 and negative == 0 else 'negative' if negative >= 2 else 'mixed'
    else:
        categories['fundamentals'] = 'unavailable'
    latest = evidence['earnings'].get('latest_report') or {}
    surprise = latest.get('surprise_fraction')
    earnings_growth = statement.get('net_income_yoy_growth') if statement.get('fresh') else None
    known = [v for v in [surprise, earnings_growth] if v is not None]
    categories['earnings'] = ('negative' if any(v < -.05 for v in known) else
                              'supportive' if any(v > 0 for v in known) else 'mixed') if known else 'unavailable'
    next_report = timestamp(evidence['earnings'].get('next_report'))
    if next_report and 0 <= (next_report - now).total_seconds() <= 2 * 86400:
        blockers.append('Earnings scheduled within two days')
    analyst = evidence['analysts']
    recommendation, upside = analyst.get('recommendation_mean'), analyst.get('target_upside')
    if (analyst.get('analyst_count') or 0) >= 3 and recommendation is not None and upside is not None:
        categories['analysts'] = ('negative' if recommendation >= 3.5 or upside < -.05 else
                                  'supportive' if recommendation <= 2.5 and upside >= .05 else 'mixed')
    else:
        categories['analysts'] = 'unavailable'
    scores = [item['sentiment']['score'] for item in evidence['news'] if 'sentiment' in item]
    average = sum(scores) / len(scores) if scores else None
    evidence['news_mean_sentiment'] = average
    categories['news'] = ('negative' if average <= -.25 else 'supportive' if average >= .15 else 'mixed') if average is not None else 'unavailable'
    for category, status in categories.items():
        reasons.append(f'{category}: {status}')
        if status == 'negative':
            blockers.append(f'Negative {category} evidence')
    if categories['fundamentals'] != 'supportive':
        blockers.append('Need supportive recent fundamentals')
    if sum(status == 'supportive' for status in categories.values()) < 2:
        blockers.append('Need at least two supportive research categories')
    if evidence['errors']:
        blockers.append('Research retrieval or sentiment-analysis error; no purchase approved')
    return {'approved': not blockers, 'categories': categories, 'blockers': blockers,
            'reason': '; '.join(blockers or reasons),
            'policy': 'Experimental research gate v1; not a calibrated return forecast'}


class CompanyResearch:
    def __init__(self, cache_dir=Path('.cache/finbert'), sentiment=None):
        self.sentiment = sentiment or FinancialSentiment(cache_dir)

    def collect(self, symbol):
        now = datetime.now(timezone.utc)
        ticker = yf.Ticker(symbol)
        errors = {}
        def fetch(name, operation, fallback):
            try:
                return operation()
            except Exception as exc:
                errors[name] = str(exc)
                return fallback
        info = fetch('fundamentals', ticker.get_info, {}) or {}
        financials = fetch('quarterly_income_statement', lambda: ticker.get_income_stmt(freq='quarterly'), None)
        earnings = fetch('earnings_dates', lambda: ticker.get_earnings_dates(limit=8), None)
        news = fetch('news', lambda: ticker.get_news(count=20), [])
        articles = select_news(news, symbol, info.get('longName') or info.get('shortName') or symbol, now)
        if articles:
            scores = fetch('news_sentiment', lambda: self.sentiment.score([
                article['title'] + '. ' + article['summary'] for article in articles]), [])
            for article, sentiment in zip(articles, scores):
                article['sentiment'] = sentiment
        price, target = number(info.get('currentPrice')), number(info.get('targetMeanPrice'))
        upside = target / price - 1 if price and price > 0 and target and target > 0 else None
        # Reject suspicious unit mismatches (e.g. pence vs pounds), don't infer conversions.
        if upside is not None and not -.8 <= upside <= 5:
            upside = None
        evidence = {'symbol': symbol, 'company': info.get('longName') or symbol,
                    'observed_at': now.isoformat(), 'errors': errors,
                    'fundamentals': {key: number(info.get(key)) for key in [
                        'marketCap', 'trailingPE', 'forwardPE', 'priceToBook', 'debtToEquity',
                        'profitMargins', 'revenueGrowth', 'earningsGrowth', 'operatingCashflow',
                        'freeCashflow', 'mostRecentQuarter']},
                    'financial_currency': info.get('financialCurrency'),
                    'financials': statement_metrics(financials, now),
                    'earnings': earnings_metrics(earnings, now),
                    'analysts': {'analyst_count': number(info.get('numberOfAnalystOpinions')),
                                 'recommendation_mean': number(info.get('recommendationMean')),
                                 'mean_target': target, 'current_price': price, 'target_upside': upside,
                                 'quote_currency': info.get('currency'),
                                 'horizon': 'Analyst target horizon, typically 12 months; not the 21-day LSTM horizon',
                                 'coverage_date': 'Provider snapshot at retrieval; individual recommendation dates unavailable'},
                    'news': articles, 'news_model': MODEL_ID, 'news_model_revision': MODEL_REVISION,
                    'news_scope': 'Relevant English headlines/provider summaries published within seven days; no full article retrieval',
                    'sources': {name: f'https://finance.yahoo.com/quote/{quote(symbol, safe="")}/{suffix}'
                                for name, suffix in [('fundamentals', 'key-statistics/'),
                                                     ('financials', 'financials/'), ('earnings', 'calendar/'),
                                                     ('analysts', 'analysis/'), ('news', 'news/')]}}
        evidence['gate'] = evaluate(evidence, now)
        return evidence

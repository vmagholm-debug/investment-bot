"""Factual human-readable and machine-readable paper account reports."""
import csv
import html
import os
from pathlib import Path


def table(headers, rows):
    def cell(value):
        return str(value).replace('|', '/').replace('\n', ' ')
    return '\n'.join(['| ' + ' | '.join(headers) + ' |',
                      '| ' + ' | '.join(['---'] * len(headers)) + ' |'] +
                     ['| ' + ' | '.join(cell(v) for v in row) + ' |' for row in rows])


def write_reports(report, directory):
    directory = Path(directory)
    learning = report['learning']
    new_trades = report['new_trades']
    lines = ['# Europe-first paper-trading report', '',
             f"Generated: {report['generated_at']}. All money and trades are simulated.", '',
             f"**Account: ${report['total_account_value']:,.2f} USD** · "
             f"Cash: ${report['remaining_cash']:,.2f} · "
             f"Holdings: ${report['holdings_value']:,.2f} · "
             f"P/L since start: ${report['profit_loss']:,.2f}", '',
             f"Coverage: {report['coverage']['europe']} European and {report['coverage']['other']} other listings. "
             'Discovered live from Yahoo Finance; European listings are considered first.', '',
             '## New simulated trades', '']
    if new_trades:
        lines += [table(['Time', 'Ticker', 'Action', 'Shares', 'USD/share', 'Fake USD spent', 'Score', 'Reason'],
                        [[t['time'], t['ticker'], t['action'], f"{t['qty']:.6f}",
                          f"{t['price']:.4f}", f"{t.get('amount', t['qty'] * t['price']):.2f}",
                          f"{t['confidence']:.4f}", t.get('reason', '')] for t in new_trades]), '']
    else:
        lines += ['No simulated purchases this run. See the signal table for scores, filters, and errors.', '']
    lines += ['## What changed in training', '',
              f"Added **{learning['new_samples']} newly labeled examples** and performed "
              f"**{learning['steps_this_run']} training updates**. Replay buffer: {report['replay_samples']} examples.", '']
    before, after = learning['fixed_batch_loss_before'], learning['fixed_batch_loss_after']
    if before is not None and after is not None:
        lines += [f"Error on the same recent training batch: **{before:.5f} → {after:.5f}** (lower is better).", '']
    if not learning['steps_this_run']:
        lines += ['No model update occurred this run; no new learning is claimed.', '']
    lines += ['These measure fit to training data, not predictive accuracy on unseen data. '
              'A model score is uncalibrated and does not prove a 10% return is likely. '
              'The model does not establish causal explanations for market moves.', '',
              table(['Ticker', 'New examples', 'Known 21-day outcomes', 'Outcomes reaching +10%'],
                    [[t, d['new_samples'], d['known_outcomes'], d['target_reached']]
                     for t, d in learning['samples_by_ticker'].items()]), '',
              '## Signals and decisions', '',
              table(['Ticker', 'Score before training', 'Score after training', 'Action / reason'],
                    [[s['ticker'], f"{learning['scores_before_update'][s['ticker']]:.4f}" if s['ticker'] in learning['scores_before_update'] else 'Unavailable',
                      f"{s['confidence']:.4f}" if 'confidence' in s else 'Unavailable',
                      s.get('error', s.get('action', '')) + (' — ' + s['reason'] if s.get('reason') else '')]
                     for s in report['results']]), '', '## Holdings', '']
    if report['portfolio']:
        lines += [table(['Ticker', 'Shares', 'USD/share', 'Fake USD value', 'Price date', 'Quote currency'],
                        [[t, f'{qty:.6f}', f"{report['valuation_prices'][t]['price']:.4f}",
                          f"{qty * report['valuation_prices'][t]['price']:.2f}",
                          report['valuation_prices'][t]['data_date'], report['valuation_prices'][t].get('quote_currency', 'USD')]
                         for t, qty in report['portfolio'].items()]), '']
    else:
        lines += ['No holdings yet.', '']
    lines += ['## Complete trade history', '',
              f"{len(report['trades'])} total simulated trades. Download `trades.csv` or `latest.json` in the "
              '`paper-trading-report` artifact for the complete ledger, including prior runs.', '',
              'Foreign quotes are converted to fake USD using dated FX prices. UK pence are divided by 100 first. '
              'If a price or FX lookup fails, no purchase is made for that ticker; any prior valuation is stale. '
              'This simulation is buy-only and does not model fees, slippage or dividend cash payments.', '']
    if report['training_errors']:
        lines += ['## Training errors', '', str(report['training_errors']), '']
    lines += ['## Live stock discovery', '']
    for scan in report.get('discovery', {}).get('scans', []):
        lines += [f"{scan['group']}: {scan['matching_stocks']} matching stocks; "
                  f"{scan['unique_candidates_fetched']} candidates fetched; "
                  f"{len(scan['selected'])} selected for detailed analysis.", '']
    lines += ['The screener refreshes on every run, advances through result pages, and prefers stocks '
              'not recently analyzed. Company research uses Yahoo financial data and relevant news summaries.', '']
    research = report.get('company_research', {})
    if research:
        lines += ['## Company research and purchase checks', '',
                  'Current research is checked alongside the price model. It is not inserted into historical LSTM training. '
                  'A purchase requires supportive recent fundamentals plus at least one other supportive category, '
                  'no negative category or research errors, and no earnings announcement within two days. '
                  'Missing news/analyst coverage is unavailable, never positive evidence.', '',
                  table(['Stock', 'Fundamentals', 'Earnings', 'Analysts', 'News', 'Research decision'],
                        [[symbol, *[data['gate'].get('categories', {}).get(key, 'unavailable')
                                    for key in ['fundamentals', 'earnings', 'analysts', 'news']],
                          'PASS' if data['gate']['approved'] else data['gate']['reason']]
                         for symbol, data in research.items()]), '']
        for symbol, data in research.items():
            financials = data.get('financials', {})
            analysts = data.get('analysts', {})
            earnings = data.get('earnings', {})
            def percent(value):
                return f'{value:.1%}' if value is not None else 'Unavailable'
            lines += [f'### {symbol}', '',
                      f"Financial period: {financials.get('period_end', 'Unavailable')}. "
                      f"Net margin: {percent(financials.get('net_margin'))}; "
                      f"revenue growth vs prior year: {percent(financials.get('revenue_yoy_growth'))}; "
                      f"net income growth: {percent(financials.get('net_income_yoy_growth'))}.", '',
                      f"Analyst count: {analysts.get('analyst_count')}; mean recommendation "
                      f"(1=strong buy, 5=sell): {analysts.get('recommendation_mean')}; "
                      f"mean target upside: {percent(analysts.get('target_upside'))}. "
                      'Analyst targets typically concern 12 months, not the model’s 21 trading days.', '',
                      f"Latest earnings: {earnings.get('latest_report')}; next reported date: {earnings.get('next_report')}.", '']
            articles = data.get('news', [])
            if not articles:
                lines += ['No recent, relevant English news with a verifiable publication date was analyzed.', '']
            for article in articles:
                title = article['title'].replace('[', '(').replace(']', ')').replace('\n', ' ')
                link = f"[{title}]({article['url']})" if article.get('url') else title
                score = article.get('sentiment', {}).get('score')
                lines += [f"- {link} — {article['published_at']}; {article['provider']}; "
                          f"FinBERT sentiment: {score if score is not None else 'unavailable'}."]
            if data.get('sources'):
                lines += ['', 'Sources: ' + ' · '.join(f'[{key}]({url})' for key, url in data['sources'].items()), '']
            if data.get('errors'):
                lines += ['Research errors: ' + str(data['errors']), '']
        lines += ['News sentiment uses a fixed, pretrained English FinBERT model on headlines and provider summaries. '
                  'It does not read full articles or complete company filings, verify claims independently, or retrain FinBERT. '
                  'Research gate thresholds are experimental rules, not proven investment advantages.', '']
    summary = '\n'.join(lines)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / 'summary.md').write_text(summary)
    # Plain text preformatted content keeps email consistent with the measured report.
    (directory / 'email.html').write_text('<html><body><pre style="white-space:pre-wrap;font:14px sans-serif">' + html.escape(summary) + '</pre></body></html>')
    fields = ['time', 'ticker', 'action', 'qty', 'price', 'amount', 'currency', 'confidence', 'reason']
    with (directory / 'trades.csv').open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        for trade in report['trades']:
            writer.writerow({**trade, 'amount': trade.get('amount', trade['qty'] * trade['price']),
                             'currency': trade.get('currency', 'USD')})
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as stream:
            stream.write(summary)

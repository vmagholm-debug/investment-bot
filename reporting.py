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
        lines += [table(['Time', 'Ticker', 'Action', 'Shares', 'USD/share', 'Fake USD amount', 'Score', 'Reason'],
                        [[t['time'], t['ticker'], t['action'], f"{t['qty']:.6f}",
                          f"{t['price']:.4f}", f"{t.get('amount', t['qty'] * t['price']):.2f}",
                          (f"{t['confidence']:.4f}" if t.get('confidence') is not None else 'Unavailable'), t.get('reason', '')] for t in new_trades]), '']
    else:
        lines += ['No simulated trades this run. See the signal table for scores, filters, and errors.', '']
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
                      f"{s['confidence']:.4f}" if s.get('confidence') is not None else 'Unavailable',
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
              'Daily buy/sell simulation excludes fees, slippage and dividend cash payments. Exit thresholds are not guaranteed fills; gaps can exceed them.', '']
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
    if report.get('strategy_policy'):
        lines += ['## Five trading strategies', '', report['strategy_policy'], '',
                  'Any single entry can qualify; overlapping signals do not increase position size. '
                  'Attribution priority: mean reversion, momentum, trend following, breakout, earnings. '
                  'Momentum ranks the analyzed universe, not the entire market. LSTM scores no longer veto entries. '
                  'Research approval remains required. Fills use latest adjusted closes and dated FX, not executable quotes.', '',
                  table(['Ticker', 'Strategy', 'Entry', 'Exit', 'Evidence / thresholds'],
                        [[s['ticker'], name, rule['entry'], rule['exit'], rule['reason']]
                         for s in report['results'] for name, rule in s.get('strategies', {}).items()]), '',
                  '## Realized strategy results', '',
                  table(['Strategy', 'Closed trades', 'Realized P/L USD'],
                        [[name, sum(t.get('strategy') == name and t['action'] == 'PAPER SELL' for t in report['trades']),
                          round(sum(t.get('realized_pnl', 0) for t in report['trades'] if t.get('strategy') == name), 2)]
                         for name in ['mean_reversion', 'momentum', 'trend_following', 'breakout', 'earnings']]), '',
                  'Realized P/L excludes open positions. Rules are experimental, without validated profitability.', '']
    patterns = report.get('pattern_analysis', {})
    if patterns:
        lines += ['## Cross-stock pattern evidence', '', patterns['policy'], '',
                  f"Library: {patterns['stored_records']} historical snapshots across {patterns['stored_tickers']} tickers; {patterns['new_records']} newly added.", '',
                  'Prospective validation: ' + str(patterns['validation']), '',
                  'Outcomes use local-currency adjusted closes less an illustrative 0.2% round-trip cost. '
                  'Positive fractions describe historical matches, not calibrated forecasts. '
                  'Research blocking a purchase is distinct from evidence against a price pattern.', '',
                  table(['Ticker', 'Shape', 'Matches / companies / months', '5d / 10d / 21d mean net return', '21d median / baseline median', '21d positive fraction', '21d downside p10', 'Extreme outcomes', 'Assessment'],
                        [[ticker, data['context']['family'],
                          f"{data['matches']['count']} / {data['matches']['tickers']} / {data['matches']['months']}",
                          ' / '.join(f"{data['matches']['outcomes'][str(h)]['mean_net_return']:.1%}" for h in [5,10,21]) if data['matches']['count'] else 'Unavailable',
                          (f"{data['matches']['outcomes']['21']['median_net_return']:.1%} / {data['baseline']['outcomes']['21']['median_net_return']:.1%}" if data['matches']['count'] else 'Unavailable'),
                          f"{data['matches']['outcomes']['21']['positive_fraction']:.1%}" if data['matches']['count'] else 'Unavailable',
                          f"{data['matches']['outcomes']['21']['p10_net_return']:.1%}" if data['matches']['count'] else 'Unavailable',
                          sum(o['extreme_outcomes'] for o in data['matches']['outcomes'].values()),
                          data['assessment'] + '; ' + data['combined_assessment']]
                         for ticker,data in patterns['results'].items()]), '']
        for ticker,data in patterns['results'].items():
            if data['examples']:
                lines += [f'### Pattern comparisons: {ticker}', '',
                          table(['Other stock', 'Pattern date', 'Outcome date', 'Distance (lower closer)', '21d gross return', 'Worst interim close return'],
                                [[e['ticker'],e['date'],e['label_end'],f"{e['distance']:.3f}",f"{e['returns']['21']:.1%}",f"{e['worst_interim_close_return']:.1%}"] for e in data['examples']]), '']
        lines += [patterns['limitations'], '', 'Pattern errors: ' + str(patterns['errors']), '',
                  'Prospective forecasts are evaluated from the first close after issuance over 21 subsequent trading bars, '
                  'when that ticker is retrieved again. Pending outcomes are not wins or losses. The pattern layer does not place orders.', '']
    catalogue = report.get('catalogue_analysis', {})
    if catalogue:
        lines += ['## Literature catalogue and validation controls', '',
                  f"94 registered families. Implementations: {catalogue['implementation_counts']}. Protocol: {catalogue['protocol_id']}.", '',
                  catalogue['evidence_attribution'] + '. Status: ' + catalogue['validation_status'], '',
                  catalogue['independence_rule'], '',
                  'Required checks: ' + str(catalogue['prerequisites']), '',
                  'Source metadata and all unavailable families: anomaly_catalogue.json in the repository. '
                  'Long-horizon value/momentum features are not validated by short-horizon 21-day outcomes.', '',
                  table(['Stock', 'Family', 'Observed values', 'Limits'],
                        [[ticker, id, item['values'], item['limitation']]
                         for ticker, row in catalogue['results'].items() for id,item in row['features'].items()]), '',
                  'Cost scenarios for historical pattern analogs: 0%, 0.2%, 0.5%, 1% round trip. '
                  'These are stress assumptions, not observed spread, market impact or borrowing costs.', '',
                  table(['Stock', '21d median at 0 / 0.2 / 0.5 / 1% cost'],
                        [[ticker, ' / '.join(f"{v['median_net_return']:.1%}" for v in row['matches']['outcomes']['21']['cost_sensitivity'].values())]
                         for ticker,row in report.get('pattern_analysis',{}).get('results',{}).items() if row['matches']['count']]), '',
                  'Multiple-testing correction is not yet estimable: there are no valid family-level p-values. '
                  'No significance or alpha claim is made; none of the 94 families is automatically promoted to trading.', '']
    summary = '\n'.join(lines)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / 'summary.md').write_text(summary)
    # Plain text preformatted content keeps email consistent with the measured report.
    (directory / 'email.html').write_text('<html><body><pre style="white-space:pre-wrap;font:14px sans-serif">' + html.escape(summary) + '</pre></body></html>')
    fields = ['time', 'ticker', 'action', 'qty', 'price', 'amount', 'currency', 'quote_currency', 'native_price', 'fx_to_usd', 'confidence', 'strategy', 'realized_pnl', 'reason']
    with (directory / 'trades.csv').open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        for trade in report['trades']:
            writer.writerow({**trade, **{key: trade.get('quote', {}).get(key) for key in ['quote_currency', 'native_price', 'fx_to_usd']}, 'amount': trade.get('amount', trade['qty'] * trade['price']),
                             'currency': trade.get('currency', 'USD')})
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as stream:
            stream.write(summary)

# Europe-first five-strategy fake-money investment bot

## Where to see results

Open https://github.com/vmagholm-debug/investment-bot/actions and select the latest
completed **Run investment bot** run. Its summary shows the fake portfolio, every
new trade, training changes, all signals and errors. Download `paper-trading-report`
for `summary.md`, `trades.csv` (all historical trades), `latest.json`, and the saved
account/model. Email delivery is configured separately through the user's Codex
follow-up and connected Gmail; no mailbox credentials are published in this repo.

## Automatic stock discovery with a European focus

No stock-symbol list is required. On every run `discovery.py` queries Yahoo
Finance's live stock screener across its supported regions, with most analysis
slots reserved for Europe. It finds equities with average daily volume above
100,000 shares and a Yahoo intraday-market-cap field of at least 500 million.
These provider filters narrow coverage; this is not every security on earth.

For Europe and the rest of the world separately, it fetches up to 250 active
candidates plus a rotating alphabetical page of up to 250. It then selects 24
European and 8 other candidates, spreading slots across exchanges and favoring those least recently analyzed with a
reproducible daily shuffle. `discovery.json` saves page positions and selection
history. Existing holdings are always included in valuation. Each report records
matching-stock counts, fetched candidates, selected symbols, and data-source
metadata. A screener failure stops the run visibly; it never silently substitutes
a fixed watchlist. The optional `--tickers` flag is only an explicit test override.

This uses yfinance's public-data interfaces and company-associated news feeds. It
does not browse arbitrary websites. Sources can be delayed or unavailable. Discovery is bounded to fit
the free scheduled runner. The LSTM remains an experimental price-history model, with a separate current-evidence research gate.

Every discovered ticker's quote currency is fetched dynamically. Foreign prices
are converted to the account's existing fake USD balance, with FX dates recorded.
UK pence are divided by 100 before GBP/USD conversion. Missing currency or FX data
blocks a purchase instead of assuming USD. No real-money broker is connected.

## Learning reports

Every run explains how many newly labeled historical windows were added, how many
training steps ran, the loss before/after on the same training batch, historical
+10% outcome counts, and changes in scores on the same latest windows. These are
measurements, not invented market narratives or proof of predictive skill.


Runs daily at 09:00 Europe/Stockholm (Swedish local time, including DST), starting with **100,000 simulated USD**. No broker,
credentials, deposits, or real orders are involved. The supplied two-layer LSTM trains on 30-day sequences. The five strategies below generate entries independently of the LSTM score. Each entry uses
2% of remaining fake cash, with at most ten holdings and no borrowing.
Purchases use the latest downloaded adjusted close, not an executable live quote.
The bot keeps cash, holdings, and trade history in `state.json`; repeated runs
cannot buy the same ticker twice for the same price date.

The supplied strategy's 10% return target is a classification threshold, not a
promised return. Model probabilities are uncalibrated; holdout accuracy is not
proof of profitability. The historical mean return field is not a forecast. LSTM scores have no measured
out-of-sample accuracy; reports explicitly mark accuracy as unavailable.
Daily sell rules are described below. Commissions, slippage and dividend cash accounting are not modeled.
This is an experimental simulation, without validated profitability.
Price dates are included in reports; failed downloads may leave stale valuations.

## Run locally

Use Python 3.11 (tested locally with Python 3.9.6):

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
bash run_bot.sh
```

Read `reports/latest.json` for decisions, trades, remaining cash, holdings value,
and profit/loss. A failed ticker produces a report and a nonzero exit code.
Keep `state.json` to preserve the account and `model.pt` to preserve learning. Back it up before deliberately removing
it to reset the fake account. Run only one local process against a state file.

## Publish and enable daily runs

From this folder:

```bash
gh auth login --hostname github.com --web
git init -b main
git add .
git commit -m "Set up persistent fake-money investment bot"
gh repo create investment-bot --public --source=. --remote=origin --push
gh workflow run run.yml
```

This creates a PUBLIC repository. Code, logs and simulation reports are public.
The GitHub account starts separately from any local simulation: local state is
ignored by Git. View runs under Actions → Run investment bot. Download the
`paper-trading-report` artifact for the JSON report and account state.

Each job restores the newest saved report artifact, runs once, then saves state,
model checkpoint, optimizer and replay buffer, and report for 90 days. Concurrent workflow runs are serialized. Artifact storage
is not permanent: back up the state if pausing the bot. If no unexpired artifact
exists, the job explicitly logs that it starts a new 100,000 fake USD account.
Scheduled jobs can be delayed; public repository schedules are disabled after
60 days without repository activity and can be re-enabled from Actions.

Standard GitHub-hosted runners are free for public repositories:
https://docs.github.com/en/billing/concepts/product-billing/github-actions

Scheduling details:
https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule

## Learning behavior

`lstm_bot.py` is the default entry point. Each daily run adds newly labeled
historical samples to a replay buffer (up to 20,000 samples), then performs 20
CPU training steps if new samples arrived. Labels require 21 future trading
days, so today's observation cannot be used as a known outcome yet. Normalization
uses only each 30-day sequence's own observations. Model, optimizer, sample IDs,
and replay tensors persist together. Repeating a run without new labeled samples
does not retrain. The pasted weekly “full retrain” only printed a message; this
implementation uses actual bounded incremental training and does not claim a
weekly reset. It runs daily, not in an endless hourly loop.

The earlier gradient-boosting implementation remains in `bot.py` as shared
accounting/indicator code and an optional standalone baseline. Its filters differ
from the scheduled five-strategy system. Do not run both against the same state file.

## Corrections

- Fixed the pasted Python indentation, escaped names, and special methods.
- Preserved recent observations for inference instead of dropping unlabeled rows.
- Normalized inputs, retained CPU replay data, and saved actual training state.
- Added fake-money accounting, bounded position sizes and duplicate protection.
- Emits JSON reports and returns a failure status for ticker errors.

## Tests

```bash
.venv/bin/python -m unittest discover -s tests -v
```

## News, fundamentals, earnings and analyst research

`research.py` retrieves current company information, quarterly income statements,
reported/estimated EPS and upcoming earnings dates, analyst recommendation/target
aggregates, and recent company-associated news. Financial data and article links,
publication dates, observation time, missing coverage and errors appear in reports.
The JSON artifact retains the complete evidence used for each decision.

FinBERT (`ProsusAI/finbert`, pinned revision) classifies relevant English headlines
and provider summaries from the last seven days as positive, negative or neutral.
It requires a company-name/ticker mention, an explicit English language tag and a
valid publication date, and removes duplicates/future/old items. It does not read
full articles, full filings, non-English news or independently verify journalism.
The pretrained FinBERT is fixed; only the original price/volume LSTM keeps learning.
No API subscription is needed; model weights are downloaded for local CPU inference.

An entry from at least one of the five strategies is required. LSTM scores are diagnostic only. Paper buys also
require supportive recent fundamentals and at least one other supportive research
category, no negative category or retrieval/inference errors, and no known earnings
announcement within two days. Unknown data is never counted as supportive.

The explicit experimental rules are:
- Fundamentals: quarterly statement no older than 180 days; at least two positive
  observations among net margin, revenue growth vs the same quarter a year earlier,
  and operating cash flow with a current reported quarter; no negative observation.
  Two negative observations classify the category as negative.
- Earnings: recent reported EPS surprise and/or year-over-year net-income growth;
  any value below -5% is negative; otherwise a positive value is supportive.
- Analysts: at least three analysts, recommendation mean <=2.5 (1 strongest buy)
  and mean target upside >=5% is supportive. Recommendation >=3.5 or target downside
  below -5% is negative. Incomplete or suspicious target/quote unit data is unavailable.
  Targets typically use a 12-month horizon, not the LSTM's 21 trading days. Individual
  analyst-report dates and full texts are not available from this aggregate feed.
- News: mean FinBERT positive probability minus negative probability >=0.15 is
  supportive; <=-0.25 is negative; other observed scores are mixed. Missing relevant
  English stories are unavailable. Failure to fetch/analyze stories blocks approval.

These thresholds are transparent research heuristics, not backtested advantages.
Today's evidence is not inserted into historical training rows, which would leak
future information. Research may veto any strategy entry. Every trade records
its research gate and reason. Daily email reports include the same research results.

Sources: https://ranaroussi.github.io/yfinance/ and
https://huggingface.co/ProsusAI/finbert

## Five strategy rules (experimental v1)

These are chosen transparent rules, not an industry-standard five-pillar system.
At least 61 valid daily observations are required. Entry priority when several
qualify: mean reversion, momentum, trend following, breakout, earnings. Only one
position per ticker is permitted; overlapping signals never multiply its size.

| Strategy | Entry | Strategy exit |
| --- | --- | --- |
| Mean reversion | Close at least 1.5 standard deviations below 20-day mean, RSI <40, and close above prior close | Close reaches SMA20 |
| Momentum | Top 20% of analyzed candidates by 60-day return (at least 5 peers), return >5%, positive 20-day return | 20-day return <=0 |
| Trend following | Close > SMA20 > SMA50 and SMA50 above its value five bars ago | Close below SMA50 |
| Breakout | Close above the preceding 20 daily highs, volume >=1.5 times preceding 20-day mean | Close below SMA20 |
| Earnings | EPS surprise >=5%, released within seven calendar days, a price bar after the report date and positive daily return | Close below SMA20 |

Every holding also exits at an observed USD return <=-5%, >=10%, or after 21
trading bars. These are checked daily, not intraday stop orders. Fills use the
observed adjusted close, so losses can exceed 5% after gaps. Quotes older than
seven calendar days or failed currency lookups block execution. Positions remain
valued at their last known quote when retrieval fails. All strategy entries still
require the research gate above. No purchase is guaranteed on any given day.

Trades retain strategy attribution and sales record realized USD P/L. The report
shows all five rule evaluations and realized results by strategy; the cumulative
CSV contains buys and sells. Existing state and LSTM training continue unchanged.
Realized strategy P/L excludes open positions and trading costs. This is forward
paper evaluation, not evidence from a historical out-of-sample backtest.

## Cross-stock pattern comparisons

`patterns.py` adds a diagnostic pattern library. It compares four consecutive
five-day price changes, distance from 20/50-day means, volatility and relative
volume across the rotating Europe-first universe. Context is tagged as rebound
after decline, uptrend, downtrend or mixed. It does not enumerate all named chart
patterns or scan every listed security. The library grows as new tickers are
analyzed, retaining at most 50,000 historical snapshots in `patterns.json`.

Matches exclude the same ticker and any outcome not fully known before the query
date. At most 60 matches within a fixed 0.75 RMS feature distance are retained;
overlapping outcome intervals within one stock are removed. Reports show returns
after 5/10/21 trading days, positive fractions, medians, downside percentiles,
worst interim close returns and actual example tickers/dates. Historical support
requires at least 20 matches across five stocks and eight calendar months; this
is an explicit heuristic, not a statistical guarantee. Correlated stocks remain
correlated observations. The cost assumption is 0.2% round trip, and returns are
in each stock's quote currency, not the fake account's FX-adjusted USD return.

Current fundamentals, earnings, analysts and news approval are shown alongside
pattern evidence. These current observations are not retroactively inserted in
historical examples. Price shapes alone cannot establish that a move followed an
earnings release; this version does not test historical earnings-event patterns.

New forecasts are saved before their outcomes exist and scored from the next
trading close over 21 further trading bars when the ticker is retrieved again.
Only one pending forecast per ticker is allowed. Forecasts use median returns to reduce domination by outliers. Extreme outcomes
(absolute returns at least 100%) are flagged and retained, not silently dropped.
Reports compare absolute forecast
error against the unconditional eligible-history median. Pending examples are not
successes. This forward evaluation starts now; no claim of proven predictive
skill is made. Changing ticker selection, survivorship, short history and shared
market moves limit interpretation. No pattern result overrides the five strategy
rules or research checks, or increases position sizes.

Methods context (not validation of this implementation):
https://www.nber.org/papers/w7613
https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html

## Applying the 94-family research catalogue

`anomaly_catalogue.json` records all 94 families, source profile pages, source-file
hash, the document author's literature classification, requirements and actual
implementation status. See `CATALOGUE_APPLICATION.md` for the complete mapping.
The source PDF itself is not redistributed. Literature classifications are not
independently verified performance results for this bot.

`catalogue.py` computes 11 daily-data feature families: 12–1 momentum (excluding
the latest 21 bars), short-term reversal, 252-day-high distance, MAX daily return,
overnight/intraday decomposition, fixed MA and breakout distances, RSI, 60-day
volatility, volatility expansion and relative volume. Five additional families
have explicitly partial current proxies: raw EPS surprise, book/price, earnings
yield, quarterly margin and headline sentiment. These are observations, not full
replications of the papers or 16 independent trading strategies. In particular,
raw EPS surprise is not standardized SUE; FinBERT is not market-wide sentiment;
current ratios have no reconstructed historical release timestamps. If required
fields/history are missing, the feature is unavailable, not zero or bullish.

The other 78 families are registered but not implemented because the current
provider lacks required history, timestamps or market microstructure, or because
a proper protocol has not been implemented. No fabricated insider/options/order
flow or analyst revision history is substituted. The existing five paper-trading
rules remain experimental; this diagnostic catalogue does not authorize them as
validated alpha or change them into an automatic 94-signal voting system.

Pattern outcomes include cost sensitivity at 0%, 0.2%, 0.5% and 1% round trip.
These are assumptions, not measured spread/impact/borrow. A protocol fingerprint
includes code and definitions, so prospective forecasts from earlier versions
are excluded from the current validation aggregate without deleting their records.
A new method cannot claim old prospective results as its own.

Reports explicitly mark the remaining validation prerequisites as not demonstrated:
point-in-time reconstruction; survivorship/delistings; realistic execution; an
untouched out-of-sample period; risk-adjusted benchmarks; multiple-testing control;
and international/time replication. No p-values exist yet, so no FDR/significance
claim is made. No parameter grid search or automatic deployment takes place.
Long-horizon value/momentum research cannot be validated by the bot's 21-day
comparison horizon; risk/behavior regularities do not imply directional returns.

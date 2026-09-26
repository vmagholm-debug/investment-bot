# Europe-first LSTM fake-money investment bot

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


Runs daily at 09:00 UTC, starting with **100,000 simulated USD**. No broker,
credentials, deposits, or real orders are involved. The supplied two-layer LSTM trains on 30-day sequences. A score above 0.8 buys
fractional simulated shares with 10% of remaining cash, without borrowing.
Purchases use the latest downloaded adjusted close, not an executable live quote.
The bot keeps cash, holdings, and trade history in `state.json`; repeated runs
cannot buy the same ticker twice for the same price date.

The supplied strategy's 10% return target is a classification threshold, not a
promised return. Model probabilities are uncalibrated; holdout accuracy is not
proof of profitability. The historical mean return field is not a forecast. LSTM scores have no measured
out-of-sample accuracy; reports explicitly mark accuracy as unavailable.
There are no sell rules, commissions, slippage, or dividend cash accounting.
This is an experimental buy-only simulation; cash will decline as purchases occur.
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
from the LSTM's score-only threshold. Do not run both against the same state file.

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

A technical score above 0.80 is now necessary but insufficient. Paper buys also
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
future information. Research may veto a high technical score. Every trade records
its research gate and reason. Daily email reports include the same research results.

Sources: https://ranaroussi.github.io/yfinance/ and
https://huggingface.co/ProsusAI/finbert

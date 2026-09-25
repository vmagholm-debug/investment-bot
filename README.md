# LSTM fake-money investment bot

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

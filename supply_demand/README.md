# Supply & Demand paper agent · supply-demand-v1

A separate deterministic paper agent for QQQ (Nasdaq-100, USD) and EXS1.DE
(DAX ETF, EUR). It does not use gamma, options flow, LSTM scores or the reference
bot's accounts. It runs every 15 minutes on weekdays 09:00–22:59 Stockholm time;
GitHub scheduling can be delayed. Data can be delayed too. Only completed regular
session candles are used, using NASDAQ/XETR exchange calendars including holidays
and early closes. Weekends/closed markets create no new entries. A 15-minute
scan evaluates only the latest 5m rejection; it can miss setups between scans.

## Fixed experimental rules

- Build exact, contiguous 1h/4h candles from completed 5m bars, anchored at the
  exchange session opening: QQQ 09:30 New York, EXS1 09:00 Berlin. Partial sessions
  and incomplete windows do not become full 4h candles.
- A base is one candle with range <=0.8 ATR14. The next candle departs with body
  >=1.5 prior ATR14 and closes above/below the base. The zone is the base range,
  known only after the departure closes. Zones expire after seven calendar days.
- Enter only on the first later 5m touch with a directional rejection candle
  closing beyond the proximal boundary. Any earlier touch consumes freshness.
  A close beyond the distal boundary invalidates the zone. Signals are not
  retrospectively backfilled from historical warm-up data.
- BUY opens LONG; SELL opens SHORT. Entry is a queued intent observed now. Fill
  uses the first completed bar whose start is at or after that recorded decision,
  never the already-known historical closing price.
- Stop: outer low for LONG or outer high for SHORT of the latest completed 1h and
  4h candles. This is the declared initial interpretation of prior high/low,
  not automatic swing-point identification. Invalid stop placement rejects entry.
- Start risk: 0.5% of the native account's equity including estimated round-trip
  costs; notional capped at 95% equity; one position per market. Stop gaps can
  exceed the planned risk. Fixed illustrative target: 2R, no automatic trailing.
- 0.1% illustrative cost each side. Stops gap at adverse open; a bar hitting stop
  and target uses stop first because the intrabar sequence is unknown.

Two new native-currency subaccounts start with 100,000 USD and 100,000 EUR.
Their balances are never summed or compared to the reference account's lifetime
P/L. Borrow fees, dividend liability, real short availability, spread and market
impact are not modeled. These are experimental rules, not validated alpha.

## Persistent state and reports

`Supply and Demand paper agent` is an independent GitHub Actions workflow.
The `supply-demand-paper-state` branch stores `supply-demand/state.json`,
`latest.json`, cumulative `trades.csv`, and `summary.md`. Each update is one atomic
Git commit with a non-forced fast-forward check. A separate concurrency group
serializes this agent; the original bot workflows and accounts are untouched.
Artifacts named `supply-demand-paper-report` provide per-run evidence for 90 days.
The state branch remains after artifact expiry. Missing or malformed state stops
the agent; it never creates a replacement account automatically.

First activation uses workflow_dispatch `initialize=true` once. That flag is
refused once the permanent branch exists. Future runs use `initialize=false`.
Stored policy must exactly match the versioned code policy; no automatic tuning
or migration is allowed. Missing execution history blocks the affected market;
other markets can proceed independently, with a visible failed run/report.

## Local checks

`python -m unittest discover -s tests -p test_supply_demand.py -v`

There is no broker connection, real order function, model reset or account import.

# Broader paper portfolio, protocol broad-paper-v1

The existing account remains the reference. The experiment starts prospectively with a copy of its cash and positions, marked at the same run's prices. Inherited trades remain available for exit bookkeeping but are excluded from the experiment's new trade history. Comparison returns begin at this common initialization, not at the original account launch. Existing positions held without any further trading provide a third, passive internal baseline. This is not a market index or proof of alpha.

| Rule | Reference | Experiment |
| --- | --- | --- |
| MiljonBot analysis universe | First twelve selected symbols | Every active feed symbol, plus discovery and holdings; errors disclosed |
| Research | Supportive recent fundamentals and another supportive category; no negative categories/errors | One supportive category or a positive checked catalyst. Negative news or earnings still blocks. Missing coverage and errors remain recorded; missing does not mean positive. |
| Momentum entry | Peer percentile >=0.8, 60-day return >5%, positive 20-day return | Percentile >=0.6, positive 60- and 20-day returns |
| Mean reversion entry | z<=-1.5, RSI<40, rebound | z<=-1, RSI<45, rebound |
| Breakout entry | Volume >=1.5 times recent mean | Volume >=1.2 times recent mean |
| Trend/earnings entries | Existing rules | Same rules |
| Holdings | Maximum ten | Maximum twenty |
| Minimum median 20-bar turnover | MiljonBot USD100,000 | All experiment entries USD25,000 |
| Sizing | MiljonBot below USD5: 1% cash; other entries 2% | Below USD5: 0.5% cash; otherwise 2%; budget including costs capped at 0.5% of median turnover |
| Costs | Original account excludes costs | Deduct illustrative combined fee/slippage 0.1% on each side. Reference net comparison deducts the same rate from recorded reference turnover. |
| Execution | Existing daily-close approximation | Queue entries and execute only at a completed bar dated after the decision date. No retrospective reconstruction of earlier signals. |

Candidates are ranked deterministically before allocation. The score is 10 points per active technical entry rule, 15 per supportive research category, and 25 for a positive checked catalyst, capped at 100. Tier1 >=65, Tier2 >=40, otherwise Tier3. These correlated inputs are not independent evidence. Scores and tiers are not probabilities, calibrated confidence, or hedge-fund endorsements.

Feed-based entries retain source, date, instrument and one-entry-per-signal checks. Unverified sources can be analyzed but cannot authorize an entry. Negative leads cannot fund entries; uncertain checked leads need supportive research. Pending orders expire after seven days and cannot outlive their source signals. Currency and minor units are verified before USD sizing. Spreads, dilution filings and broker availability are not comprehensively verified. Entry price alone does not establish cheapness or value.

Daily exits retain -5% loss, +10% profit, 21-bar holding period and original strategy exit rules, filled at the observed close rather than an invented threshold price. Pending entry delays differ from reference execution, so the comparison measures the complete bundled policy, not just relaxed research. Intraday drawdowns and gap losses can be worse than run snapshots. Market impact can exceed the illustrative costs, especially for small stocks.

`experiment-state.json` is a separate persisted account restored/uploaded with the same GitHub artifact. `reports/experiment.json`, `reports/experiment-trades.csv` and the experiment section of `summary.md` expose cumulative trades, decisions, missing research, returns, net equity, maximum observed drawdown and cost sensitivity. Sensitivity at 0/0.1/0.25/0.5% per side holds recorded quantities fixed; it does not resimulate alternate cash paths. Neither portfolio's result validates the diagnostic LSTM.

The existing schedule is unchanged. Experiment-only symbols do not enter reference momentum ranks or LSTM training. If experiment initialization lacks a valid price for an inherited holding, it waits rather than silently resetting or assigning a zero valuation. Later missing prices are marked as stale. Protocol changes require a new state filename rather than overwriting the current trial.

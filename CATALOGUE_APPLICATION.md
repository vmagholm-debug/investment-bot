# Tillämpning av den dokumenterade mönsterkatalogen

Evidensklasserna är katalogförfattarens syntes, inte botens valideringsresultat. Ingen av familjerna betraktas som bevisad lönsam alpha i denna implementation.

11 familjer får definierade dagliga mått; fem får uttryckligen begränsade aktuella proxyvärden. Övriga 78 är registrerade med datakrav men inte implementerade som signaler.

| ID | Familj | Katalogens evidens | Implementationsstatus | Källsida |
|---|---|---|---|---|
| E1 | PEAD | relatively_strong | partial_current_proxy | 11 |
| E2 | Announcement-return continuation | relatively_strong | not_implemented_missing_data_or_protocol | 11 |
| E3 | Revenue surprise | relatively_strong | not_implemented_missing_data_or_protocol | 12 |
| E4 | Analyst revisions | relatively_strong | not_implemented_missing_data_or_protocol | 12 |
| E5 | Guidance surprise | mixed | not_implemented_missing_data_or_protocol | 12 |
| E6 | Earnings-announcement premium | mixed | not_implemented_missing_data_or_protocol | 12 |
| E7 | Optionsignal före earnings | mixed | not_implemented_missing_data_or_protocol | 13 |
| F1 | Book-to-market value | relatively_strong | partial_current_proxy | 13 |
| F2 | Earnings/cash-flow/sales yield | relatively_strong | partial_current_proxy | 13 |
| F3 | Enterprise multiple | mixed | not_implemented_missing_data_or_protocol | 13 |
| F4 | Size | mixed | not_implemented_missing_data_or_protocol | 13 |
| F5 | Accruals | relatively_strong | not_implemented_missing_data_or_protocol | 14 |
| F6 | Gross profitability | relatively_strong | not_implemented_missing_data_or_protocol | 14 |
| F7 | Quality/ROE/ROIC/margins | relatively_strong | partial_current_proxy | 14 |
| F8 | Investment/asset growth | relatively_strong | not_implemented_missing_data_or_protocol | 14 |
| F9 | Net share issuance | relatively_strong | not_implemented_missing_data_or_protocol | 15 |
| F10 | Debt issuance/leverage change | mixed | not_implemented_missing_data_or_protocol | 15 |
| F11 | Piotroski F-score | mixed | not_implemented_missing_data_or_protocol | 15 |
| F12 | R&D/intangibles | mixed | not_implemented_missing_data_or_protocol | 15 |
| F13 | Distress | mixed | not_implemented_missing_data_or_protocol | 15 |
| F14 | Dividend/payout | mixed | not_implemented_missing_data_or_protocol | 16 |
| P1 | Intermediate momentum | relatively_strong | daily_feature | 16 |
| P2 | Short-term reversal | relatively_strong | daily_feature | 16 |
| P3 | Long-term reversal | mixed | not_implemented_missing_data_or_protocol | 16 |
| P4 | Residual/industry/peer momentum | mixed | not_implemented_missing_data_or_protocol | 16 |
| P5 | 52-week high | mixed | daily_feature | 17 |
| P6 | MAX | mixed | daily_feature | 17 |
| P7 | Overnight/intraday decomposition | mixed | daily_feature | 17 |
| P8 | Gap continuation/reversal | weak | not_implemented_missing_data_or_protocol | 17 |
| T1 | Moving averages | mixed | daily_feature | 17 |
| T2 | Trading-range breakout/support/resistance | mixed | daily_feature | 18 |
| T3 | Head-and-shoulders/double tops-bottoms | weak | not_implemented_missing_data_or_protocol | 18 |
| T4 | Triangles/flags/pennants | weak | not_implemented_missing_data_or_protocol | 18 |
| T5 | Candlesticks | folklore_data_mining | not_implemented_missing_data_or_protocol | 18 |
| T6 | RSI/MACD/Bollinger | weak | daily_feature | 19 |
| S1 | Aggregate sentiment | mixed | not_implemented_missing_data_or_protocol | 19 |
| S2 | Media/news sentiment | mixed | partial_current_proxy | 19 |
| S3 | Google search attention | mixed | not_implemented_missing_data_or_protocol | 19 |
| S4 | Retail attention-driven buying | mixed | not_implemented_missing_data_or_protocol | 19 |
| S5 | Analyst disagreement | mixed | not_implemented_missing_data_or_protocol | 20 |
| S6 | Short interest | relatively_strong | not_implemented_missing_data_or_protocol | 20 |
| S7 | Social media/meme sentiment | weak | not_implemented_missing_data_or_protocol | 20 |
| I1 | Insider purchases | relatively_strong | not_implemented_missing_data_or_protocol | 20 |
| I2 | Insider sales | mixed | not_implemented_missing_data_or_protocol | 21 |
| C1 | IPO underpricing | relatively_strong | not_implemented_missing_data_or_protocol | 21 |
| C2 | IPO/SEO long-run underperformance | mixed | not_implemented_missing_data_or_protocol | 21 |
| C3 | Repurchase drift | mixed | not_implemented_missing_data_or_protocol | 21 |
| C4 | Spin-offs | mixed | not_implemented_missing_data_or_protocol | 21 |
| C5 | Splits/reverse splits | mixed | not_implemented_missing_data_or_protocol | 22 |
| C6 | M&A/merger arbitrage | relatively_strong | not_implemented_missing_data_or_protocol | 22 |
| C7 | Index inclusion/deletion | mixed | not_implemented_missing_data_or_protocol | 22 |
| C8 | Dividend initiation/omission/cut | mixed | not_implemented_missing_data_or_protocol | 22 |
| C9 | CEO/CFO changes, layoffs, restructuring | weak | not_implemented_missing_data_or_protocol | 23 |
| N1 | Mutual-fund flows | mixed | not_implemented_missing_data_or_protocol | 23 |
| N2 | Forced fire sales | relatively_strong | not_implemented_missing_data_or_protocol | 23 |
| N3 | Institutional ownership/breadth/crowding | mixed | not_implemented_missing_data_or_protocol | 23 |
| N4 | Window dressing/quarter-end | mixed | not_implemented_missing_data_or_protocol | 23 |
| N5 | ETF/passive-flow pressure | mixed | not_implemented_missing_data_or_protocol | 24 |
| M1 | Aggregate valuation | mixed | not_implemented_missing_data_or_protocol | 24 |
| M2 | Yield curve/term spread | mixed | not_implemented_missing_data_or_protocol | 24 |
| M3 | Credit spreads/financial conditions/money | mixed | not_implemented_missing_data_or_protocol | 24 |
| M4 | Monetary-policy surprises | relatively_strong | not_implemented_missing_data_or_protocol | 25 |
| M5 | Macro surprises | mixed | not_implemented_missing_data_or_protocol | 25 |
| M6 | Oil/commodities/FX | mixed | not_implemented_missing_data_or_protocol | 25 |
| O1 | Put/call ratio | mixed | not_implemented_missing_data_or_protocol | 25 |
| O2 | Option-to-stock volume | mixed | not_implemented_missing_data_or_protocol | 25 |
| O3 | IV spread/put-call parity | mixed | not_implemented_missing_data_or_protocol | 26 |
| O4 | IV skew/smirk | mixed | not_implemented_missing_data_or_protocol | 26 |
| O5 | IV minus realized / VRP | mixed | not_implemented_missing_data_or_protocol | 26 |
| O6 | Gamma/dealer positioning/unusual options | weak | not_implemented_missing_data_or_protocol | 26 |
| V1 | Low volatility | relatively_strong | daily_feature | 27 |
| V2 | Betting against beta | mixed | not_implemented_missing_data_or_protocol | 27 |
| V3 | Idiosyncratic volatility | mixed | not_implemented_missing_data_or_protocol | 27 |
| V4 | Volatility clustering/compression-expansion | relatively_strong | daily_feature | 27 |
| L1 | Illiquidity premium | relatively_strong | not_implemented_missing_data_or_protocol | 28 |
| L2 | Liquidity-risk beta | mixed | not_implemented_missing_data_or_protocol | 28 |
| L3 | Turnover/abnormal volume | mixed | daily_feature | 28 |
| L4 | Spread/depth/order imbalance | relatively_strong | not_implemented_missing_data_or_protocol | 28 |
| K1 | January/turn-of-year | mixed | not_implemented_missing_data_or_protocol | 29 |
| K2 | Day-of-week | weak | not_implemented_missing_data_or_protocol | 29 |
| K3 | Turn-of-month | mixed | not_implemented_missing_data_or_protocol | 29 |
| K4 | Pre-holiday | weak | not_implemented_missing_data_or_protocol | 29 |
| K5 | Expiration/quarter-end | weak | not_implemented_missing_data_or_protocol | 30 |
| K6 | Daylight saving | folklore_data_mining | not_implemented_missing_data_or_protocol | 30 |
| K7 | Month-of-year/sell-in-May/earnings-season | mixed | not_implemented_missing_data_or_protocol | 30 |
| U1 | Opening/closing auction & intraday seasonality | relatively_strong | not_implemented_missing_data_or_protocol | 30 |
| U2 | Bid–ask bounce | relatively_strong | not_implemented_missing_data_or_protocol | 30 |
| U3 | Order-flow persistence/price impact | relatively_strong | not_implemented_missing_data_or_protocol | 31 |
| U4 | Lead–lag/non-synchronous trading | relatively_strong | not_implemented_missing_data_or_protocol | 31 |
| B1 | Disposition effect | relatively_strong | not_implemented_missing_data_or_protocol | 31 |
| B2 | Herding/feedback trading | mixed | not_implemented_missing_data_or_protocol | 31 |
| B3 | Underreaction/information diffusion | relatively_strong | not_implemented_missing_data_or_protocol | 32 |
| B4 | Overreaction/representativeness | mixed | not_implemented_missing_data_or_protocol | 32 |
| B5 | Limits to arbitrage | relatively_strong | not_implemented_missing_data_or_protocol | 32 |

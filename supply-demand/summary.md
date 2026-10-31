# Supply & Demand · PAPER

2026-10-31T08:31:20.940683+00:00

{
  "protocol": "supply-demand-v1",
  "mode": "paper only",
  "universe": {
    "QQQ": {
      "currency": "USD",
      "zone": "America/New_York",
      "open": 570,
      "close": 960
    },
    "EXS1.DE": {
      "currency": "EUR",
      "zone": "Europe/Berlin",
      "open": 540,
      "close": 1050
    }
  },
  "zones": "1h/4h single base candle range <=0.8 preceding ATR14, followed by departure body >=1.5 ATR and close beyond the base. Zone known only at departure close.",
  "entry": "First later 5m touch of fresh zone, with directional candle closing beyond proximal boundary. No gamma, options flow or LSTM requirement. No historical signal backfill.",
  "stop": "Outer low for LONG / high for SHORT of latest completed session-anchored 1h and 4h bars known at decision.",
  "risk_fraction": 0.005,
  "notional_equity_cap": 0.95,
  "cost_per_side": 0.001,
  "target_R": 2.0,
  "pending_expiry_hours": 6,
  "zone_expiry_days": 7,
  "same_bar_stop_and_target": "Stop first, conservatively; intrabar order unknown.",
  "accounts": "Separate 100000 USD QQQ and 100000 EUR EXS1.DE paper subaccounts. Never sum native currencies.",
  "limits": "Experimental fixed rules, unvalidated profitability. Yahoo can be delayed. OHLC fills are illustrative; no spread, borrow fee, dividend liability or real short availability model."
}

{
  "QQQ": {
    "max_observed_drawdown": 0.0,
    "currency": "USD",
    "cash": 100000.0,
    "net_equity": 100000.0,
    "return_since_start": 0.0,
    "position": null,
    "pending": null,
    "decision": "AVVAKTA",
    "notes": [
      "Stale/closed market: no new entry"
    ],
    "quote_date": "2026-10-30T20:00:00+00:00",
    "stale_valuation": true,
    "zone_count": 0,
    "recent_zones": []
  },
  "EXS1.DE": {
    "max_observed_drawdown": 0.0,
    "currency": "EUR",
    "cash": 100000.0,
    "net_equity": 100000.0,
    "return_since_start": 0.0,
    "position": null,
    "pending": null,
    "decision": "AVVAKTA",
    "notes": [
      "Stale/closed market: no new entry"
    ],
    "quote_date": "2026-10-30T16:30:00+00:00",
    "stale_valuation": true,
    "zone_count": 0,
    "recent_zones": []
  }
}

## New trades

[]

## Errors

{}
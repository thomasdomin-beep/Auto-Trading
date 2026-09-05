# BSE Sensex Ideal Premium (IP) strategy

Same IP and support/resistance logic as the [Delta ETHUSD.P solution](../README.md), with data from **BSE India** (the APIs behind [bseindia.com](https://www.bseindia.com) option chain and contract quotes).

- **Underlying**: BSE Sensex spot (scrip code `1`)
- **Option chain**: nearest expiry from BSE derivatives option chain
- **Default schedule**: **5 minutes** (`interval_minutes` in config)
- **TradingView**: add [`pine/sensex_ip_strategy_levels.pine`](pine/sensex_ip_strategy_levels.pine) on **BSE:SENSEX** (configurable)

## Setup

```bash
cd bse-sensex
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Run

```bash
sensex-ip run-once
sensex-ip schedule              # every 5 minutes by default
sensex-ip schedule --with-bridge
sensex-ip serve-bridge          # http://127.0.0.1:8766/
```

## BSE data endpoints (public market data)

| Purpose | API path |
|---------|----------|
| Sensex spot | `getScripHeaderData/w?scripcode=1` |
| Expiries | `ddlExpiry_New/w?scrip_cd=1` |
| Option chain | `DerivOptionChain_IV/w?Expiry=…&scrip_cd=1&strprice=` |
| CE/PE daily low (chart header) | `StockReachGraph/w?scripcode={series_id}` (option quote chart on BSE) |

If the chart API returns no intraday points (common outside market hours), `daily_low_use_premium_fallback` uses the chain **LTP** for that leg so runs still complete; check `meta.daily_low_premium_fallback_used` in `levels.json`.

## Configuration

See [`config.yaml`](config.yaml). Notable keys:

- `interval_minutes: 5`
- `premium_field`: `ltp` (chain LTP), `mid` (bid/ask mid), or `close`
- `daily_low_mode`: `current_session` uses `Low` from `DeriScriptHeader`; `last_closed` falls back to `PrevClose` if `Low` is missing

Env prefix: `SENSEX_IP_` (e.g. `SENSEX_IP_INTERVAL_MINUTES=5`).

## Tests

```bash
pytest
```

## Disclaimer

Research and charting only, not financial advice. Verify levels against the BSE option chain UI during live market hours.

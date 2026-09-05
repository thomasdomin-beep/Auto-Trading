# NSE NIFTY / BANKNIFTY Ideal Premium (IP) strategy

Same IP and support/resistance rules as the [Delta ETH](../README.md) and [BSE Sensex](../bse-sensex/README.md) builds. Market data comes from **NSE India** public JSON APIs used by [nseindia.com/option-chain](https://www.nseindia.com/option-chain).

## Underlyings

| Config file | Symbol | TradingView (spot index) | Bridge port (default) |
|-------------|--------|--------------------------|------------------------|
| [`config.nifty.yaml`](config.nifty.yaml) | NIFTY | NSE:NIFTY | 8767 |
| [`config.banknifty.yaml`](config.banknifty.yaml) | BANKNIFTY | NSE:BANKNIFTY | 8768 |

Default interval: **5 minutes**.

## Setup

```bash
cd nse-indices
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

## Run

**NIFTY**

```bash
nse-ip -c config.nifty.yaml run-once
nse-ip -c config.nifty.yaml schedule --with-bridge
```

**BANKNIFTY**

```bash
nse-ip -c config.banknifty.yaml run-once
nse-ip -c config.banknifty.yaml schedule --with-bridge
```

## NSE APIs used

| Step | Endpoint |
|------|----------|
| Expiries | `/api/option-chain-contract-info?symbol=NIFTY` |
| Chain + spot | `/api/option-chain-v3?type=Indices&symbol=…&expiry=…` |
| Daily low (CE/PE chart) | `/api/chart-databyindex?index={identifier}&indices=false` — minimum of intraday `grapthData` |

Session warm-up uses `curl_cffi` (browser TLS) plus a visit to nseindia.com, matching what the website does.

If chart data is missing, `daily_low_use_premium_fallback` uses chain **LTP** (`lastPrice`).

## TradingView

Add [`pine/nse_ip_strategy_levels.pine`](pine/nse_ip_strategy_levels.pine) on **NSE:NIFTY** or **NSE:BANKNIFTY**. Paste support/resistance from the bridge UI or `output/levels.json`.

## Tests

```bash
pytest
```

## Disclaimer

Research and charting only. Respect NSE rate limits; avoid hammering the API faster than your configured interval.

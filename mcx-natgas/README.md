# MCX Natural Gas Ideal Premium (IP) strategy

Same IP / LHS / RHS rules as the [Delta ETH](../README.md), [BSE Sensex](../bse-sensex/README.md), and [NSE indices](../nse-indices/README.md) builds, but for **MCX Natural Gas** option-on-futures. Option chain data is fetched via the local proxy from the sibling [`option-premium-calculator/mcx-proxy`](../../option-premium-calculator/mcx-proxy) project (a small Playwright-driven Node server), since MCX's option chain endpoint blocks plain HTTP clients and only allows CORS from mcxindia.com.

## Important: no daily-low data source

The Delta/NSE/BSE builds compute IP as the average of the four crossover-pair legs' **daily low** (from an exchange candle/history API). MCX's option-chain feed only exposes a **live snapshot** (LTP) with no historical/intraday endpoint, so this build computes IP as the average of the four legs' **current LTP** instead. See `meta.ip_source` (`"current_ltp"`) in `output/levels.json`.

## Strategy summary

1. Load the nearest live Natural Gas option expiry (options on futures, `optfut`).
2. Find adjacent strikes **A** and **B** where CE premium &gt; PE at **A** and CE &lt; PE at **B** (pick the pair closest to spot/futures price).
3. **IP** = average of the current LTP of CE/PE at A and CE/PE at B.
4. Scan the left side of the option chain (the **CE** column, across every strike): find the strike whose CE premium is closest to IP → **LHS**. Scan the right side (the **PE** column, across every strike): find the strike whose PE premium is closest to IP → **RHS**. The scan isn't restricted to strikes below/above spot; spot is only used to break ties between two equally-close premiums.

## Setup

1. **Start the MCX proxy** (required before running this project):

   ```bash
   cd "/Users/thomasdomin/option-premium-calculator/mcx-proxy"
   npm install   # first time only
   npm start
   ```

   This opens a small visible Chrome window and listens on `http://127.0.0.1:3001` — leave it running.

2. **Install this project:**

   ```bash
   cd mcx-natgas
   python3 -m venv .venv && source .venv/bin/activate
   pip install -e ".[dev]"
   ```

Edit [`config.yaml`](config.yaml) (`underlying`, `mcx_proxy_base_url`, `interval_minutes`, etc.) if needed.

## Run

```bash
mcx-ip run-once
mcx-ip schedule --with-bridge
```

Open [http://127.0.0.1:8769/](http://127.0.0.1:8769/) and use **Copy LHS & RHS** for Pine inputs.

## TradingView

Add [`pine/mcx_natgas_ip_strategy_levels.pine`](pine/mcx_natgas_ip_strategy_levels.pine) on MCX Natural Gas futures. Paste LHS/RHS from the bridge UI or `output/levels.json`.

## Output

`output/levels.json` fields: `underlying`, `expiry_date`, `spot`, `strike_a`, `strike_b`, `ideal_premium`, `lhs`, `rhs`, `premiums` (the four crossover-pair leg LTPs used for IP), `computed_at` (UTC ISO), `computed_at_ist` (display), `meta.ip_source`.

Each successful run also appends one row (`computed_at`, `computed_at_ist`, `ideal_premium`, `lhs`, `rhs`) to `output/history.csv`.

## Tests

```bash
pytest
```

## Disclaimer

Research and charting only. The mcx-proxy is for local, personal use — it drives a real Chrome window and isn't hardened for multi-user or public deployment.

# ETHUSD.P Ideal Premium (IP) strategy

Computes **Ideal Premium (IP)** and **LHS / RHS** strike levels from the Delta Exchange India ETH option chain, then exposes them for a TradingView Pine indicator on **DELTAIN:ETHUSD.P**.

Data is fetched only from the [Delta Exchange India REST API](https://docs.delta.exchange/) (`https://api.india.delta.exchange`). Market-data endpoints used here do not require API keys.

## Strategy summary

1. Load the nearest live ETH option expiry.
2. Find adjacent strikes **A** and **B** where CE premium &gt; PE at **A** and CE &lt; PE at **B** (pick the pair closest to spot).
3. **IP** = average of daily **low** (1d candles) for CE/PE at A and CE/PE at B.
4. Scan the left side of the option chain (the **CE**/Calls column, across every strike): find the strike whose CE premium is closest to IP → **LHS**. Scan the right side (the **PE**/Puts column, across every strike): find the strike whose PE premium is closest to IP → **RHS**. The scan is not restricted to strikes below/above spot; spot is only used to break ties between two equally-close premiums.

## Order-flow signal (Buy CE / Buy PE)

While the bridge UI is running (`serve-bridge` or `schedule --with-bridge`), a background thread polls the live option chain every `order_flow_poll_seconds` (default 3s) and evaluates a continuous signal:

- **ATP** (Average Traded Price) = ticker `turnover_usd / volume` (a VWAP-style average for the day).
- **LTP** (Last Traded Price) = ticker `close`.
- **ATM** strike = the live strike closest to spot. **Nearest ITM** strike = the next strike in the in-the-money direction from ATM (one lower for calls, one higher for puts).
- **Buy CE** fires when the nearest ITM call's `(ATP − LTP)` drops below the ATM call's `(ATP − LTP)`.
- **Buy PE** fires when the nearest ITM put's `(ATP − LTP)` drops below the ATM put's `(ATP − LTP)`.

The dashboard shows a banner ("Buy CE" / "Buy PE" / "No signal") that refreshes every 2 seconds via `/api/orderflow`. Set `order_flow_enabled: false` in `config.yaml` to disable the poller.

## Setup

```bash
cd "/Users/thomasdomin/IP Based Strategy on Delta"
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Edit [`config.yaml`](config.yaml) (interval, `premium_field`, `daily_low_mode`, etc.).

## Run

**Single run** (writes `output/levels.json`):

```bash
ip-strategy run-once
```

**Scheduled runs** (interval from config):

```bash
ip-strategy schedule
```

**Scheduler + local bridge UI**:

```bash
ip-strategy schedule --with-bridge
```

**Bridge only** (after you already have `output/levels.json`):

```bash
ip-strategy serve-bridge
```

Open [http://127.0.0.1:8765/](http://127.0.0.1:8765/) and use **Copy LHS & RHS** for Pine inputs.

Optional: set `auto_clipboard: true` in config to copy LHS/RHS after each successful run (macOS may require Accessibility permission for `pyperclip`).

## Choosing an expiry

By default the strategy uses the **nearest live** ETH option expiry. To pin a specific expiry instead:

- **Dashboard (recommended):** open the bridge UI, pick a date from the **Expiry** dropdown (populated from Delta's live expiries) and click **Fetch selected expiry**. Levels are recomputed immediately for that expiry, and the scheduler keeps using it for subsequent auto-refreshes until you click **Use nearest (auto)** or pick another date.
- **Config/CLI:** set `expiry_date: "DD-MM-YYYY"` in `config.yaml`, or pass `--expiry DD-MM-YYYY` to `run-once` / `schedule` (overrides the config value for that process).

A requested expiry that isn't currently live returns an error listing the available expiries.

## TradingView (DELTAIN:ETHUSD.P)

1. Open **ETHUSD.P** from **Delta Exchange India** on TradingView.
2. Pine Editor → paste [`pine/ip_strategy_levels.pine`](pine/ip_strategy_levels.pine) → Add to chart.
3. After each run, set indicator inputs:
   - **LHS** / **RHS** from the bridge UI or `output/levels.json`
   - Optional: IP for the debug table

TradingView does not allow external apps to change indicator inputs automatically; updating inputs from the bridge copy step is expected.

## Output

`output/levels.json` example fields:

- `expiry_date`, `spot`, `strike_a`, `strike_b`, `ideal_premium`, `lhs`, `rhs`, `daily_lows`, `computed_at` (UTC ISO), `computed_at_ist` (display)

On failure, if `preserve_levels_on_failure: true`, the previous successful `levels.json` is kept and details are written to `output/last_failure.json`.

Each successful run also **appends one row** to a per-expiry `output/history-dd.mm.yy.csv` (e.g. `history-26.12.26.csv` for the 26 Dec 2026 expiry) with `computed_at`, `computed_at_ist`, `ideal_premium`, `lhs`, and `rhs` for historical analysis (Excel, pandas, etc.). The scheduler calls this after every successful interval run. If the expiry is unknown, rows fall back to `output/history.csv`.

## Tests

```bash
pytest
```

## Configuration reference

| Key | Description |
|-----|-------------|
| `interval_minutes` | Scheduler interval |
| `expiry_date` | Pin a specific `DD-MM-YYYY` expiry instead of the nearest live one (also settable from the dashboard or `--expiry`) |
| `premium_field` | `mark_price`, `close`, or `mid` (bid/ask) |
| `daily_low_mode` | `current_session` or `last_closed` 1d candle low |
| `preserve_levels_on_failure` | Keep last good levels when a run fails |
| `order_flow_enabled` | Enable/disable the continuous Buy CE / Buy PE order-flow poller |
| `order_flow_poll_seconds` | Poll interval (seconds) for the order-flow signal |

Environment overrides use prefix `IP_STRATEGY_` (e.g. `IP_STRATEGY_INTERVAL_MINUTES=5`).

## Disclaimer

This software is for research and charting automation only. It is not financial advice. Verify levels against the Delta option chain UI before trading.

## BSE Sensex variant

A parallel implementation for **BSE Sensex** is in [`bse-sensex/`](bse-sensex/README.md). Default interval is **5 minutes**; CLI `sensex-ip`.

## NSE NIFTY / BANKNIFTY variant

[`nse-indices/`](nse-indices/README.md) — NSE option chain via `nseindia.com` APIs; configs `config.nifty.yaml` and `config.banknifty.yaml`; CLI `nse-ip`.

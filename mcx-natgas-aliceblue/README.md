# MCX Natural Gas — ATP/LTP dashboard (Aliceblue)

A live dashboard for MCX Natural Gas options: the ATM strike and its nearest
ITM strike for both CE and PE, each showing **LTP**, **ATP** (average traded
price), and **ATP−LTP** — continuously refreshed, similar in spirit to the
[Delta ETH](../README.md) order-flow panel but using **Aliceblue** as the
data source (Aliceblue has a genuine ATP field; Delta Exchange does not).

This is a separate project from the sibling [`mcx-natgas`](../mcx-natgas/)
build — that one computes an Ideal-Premium/LHS/RHS strategy via a local
mcxindia.com scraping proxy. This one is purely the ATP/LTP table you asked
for, sourced directly from Aliceblue's API.

## Why the Developer Portal App (not just an API Key)

Aliceblue has two API generations. The classic API Key (Profile → API) has
no documented Option Chain endpoint and no confirmed ATP field. The current,
fully-documented API — with a real Option Chain endpoint and a genuine `avg`
(ATP) field on its Market Data endpoint — requires a **Developer Portal App**
(`appCode` + `apiSecret`). Both are free; the App is just an extra one-time
setup step.

## One-time setup

1. Go to https://a3.aliceblueonline.com → **My Apps** → **Create New App**.
2. Set the app's **Redirect URL** to exactly:
   `http://127.0.0.1:8771/` (must match `redirect_host`/`redirect_port` in
   [`config.yaml`](config.yaml) — change both together if you use a different port).
3. Save. You'll get an `appCode` and `apiSecret`.
4. **Do not put these in `config.yaml`.** Export them as environment
   variables (or put them in a local `.env` file in this folder — already
   gitignored):

   ```bash
   export MCX_ATP_APP_CODE="your-app-code"
   export MCX_ATP_API_SECRET="your-api-secret"
   ```

## Install

```bash
cd mcx-natgas-aliceblue
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

## Login (once per day/session)

```bash
mcx-atp login
```

This opens a real browser tab for you to log into Aliceblue. After a
successful login it saves a session token to `.aliceblue_session.json`
(gitignored, `chmod 600`). Re-run `mcx-atp login` whenever the dashboard
reports a 401/session error.

## Run

```bash
mcx-atp run-once     # one snapshot, printed as JSON (for debugging)
mcx-atp serve         # continuously poll + serve the dashboard
```

Open http://127.0.0.1:8770/.

## How ATM/ITM is chosen

Aliceblue's Option Chain response doesn't include a separate underlying
(future) price field, so ATM is approximated using **put-call parity**: the
strike where the CE and PE premiums are closest to each other. ITM (CE) is
the next lower strike; ITM (PE) is the next higher strike. If you find this
heuristic picks the wrong strike compared to what you see in the Aliceblue
app, let me know your actual futures spot and we can switch to a direct
futures-LTP lookup via the contract master instead.

## Config

See [`config.yaml`](config.yaml): `underlying`, `exch`, `strike_interval`
(Aliceblue only accepts 5/10/15/20/25 — check the live chain if this looks
off), `poll_seconds`, `bridge_port`.

## Tests

```bash
pytest
```

Tests cover only the pure ATM/ITM selection and ATP−LTP logic in `chain.py`
(no live API calls).

## Disclaimer

Research and personal use only. Not investment advice. The put-call-parity
ATM heuristic is an approximation, not an exact spot price.

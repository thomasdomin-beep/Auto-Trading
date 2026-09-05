from __future__ import annotations

import json
import logging
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from ip_strategy.config import AppConfig
from ip_strategy.delta_client import DeltaClient
from ip_strategy.models import OrderFlowSignal, StrategyLevels
from ip_strategy.order_flow_runner import OrderFlowState, run_order_flow_once
from ip_strategy.runner import RunState, execute_run

logger = logging.getLogger(__name__)


class _TTLCache:
    """Tiny thread-safe cache: recompute only when the key changes or the
    previous value is older than `ttl_seconds`. Lets the dashboard fetch fresh
    data "on open" (no background poller required) without hammering the
    upstream API on every rapid client poll.
    """

    def __init__(self, ttl_seconds: float) -> None:
        self._ttl = ttl_seconds
        self._lock = threading.Lock()
        self._key: object = object()
        self._value: object = None
        self._ts: float = 0.0

    def get_or_compute(self, key: object, compute_fn):
        with self._lock:
            now = time.monotonic()
            if key == self._key and (now - self._ts) < self._ttl:
                return self._value
        value = compute_fn()
        with self._lock:
            self._key = key
            self._value = value
            self._ts = time.monotonic()
        return value


_levels_cache = _TTLCache(ttl_seconds=15.0)
_orderflow_cache = _TTLCache(ttl_seconds=2.0)
_last_good_levels: StrategyLevels | None = None
_last_good_lock = threading.Lock()

HTML_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <meta name="apple-mobile-web-app-capable" content="yes"/>
  <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent"/>
  <meta name="apple-mobile-web-app-title" content="IP Strategy"/>
  <meta name="theme-color" content="#111827"/>
  <title>IP Strategy Levels</title>
  <style>
    body { font-family: system-ui, sans-serif; max-width: 640px; margin: 2rem auto; padding: 0 1rem; }
    h1 { font-size: 1.25rem; }
    dl { display: grid; grid-template-columns: 10rem 1fr; gap: 0.35rem 1rem; }
    dt { color: #555; }
    dd { margin: 0; font-variant-numeric: tabular-nums; }
    .err { color: #b00020; }
    button, select { margin: 0.5rem 0.5rem 0.5rem 0; padding: 0.5rem 1rem; cursor: pointer; }
    pre { background: #f4f4f4; padding: 0.75rem; overflow: auto; font-size: 0.85rem; }
    .hint { color: #666; font-size: 0.9rem; margin-top: 1.5rem; }
    .expiry-row { display: flex; align-items: center; flex-wrap: wrap; gap: 0.25rem; margin: 0.75rem 0; }
    #of-banner { font-weight: bold; padding: 0.6rem 1rem; border-radius: 0.35rem; }
    .of-neutral { background: #eee; color: #444; }
    .of-buy-ce { background: #0b6b2a; color: #fff; }
    .of-buy-pe { background: #0b3f8a; color: #fff; }
    .of-error { background: #b00020; color: #fff; }
  </style>
</head>
<body>
  <h1>ETHUSD.P Ideal Premium — levels</h1>
  <div class="expiry-row">
    <label for="expiry-select">Expiry:</label>
    <select id="expiry-select"><option value="">Loading…</option></select>
    <button type="button" id="fetch-expiry">Fetch selected expiry</button>
    <button type="button" id="fetch-nearest">Use nearest (auto)</button>
  </div>
  <p id="status">Loading…</p>
  <dl id="fields"></dl>
  <button type="button" id="copy-sr">Copy LHS &amp; RHS (Pine inputs)</button>
  <button type="button" id="copy-json">Copy full JSON</button>
  <pre id="raw"></pre>
  <p class="hint">Paste LHS and RHS into the Pine indicator inputs on DELTAIN:ETHUSD.P. Pick an expiry above and click Fetch to (re)compute levels for it; the dashboard keeps auto-refreshing that expiry afterwards.</p>

  <h1>Order-flow signal (ATP−LTP, ITM vs ATM)</h1>
  <p id="of-banner" class="of-neutral">Waiting for first poll…</p>
  <dl id="of-fields"></dl>
  <p class="hint">Buy CE fires when the nearest ITM call's (ATP−LTP) drops below the ATM call's. Buy PE fires when the nearest ITM put's (ATP−LTP) drops below the ATM put's. ATP = day's turnover_usd / volume; LTP = last close.</p>

  <script>
    let latest = null;

    async function loadExpiries() {
      const sel = document.getElementById('expiry-select');
      try {
        const r = await fetch('/api/expiries');
        const data = await r.json();
        const options = data.expiries || [];
        const current = latest && latest.expiry_date;
        sel.innerHTML = '';
        for (const exp of options) {
          const opt = document.createElement('option');
          opt.value = exp;
          opt.textContent = exp;
          if (exp === current) opt.selected = true;
          sel.appendChild(opt);
        }
        if (!options.length) {
          const opt = document.createElement('option');
          opt.value = '';
          opt.textContent = 'No live expiries found';
          sel.appendChild(opt);
        }
      } catch (e) {
        sel.innerHTML = '<option value="">Failed to load expiries</option>';
      }
    }

    async function load() {
      const r = await fetch('/api/levels');
      latest = await r.json();
      renderLevels();
    }

    function renderLevels() {
      document.getElementById('raw').textContent = JSON.stringify(latest, null, 2);
      const st = document.getElementById('status');
      const dl = document.getElementById('fields');
      dl.innerHTML = '';
      if (!latest.success) {
        st.innerHTML = '<span class="err">Last run failed: ' + (latest.error || 'unknown') + '</span>';
      } else {
        st.textContent = 'Last successful computation';
      }
      const rows = [
        ['Computed at (IST)', latest.computed_at_ist || latest.computed_at],
        ['Expiry', latest.expiry_date],
        ['Spot', latest.spot],
        ['Ideal Premium (IP)', latest.ideal_premium],
        ['LHS', latest.lhs],
        ['RHS', latest.rhs],
      ];
      for (const [k, v] of rows) {
        const dt = document.createElement('dt'); dt.textContent = k;
        const dd = document.createElement('dd'); dd.textContent = v == null ? '—' : v;
        dl.appendChild(dt); dl.appendChild(dd);
      }
      const sel = document.getElementById('expiry-select');
      if (latest.expiry_date) {
        for (const opt of sel.options) {
          opt.selected = opt.value === latest.expiry_date;
        }
      }
    }

    async function triggerRun(expiry) {
      const st = document.getElementById('status');
      st.textContent = expiry ? ('Computing for expiry ' + expiry + '…') : 'Computing for nearest expiry…';
      try {
        const r = await fetch('/api/run', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ expiry: expiry || null }),
        });
        latest = await r.json();
        renderLevels();
        await loadExpiries();
      } catch (e) {
        st.innerHTML = '<span class="err">Fetch failed: ' + e + '</span>';
      }
    }

    document.getElementById('fetch-expiry').onclick = () => {
      const sel = document.getElementById('expiry-select');
      if (!sel.value) return alert('Pick an expiry first');
      triggerRun(sel.value);
    };
    document.getElementById('fetch-nearest').onclick = () => triggerRun(null);
    document.getElementById('copy-sr').onclick = () => {
      if (!latest || latest.lhs == null) return alert('No LHS/RHS');
      navigator.clipboard.writeText(String(latest.lhs) + '\\n' + String(latest.rhs));
    };
    document.getElementById('copy-json').onclick = () => {
      navigator.clipboard.writeText(JSON.stringify(latest, null, 2));
    };
    load().then(loadExpiries);
    setInterval(load, 30000);

    async function loadOrderFlow() {
      const banner = document.getElementById('of-banner');
      const dl = document.getElementById('of-fields');
      try {
        const r = await fetch('/api/orderflow');
        const of = await r.json();
        dl.innerHTML = '';
        if (!of || of.success === false) {
          banner.className = 'of-error';
          banner.textContent = 'Order-flow error: ' + ((of && of.error) || 'no data yet');
          return;
        }
        const msgs = of.messages || [];
        if (msgs.includes('Buy CE') && msgs.includes('Buy PE')) {
          banner.className = 'of-buy-ce';
          banner.textContent = 'Buy CE & Buy PE';
        } else if (msgs.includes('Buy CE')) {
          banner.className = 'of-buy-ce';
          banner.textContent = 'Buy CE';
        } else if (msgs.includes('Buy PE')) {
          banner.className = 'of-buy-pe';
          banner.textContent = 'Buy PE';
        } else {
          banner.className = 'of-neutral';
          banner.textContent = 'No signal';
        }
        const fmt = (leg) => leg ? ('ATP ' + leg.atp + ' / LTP ' + leg.ltp + ' / diff ' + leg.atp_minus_ltp) : '\u2014';
        const rows = [
          ['Computed at (IST)', of.computed_at_ist],
          ['Expiry', of.expiry_date],
          ['Spot', of.spot],
          ['ATM strike', of.atm_strike],
          ['CE ATM', fmt(of.ce_atm)],
          ['CE ITM strike / values', (of.ce_itm_strike == null ? '\u2014' : of.ce_itm_strike) + ' \u2014 ' + fmt(of.ce_itm)],
          ['PE ATM', fmt(of.pe_atm)],
          ['PE ITM strike / values', (of.pe_itm_strike == null ? '\u2014' : of.pe_itm_strike) + ' \u2014 ' + fmt(of.pe_itm)],
        ];
        for (const [k, v] of rows) {
          const dt = document.createElement('dt'); dt.textContent = k;
          const dd = document.createElement('dd'); dd.textContent = v == null ? '\u2014' : v;
          dl.appendChild(dt); dl.appendChild(dd);
        }
      } catch (e) {
        banner.className = 'of-error';
        banner.textContent = 'Order-flow fetch failed: ' + e;
      }
    }
    loadOrderFlow();
    setInterval(loadOrderFlow, 2000);
  </script>
</body>
</html>
"""


def make_handler(
    cfg: AppConfig,
    state: RunState | None = None,
    of_state: OrderFlowState | None = None,
) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            logger.debug(format, *args)

        def _send_json(self, data: object, status: int = 200) -> None:
            body = json.dumps(data, default=str).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            if self.path in ("/", "/index.html"):
                body = HTML_PAGE.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if self.path == "/api/levels":
                expiry = state.get_expiry() if state is not None else None

                def _compute_levels() -> StrategyLevels:
                    global _last_good_levels
                    levels = execute_run(cfg, expiry_override=expiry, state=state, persist=False)
                    if levels.success:
                        with _last_good_lock:
                            _last_good_levels = levels
                    elif cfg.preserve_levels_on_failure:
                        with _last_good_lock:
                            if _last_good_levels is not None:
                                levels = _last_good_levels
                    return levels

                levels = _levels_cache.get_or_compute(expiry, _compute_levels)
                self._send_json(levels.model_dump(mode="json"), 200 if levels.success else 502)
                return
            if self.path == "/api/expiries":
                try:
                    with DeltaClient(
                        cfg.delta_base_url, cfg.candle_request_delay_seconds
                    ) as client:
                        expiries = client.list_live_expiries(cfg.underlying)
                    self._send_json({"expiries": expiries})
                except Exception as e:
                    logger.exception("Failed to list expiries: %s", e)
                    self._send_json({"expiries": [], "error": str(e)}, 502)
                return
            if self.path == "/api/orderflow":
                expiry = state.get_expiry() if state is not None else None

                def _compute_orderflow() -> OrderFlowSignal:
                    return run_order_flow_once(cfg, expiry_override=expiry)

                signal = _orderflow_cache.get_or_compute(expiry, _compute_orderflow)
                self._send_json(signal.model_dump(mode="json"), 200 if signal.success else 502)
                return
            self.send_error(404)

        def do_POST(self) -> None:
            if self.path != "/api/run":
                self.send_error(404)
                return
            length = int(self.headers.get("Content-Length", 0) or 0)
            raw = self.rfile.read(length) if length else b""
            try:
                payload = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                payload = {}
            expiry = payload.get("expiry") or None

            levels = execute_run(cfg, expiry_override=expiry)
            if state is not None and levels.success:
                state.set_expiry(expiry)
            self._send_json(levels.model_dump(mode="json"), 200 if levels.success else 502)

    return Handler


def _bind_host(cfg: AppConfig) -> str:
    # Bind all local IPv4 interfaces so 127.0.0.1 and LAN IP both work.
    if cfg.bridge_host in ("127.0.0.1", "localhost"):
        return "0.0.0.0"
    return cfg.bridge_host


def serve(
    cfg: AppConfig,
    state: RunState | None = None,
    of_state: OrderFlowState | None = None,
) -> None:
    handler = make_handler(cfg, state, of_state)
    host = _bind_host(cfg)
    port = cfg.bridge_port

    class ReuseThreadingHTTPServer(ThreadingHTTPServer):
        allow_reuse_address = True

    server = ReuseThreadingHTTPServer((host, port), handler)
    logger.info("Bridge UI http://127.0.0.1:%s/ (also http://localhost:%s/)", port, port)
    server.serve_forever()


def serve_in_thread(
    cfg: AppConfig,
    state: RunState | None = None,
    of_state: OrderFlowState | None = None,
) -> None:
    serve(cfg, state, of_state)

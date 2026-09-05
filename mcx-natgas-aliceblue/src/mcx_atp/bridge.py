from __future__ import annotations

import json
import logging
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from mcx_atp.config import AppConfig
from mcx_atp.runner import ChainState

logger = logging.getLogger(__name__)

HTML_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>MCX Natural Gas — ITM/ATM ATP-LTP</title>
  <style>
    body { font-family: system-ui, sans-serif; max-width: 720px; margin: 2rem auto; padding: 0 1rem; }
    h1 { font-size: 1.25rem; }
    table { border-collapse: collapse; width: 100%; margin-top: 1rem; }
    th, td { border: 1px solid #ddd; padding: 0.4rem 0.6rem; text-align: right; font-variant-numeric: tabular-nums; }
    th:first-child, td:first-child { text-align: left; }
    .err { color: #b00020; }
    #banner { font-weight: bold; padding: 0.6rem 1rem; border-radius: 0.35rem; margin-top: 1rem; }
    .neutral { background: #eee; color: #444; }
    .buy-ce { background: #0b6b2a; color: #fff; }
    .buy-pe { background: #0b3f8a; color: #fff; }
    .error { background: #b00020; color: #fff; }
    .hint { color: #666; font-size: 0.9rem; margin-top: 1.5rem; }
    dl { display: grid; grid-template-columns: 8rem 1fr; gap: 0.35rem 1rem; margin-top: 1rem; }
    dt { color: #555; } dd { margin: 0; }
  </style>
</head>
<body>
  <h1>MCX Natural Gas — ITM/ATM options (LTP, ATP, ATP−LTP)</h1>
  <p id="status">Loading…</p>
  <dl id="meta"></dl>
  <table id="chain">
    <thead><tr><th>Leg</th><th>Strike</th><th>Symbol</th><th>LTP</th><th>ATP</th><th>ATP−LTP</th></tr></thead>
    <tbody id="rows"></tbody>
  </table>
  <p id="banner" class="neutral">Waiting for first poll…</p>
  <p class="hint">ATM = strike where CE and PE premiums are closest (put-call parity). ITM (CE) = next lower
  strike; ITM (PE) = next higher strike. ATP = average traded price for the session (Aliceblue Market Data
  "avg"). Buy CE/Buy PE fires when the ITM leg's ATP−LTP drops below the ATM leg's.</p>

  <script>
    function fmt(v) { return v == null ? '—' : (typeof v === 'number' ? v.toFixed(2) : v); }

    function row(label, strike, leg) {
      const tr = document.createElement('tr');
      const cells = [label, fmt(strike), leg ? leg.symbol : '—', fmt(leg && leg.ltp), fmt(leg && leg.atp), fmt(leg && leg.atp_minus_ltp)];
      for (const c of cells) { const td = document.createElement('td'); td.textContent = c; tr.appendChild(td); }
      return tr;
    }

    async function load() {
      const status = document.getElementById('status');
      const banner = document.getElementById('banner');
      const meta = document.getElementById('meta');
      const rows = document.getElementById('rows');
      try {
        const r = await fetch('/api/chain');
        const data = await r.json();
        if (!data || data.success === false) {
          status.innerHTML = '<span class="err">' + (data && data.error ? data.error : 'No data yet') + '</span>';
          banner.className = 'error';
          banner.textContent = 'Error';
          rows.innerHTML = '';
          return;
        }
        status.textContent = 'Last successful poll';
        meta.innerHTML = '';
        const metaRows = [
          ['Computed at (IST)', data.computed_at_ist],
          ['Underlying', data.underlying],
          ['Expiry', data.expiry_date],
          ['ATM strike', data.atm_strike],
        ];
        for (const [k, v] of metaRows) {
          const dt = document.createElement('dt'); dt.textContent = k;
          const dd = document.createElement('dd'); dd.textContent = v == null ? '—' : v;
          meta.appendChild(dt); meta.appendChild(dd);
        }
        rows.innerHTML = '';
        rows.appendChild(row('CE ATM', data.atm_strike, data.ce_atm));
        rows.appendChild(row('CE ITM', data.ce_itm_strike, data.ce_itm));
        rows.appendChild(row('PE ATM', data.atm_strike, data.pe_atm));
        rows.appendChild(row('PE ITM', data.pe_itm_strike, data.pe_itm));

        const msgs = data.messages || [];
        if (msgs.includes('Buy CE') && msgs.includes('Buy PE')) { banner.className = 'buy-ce'; banner.textContent = 'Buy CE & Buy PE'; }
        else if (msgs.includes('Buy CE')) { banner.className = 'buy-ce'; banner.textContent = 'Buy CE'; }
        else if (msgs.includes('Buy PE')) { banner.className = 'buy-pe'; banner.textContent = 'Buy PE'; }
        else { banner.className = 'neutral'; banner.textContent = 'No signal'; }
      } catch (e) {
        status.innerHTML = '<span class="err">Fetch failed: ' + e + '</span>';
      }
    }
    load();
    setInterval(load, 3000);
  </script>
</body>
</html>
"""


def make_handler(state: ChainState) -> type[BaseHTTPRequestHandler]:
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
            if self.path == "/api/chain":
                snapshot = state.get()
                if snapshot is None:
                    self._send_json({"success": False, "error": "Not polled yet"}, 404)
                    return
                self._send_json(snapshot.model_dump(mode="json"), 200 if snapshot.success else 502)
                return
            self.send_error(404)

    return Handler


class ReuseThreadingHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True


def serve(cfg: AppConfig, state: ChainState) -> None:
    server = ReuseThreadingHTTPServer((cfg.bridge_host, cfg.bridge_port), make_handler(state))
    logger.info("Bridge UI http://%s:%s/", cfg.bridge_host, cfg.bridge_port)
    server.serve_forever()

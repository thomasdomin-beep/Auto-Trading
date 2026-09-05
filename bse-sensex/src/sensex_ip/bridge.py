from __future__ import annotations

import json
import logging
from http.server import BaseHTTPRequestHandler, HTTPServer

from sensex_ip.config import AppConfig

logger = logging.getLogger(__name__)

HTML_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Sensex IP Strategy Levels</title>
  <style>
    body { font-family: system-ui, sans-serif; max-width: 640px; margin: 2rem auto; padding: 0 1rem; }
    h1 { font-size: 1.25rem; }
    dl { display: grid; grid-template-columns: 10rem 1fr; gap: 0.35rem 1rem; }
    dt { color: #555; }
    dd { margin: 0; font-variant-numeric: tabular-nums; }
    .err { color: #b00020; }
    button { margin: 0.5rem 0.5rem 0.5rem 0; padding: 0.5rem 1rem; cursor: pointer; }
    pre { background: #f4f4f4; padding: 0.75rem; overflow: auto; font-size: 0.85rem; }
    .hint { color: #666; font-size: 0.9rem; margin-top: 1.5rem; }
  </style>
</head>
<body>
  <h1>BSE Sensex Ideal Premium — levels</h1>
  <p id="status">Loading…</p>
  <dl id="fields"></dl>
  <button type="button" id="copy-sr">Copy Support &amp; Resistance (Pine inputs)</button>
  <button type="button" id="copy-json">Copy full JSON</button>
  <pre id="raw"></pre>
  <p class="hint">Paste Support and Resistance into the Pine indicator on BSE:SENSEX (or your Sensex spot chart). Refresh after each run (default every 5 minutes).</p>
  <script>
    let latest = null;
    async function load() {
      const r = await fetch('/api/levels');
      latest = await r.json();
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
        ['Strike A', latest.strike_a],
        ['Strike B', latest.strike_b],
        ['Ideal Premium (IP)', latest.ideal_premium],
        ['Support', latest.support],
        ['Resistance', latest.resistance],
      ];
      for (const [k, v] of rows) {
        const dt = document.createElement('dt'); dt.textContent = k;
        const dd = document.createElement('dd'); dd.textContent = v == null ? '—' : v;
        dl.appendChild(dt); dl.appendChild(dd);
      }
    }
    document.getElementById('copy-sr').onclick = () => {
      if (!latest || latest.support == null) return alert('No support/resistance');
      navigator.clipboard.writeText(String(latest.support) + '\\n' + String(latest.resistance));
    };
    document.getElementById('copy-json').onclick = () => {
      navigator.clipboard.writeText(JSON.stringify(latest, null, 2));
    };
    load();
    setInterval(load, 30000);
  </script>
</body>
</html>
"""


def make_handler(cfg: AppConfig) -> type[BaseHTTPRequestHandler]:
    levels_file = cfg.output_path / "levels.json"

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
                if not levels_file.is_file():
                    self._send_json(
                        {
                            "success": False,
                            "error": "No levels.json yet; run sensex-ip run-once",
                        },
                        404,
                    )
                    return
                data = json.loads(levels_file.read_text(encoding="utf-8"))
                self._send_json(data)
                return
            self.send_error(404)

    return Handler


def serve(cfg: AppConfig) -> None:
    handler = make_handler(cfg)
    server = HTTPServer((cfg.bridge_host, cfg.bridge_port), handler)
    logger.info("Bridge UI http://%s:%s/", cfg.bridge_host, cfg.bridge_port)
    server.serve_forever()


def serve_in_thread(cfg: AppConfig) -> None:
    serve(cfg)

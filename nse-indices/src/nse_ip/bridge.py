from __future__ import annotations

import json
import logging
from http.server import BaseHTTPRequestHandler, HTTPServer

from nse_ip.config import AppConfig

logger = logging.getLogger(__name__)

HTML = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"/><title>NSE IP Levels</title>
<style>body{font-family:system-ui,sans-serif;max-width:640px;margin:2rem auto;padding:0 1rem}
dl{display:grid;grid-template-columns:10rem 1fr;gap:.35rem 1rem}dt{color:#555}dd{margin:0}
.err{color:#b00020}button{margin:.5rem .5rem .5rem 0;padding:.5rem 1rem}
pre{background:#f4f4f4;padding:.75rem;font-size:.85rem}</style></head>
<body><h1 id="title">NSE IP — levels</h1><p id="status">Loading…</p><dl id="fields"></dl>
<button id="copy-sr">Copy Support &amp; Resistance</button><button id="copy-json">Copy JSON</button>
<pre id="raw"></pre>
<script>
let latest=null;
async function load(){const r=await fetch('/api/levels');latest=await r.json();
document.getElementById('raw').textContent=JSON.stringify(latest,null,2);
const st=document.getElementById('status');const dl=document.getElementById('fields');dl.innerHTML='';
document.getElementById('title').textContent=(latest.underlying||'NSE')+' IP — levels';
st.innerHTML=latest.success?'Last successful run':'<span class="err">Failed: '+(latest.error||'?')+'</span>';
[['Underlying',latest.underlying],['Computed at (IST)',latest.computed_at_ist||latest.computed_at],['Expiry',latest.expiry_date],['Spot',latest.spot],['Strike A',latest.strike_a],['Strike B',latest.strike_b],['IP',latest.ideal_premium],['Support',latest.support],['Resistance',latest.resistance]].forEach(([k,v])=>{const dt=document.createElement('dt');dt.textContent=k;const dd=document.createElement('dd');dd.textContent=v??'—';dl.appendChild(dt);dl.appendChild(dd);});}
document.getElementById('copy-sr').onclick=()=>{if(!latest?.support)return alert('No levels');navigator.clipboard.writeText(String(latest.support)+'\\n'+String(latest.resistance));};
document.getElementById('copy-json').onclick=()=>navigator.clipboard.writeText(JSON.stringify(latest,null,2));
load();setInterval(load,30000);
</script></body></html>"""


def make_handler(cfg: AppConfig) -> type[BaseHTTPRequestHandler]:
    levels_file = cfg.output_path / "levels.json"

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            logger.debug(format, *args)

        def do_GET(self) -> None:
            if self.path in ("/", "/index.html"):
                body = HTML.encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if self.path == "/api/levels":
                if not levels_file.is_file():
                    self.send_response(404)
                    self.end_headers()
                    self.wfile.write(b'{"success":false,"error":"run nse-ip run-once first"}')
                    return
                data = json.loads(levels_file.read_text())
                body = json.dumps(data, default=str).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(body)
                return
            self.send_error(404)

    return Handler


def serve(cfg: AppConfig) -> None:
    server = HTTPServer((cfg.bridge_host, cfg.bridge_port), make_handler(cfg))
    logger.info("Bridge http://%s:%s/", cfg.bridge_host, cfg.bridge_port)
    server.serve_forever()


def serve_in_thread(cfg: AppConfig) -> None:
    serve(cfg)

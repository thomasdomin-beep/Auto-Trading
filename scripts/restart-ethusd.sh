#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

pkill -f "ip-strategy schedule" 2>/dev/null || true
sleep 1

mkdir -p output
nohup .venv/bin/ip-strategy schedule -c config.yaml --with-bridge >> output/ethusd.log 2>&1 &
PID=$!
echo "ETHUSD started (PID $PID)"
echo "UI: http://127.0.0.1:8765/"
echo "Log: $ROOT/output/ethusd.log"

sleep 8
if curl -sf -o /dev/null http://127.0.0.1:8765/; then
  echo "Bridge UI is responding."
else
  echo "Bridge UI not responding yet — check output/ethusd.log"
fi

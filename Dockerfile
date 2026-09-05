FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir -e .

COPY config.yaml ./

ENV IP_STRATEGY_BRIDGE_HOST=0.0.0.0

EXPOSE 8765

# Render (and similar PaaS) inject $PORT at runtime; fall back to 8765 locally.
CMD ["sh", "-c", "IP_STRATEGY_BRIDGE_PORT=${PORT:-8765} ip-strategy serve-bridge -c config.yaml"]

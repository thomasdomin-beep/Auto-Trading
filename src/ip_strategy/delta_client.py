from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

import httpx

from ip_strategy.config import PremiumField
from ip_strategy.models import OptionLeg, OrderFlowLeg, OrderFlowStrikeRow, StrikeRow
from ip_strategy.symbols import product_expiry_to_api


class DeltaClient:
    def __init__(self, base_url: str, candle_delay: float = 0.15) -> None:
        self.base_url = base_url.rstrip("/")
        self.candle_delay = candle_delay
        self._client = httpx.Client(
            base_url=self.base_url,
            headers={"Accept": "application/json"},
            timeout=30.0,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> DeltaClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        r = self._client.get(path, params=params)
        r.raise_for_status()
        body = r.json()
        if not body.get("success", True):
            raise RuntimeError(f"Delta API error: {body}")
        return body.get("result", body)

    def get_products(
        self,
        underlying: str,
        contract_types: str = "call_options,put_options",
    ) -> list[dict[str, Any]]:
        result = self._get(
            "/v2/products",
            params={
                "contract_types": contract_types,
                "states": "live",
            },
        )
        if not isinstance(result, list):
            return []
        return [
            p
            for p in result
            if p.get("underlying_asset", {}).get("symbol") == underlying
            or p.get("underlying_asset_symbol") == underlying
        ]

    def list_live_expiries(self, underlying: str) -> list[str]:
        """Return all live expiry dates (DD-MM-YYYY), soonest first, de-duplicated."""
        products = self.get_products(underlying)
        now = datetime.now(timezone.utc)
        seen: dict[str, datetime] = {}
        for p in products:
            sym = p.get("symbol", "")
            if not sym.startswith(("C-", "P-")):
                continue
            st = p.get("settlement_time")
            if not st:
                continue
            try:
                dt = datetime.fromisoformat(st.replace("Z", "+00:00"))
            except ValueError:
                continue
            if dt < now:
                continue
            api_exp = product_expiry_to_api(st)
            if api_exp not in seen or dt < seen[api_exp]:
                seen[api_exp] = dt
        return [exp for exp, _ in sorted(seen.items(), key=lambda kv: kv[1])]

    def nearest_expiry_date(self, underlying: str) -> str | None:
        expiries = self.list_live_expiries(underlying)
        return expiries[0] if expiries else None

    def get_option_chain_tickers(
        self, underlying: str, expiry_date: str
    ) -> list[dict[str, Any]]:
        result = self._get(
            "/v2/tickers",
            params={
                "contract_types": "call_options,put_options",
                "underlying_asset_symbols": underlying,
                "expiry_date": expiry_date,
            },
        )
        if isinstance(result, list):
            return result
        return []

    def get_ticker(self, symbol: str) -> dict[str, Any]:
        result = self._get(f"/v2/tickers/{symbol}")
        if isinstance(result, dict):
            return result
        raise RuntimeError(f"Unexpected ticker response for {symbol}")

    def get_candles(
        self,
        symbol: str,
        resolution: str,
        start: int,
        end: int,
    ) -> list[dict[str, Any]]:
        result = self._get(
            "/v2/history/candles",
            params={
                "symbol": symbol,
                "resolution": resolution,
                "start": start,
                "end": end,
            },
        )
        if isinstance(result, list):
            return result
        return []

    @staticmethod
    def extract_premium(ticker: dict[str, Any], field: PremiumField) -> float | None:
        if field == "mid":
            quotes = ticker.get("quotes") or {}
            bid = quotes.get("best_bid")
            ask = quotes.get("best_ask")
            if bid is not None and ask is not None:
                return (float(bid) + float(ask)) / 2.0
            return None
        if field == "close":
            val = ticker.get("close")
        else:
            val = ticker.get("mark_price") or ticker.get("close")
        if val is None:
            return None
        return float(val)

    def merge_chain_by_strike(
        self, tickers: list[dict[str, Any]], premium_field: PremiumField
    ) -> list[StrikeRow]:
        by_strike: dict[float, StrikeRow] = {}
        for t in tickers:
            sym = t.get("symbol", "")
            strike_raw = t.get("strike_price")
            if strike_raw is None:
                continue
            strike = float(strike_raw)
            premium = self.extract_premium(t, premium_field)
            if premium is None:
                continue
            row = by_strike.get(strike)
            if row is None:
                row = StrikeRow(strike=strike)
                by_strike[strike] = row
            leg = OptionLeg(symbol=sym, premium=premium)
            if sym.startswith("C-"):
                row.ce = leg
            elif sym.startswith("P-"):
                row.pe = leg
        return sorted(by_strike.values(), key=lambda r: r.strike)

    @staticmethod
    def extract_atp(ticker: dict[str, Any]) -> float | None:
        """Average Traded Price: day's turnover_usd / day's volume (a VWAP-style average)."""
        turnover_usd = ticker.get("turnover_usd")
        volume = ticker.get("volume")
        if turnover_usd is None or volume is None:
            return None
        try:
            volume_f = float(volume)
        except (TypeError, ValueError):
            return None
        if volume_f == 0:
            return None
        return float(turnover_usd) / volume_f

    def merge_chain_by_strike_atp_ltp(
        self, tickers: list[dict[str, Any]]
    ) -> list[OrderFlowStrikeRow]:
        """Build a strike ladder of (ATP, LTP) per CE/PE leg for order-flow monitoring.

        ATP = turnover_usd / volume; LTP = ticker `close` (last traded price).
        """
        by_strike: dict[float, OrderFlowStrikeRow] = {}
        for t in tickers:
            sym = t.get("symbol", "")
            strike_raw = t.get("strike_price")
            if strike_raw is None:
                continue
            strike = float(strike_raw)
            atp = self.extract_atp(t)
            ltp = self.extract_premium(t, "close")
            if atp is None and ltp is None:
                continue
            row = by_strike.get(strike)
            if row is None:
                row = OrderFlowStrikeRow(strike=strike)
                by_strike[strike] = row
            leg = OrderFlowLeg(symbol=sym, atp=atp, ltp=ltp)
            if sym.startswith("C-"):
                row.ce = leg
            elif sym.startswith("P-"):
                row.pe = leg
        return sorted(by_strike.values(), key=lambda r: r.strike)

    def fetch_daily_low(
        self,
        symbol: str,
        mode: str,
    ) -> float | None:
        end = int(datetime.now(timezone.utc).timestamp())
        start = end - 86400 * 14
        candles = self.get_candles(symbol, "1d", start, end)
        time.sleep(self.candle_delay)
        if not candles:
            return None
        candles = sorted(candles, key=lambda c: c.get("time", 0))
        if mode == "last_closed" and len(candles) >= 2:
            bar = candles[-2]
        else:
            bar = candles[-1]
        low = bar.get("low")
        if low is None:
            return None
        return float(low)

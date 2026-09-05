from __future__ import annotations

import time
from typing import Any

from curl_cffi import requests as curl_requests

from nse_ip.config import DailyLowMode, PremiumField


def _num(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class NseIndexClient:
    """NSE India option chain (same JSON APIs as nseindia.com option-chain page)."""

    def __init__(
        self,
        base_url: str,
        symbol: str,
        chart_delay: float = 0.2,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.symbol = symbol.upper()
        self.chart_delay = chart_delay
        self._session = curl_requests.Session(impersonate="chrome120")
        self._session.headers.update(
            {
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "en-US,en;q=0.9",
                "Referer": f"{self.base_url}/option-chain",
            }
        )

    def close(self) -> None:
        self._session.close()

    def __enter__(self) -> NseIndexClient:
        self.warm_session()
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def warm_session(self) -> None:
        self._session.get(f"{self.base_url}/", timeout=30)
        self._session.get(f"{self.base_url}/option-chain", timeout=30)

    def _api_get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        url = f"{self.base_url}/api/{path.lstrip('/')}"
        r = self._session.get(url, params=params or {}, timeout=30)
        r.raise_for_status()
        text = r.text.strip()
        if not text.startswith("{"):
            raise RuntimeError(
                f"NSE non-JSON from {path}: status={r.status_code} body={text[:120]}"
            )
        return r.json()

    def nearest_expiry(self) -> str:
        data = self._api_get(
            "option-chain-contract-info",
            {"symbol": self.symbol},
        )
        dates = data.get("expiryDates") or []
        if not dates:
            raise RuntimeError(f"No expiries for {self.symbol}")
        return str(dates[0])

    def fetch_option_chain(self, expiry: str) -> dict[str, Any]:
        params = {
            "type": "Indices",
            "symbol": self.symbol,
            "expiry": expiry,
        }
        return self._api_get("option-chain-v3", params)

    @staticmethod
    def _leg_from_side(side: dict[str, Any] | None, field: PremiumField) -> tuple[float | None, str | None]:
        if not side:
            return None, None
        ident = side.get("identifier")
        if field == "mid":
            bid = _num(side.get("buyPrice1") or side.get("bidprice"))
            ask = _num(side.get("sellPrice1") or side.get("askPrice"))
            if bid is not None and ask is not None:
                return (bid + ask) / 2.0, ident
        premium = _num(side.get("lastPrice"))
        return premium, ident

    def merge_chain_by_strike(
        self, payload: dict[str, Any], expiry: str, premium_field: PremiumField
    ) -> tuple[list, float]:
        from nse_ip.models import OptionLeg, StrikeRow

        records = payload.get("records") or {}
        spot = float(records.get("underlyingValue") or 0)
        rows_in = records.get("data") or []
        by_strike: dict[float, StrikeRow] = {}

        for row in rows_in:
            row_exp = row.get("expiryDate")
            if row_exp is not None and row_exp != expiry:
                continue
            strike = _num(row.get("strikePrice"))
            if strike is None:
                continue
            entry = by_strike.get(strike)
            if entry is None:
                entry = StrikeRow(strike=strike)
                by_strike[strike] = entry
            ce_p, ce_id = self._leg_from_side(row.get("CE"), premium_field)
            pe_p, pe_id = self._leg_from_side(row.get("PE"), premium_field)
            if ce_p is not None and ce_id:
                entry.ce = OptionLeg(
                    symbol=ce_id, identifier=ce_id, premium=ce_p
                )
            if pe_p is not None and pe_id:
                entry.pe = OptionLeg(
                    symbol=pe_id, identifier=pe_id, premium=pe_p
                )

        chain = sorted(by_strike.values(), key=lambda r: r.strike)
        if spot <= 0:
            raise RuntimeError("Missing underlyingValue in NSE option chain")
        return chain, spot

    def fetch_daily_low(self, identifier: str, mode: DailyLowMode) -> float | None:
        time.sleep(self.chart_delay)
        data = self._api_get(
            "chart-databyindex",
            {"index": identifier, "indices": "false"},
        )
        graph = data.get("grapthData") or data.get("graphData") or []
        lows: list[float] = []
        for pt in graph:
            if isinstance(pt, (list, tuple)) and len(pt) >= 2:
                v = _num(pt[1])
                if v is not None:
                    lows.append(v)
        if lows:
            return min(lows)
        close = _num(data.get("closePrice"))
        if mode == "last_closed" and close is not None:
            return close
        return close

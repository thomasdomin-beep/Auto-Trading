from __future__ import annotations

from typing import Any

import httpx

from mcx_ip.models import OptionLeg, StrikeRow


def _num(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class McxProxyError(RuntimeError):
    """Raised when the local mcx-proxy (option-premium-calculator/mcx-proxy) is
    unreachable, not running, or returns an error."""


class McxClient:
    """Fetches MCX option chain data via the local mcx-proxy.

    The proxy lives in the sibling `option-premium-calculator/mcx-proxy`
    project (a small Playwright-driven Node server) because MCX's option
    chain endpoint (https://www.mcxindia.com/GetOptionChain) only allows
    CORS from mcxindia.com and blocks plain HTTP clients behind Akamai bot
    protection. Start it with `cd mcx-proxy && npm start` before running
    this client - see that project's README for details.
    """

    def __init__(self, base_url: str, instrument: str, symbol: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.instrument = instrument
        self.symbol = symbol.upper()
        self._client = httpx.Client(timeout=60.0)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "McxClient":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def _get(self, path: str, params: dict[str, Any]) -> Any:
        url = f"{self.base_url}{path}"
        try:
            r = self._client.get(url, params=params)
        except httpx.ConnectError as exc:
            raise McxProxyError(
                f"Could not reach the local MCX proxy at {self.base_url}. "
                "Make sure it's running: cd option-premium-calculator/mcx-proxy && npm start"
            ) from exc
        try:
            body = r.json()
        except ValueError:
            body = {}
        if r.status_code != 200:
            raise McxProxyError(
                body.get("error") or f"MCX proxy request failed ({r.status_code})."
            )
        return body

    def list_expiries(self) -> list[dict[str, str]]:
        body = self._get(
            "/api/expiries", {"instrument": self.instrument, "symbol": self.symbol}
        )
        return body.get("data") or []

    def nearest_expiry(self) -> str | None:
        """First entry from the live expiry dropdown (MCX lists them nearest-first)."""
        expiries = self.list_expiries()
        return expiries[0]["value"] if expiries else None

    def fetch_option_chain(self, expiry: str) -> dict[str, Any]:
        return self._get(
            "/api/option-chain",
            {"instrument": self.instrument, "symbol": self.symbol, "expiry": expiry},
        )

    def build_symbol(self, expiry: str, strike: float, is_call: bool) -> str:
        """Display-only contract label, e.g. NATURALGAS23SEP2026C2470 (MCX's
        option chain feed doesn't return a contract symbol/identifier)."""
        return f"{self.symbol}{expiry.upper()}{'C' if is_call else 'P'}{strike:g}"

    def merge_chain_by_strike(
        self, payload: dict[str, Any], expiry: str
    ) -> tuple[list[StrikeRow], float]:
        rows_in = payload.get("Data") or []
        if not rows_in:
            raise McxProxyError(
                f"No option chain rows returned for {self.symbol} expiring {expiry}."
            )

        spot = _num(rows_in[0].get("UnderlyingValue"))
        by_strike: dict[float, StrikeRow] = {}
        for row in rows_in:
            ce_strike = row.get("CE_StrikePrice")
            strike = _num(ce_strike if ce_strike is not None else row.get("PE_StrikePrice"))
            if strike is None:
                continue
            entry = by_strike.get(strike)
            if entry is None:
                entry = StrikeRow(strike=strike)
                by_strike[strike] = entry
            ce = _num(row.get("CE_LTP"))
            if ce is not None:
                entry.ce = OptionLeg(symbol=self.build_symbol(expiry, strike, True), premium=ce)
            pe = _num(row.get("PE_LTP"))
            if pe is not None:
                entry.pe = OptionLeg(symbol=self.build_symbol(expiry, strike, False), premium=pe)

        chain = sorted(by_strike.values(), key=lambda r: r.strike)
        if spot is None or spot <= 0:
            raise McxProxyError("Missing UnderlyingValue in MCX option chain response")
        return chain, spot

from __future__ import annotations

import logging
from typing import Any

import httpx

from mcx_atp.aliceblue_auth import API_BASE, AliceblueSession

logger = logging.getLogger(__name__)


class AliceblueApiError(RuntimeError):
    pass


def _num(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class AliceblueClient:
    """Thin wrapper around Aliceblue's Option Chain + Market Data REST APIs.

    Requires a Developer Portal App session (see aliceblue_auth.perform_login).
    """

    def __init__(self, session: AliceblueSession, base_url: str = API_BASE) -> None:
        self.session = session
        self._client = httpx.Client(base_url=base_url, timeout=30.0)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "AliceblueClient":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.session.user_session}",
            "Content-Type": "application/json",
        }

    def _post(self, path: str, payload: Any) -> Any:
        resp = self._client.post(path, json=payload, headers=self._headers())
        try:
            body = resp.json()
        except ValueError as exc:
            raise AliceblueApiError(
                f"Non-JSON response from {path}: {resp.text[:200]}"
            ) from exc
        if resp.status_code == 401:
            raise AliceblueApiError(
                "Aliceblue session rejected (401). Run `mcx-atp login` again."
            )
        if resp.status_code != 200 or body.get("status") not in ("Ok", None):
            raise AliceblueApiError(f"{path} failed: {body.get('message') or body}")
        return body

    def get_underlying(self, exch: str) -> list[str]:
        body = self._post("obrest/optionChain/getUnderlying", {"exch": exch})
        result = body.get("result") or []
        if not result:
            return []
        return result[0].get("list_underlying") or []

    def get_underlying_expiry(self, underlying: str, exch: str) -> list[str]:
        body = self._post(
            "obrest/optionChain/getUnderlyingExp", {"underlying": underlying, "exch": exch}
        )
        result = body.get("result") or []
        if not result:
            return []
        return result[0].get("underlying_expiry") or []

    def get_option_chain(
        self, underlying: str, expiry: str, exch: str, interval: int
    ) -> list[dict[str, Any]]:
        body = self._post(
            "obrest/optionChain/getOptionChain",
            {"underlying": underlying, "expiry": expiry, "interval": interval, "exch": exch},
        )
        result = body.get("result") or []
        if not result:
            return []
        return result[0].get("data") or []

    def get_market_data(
        self, tokens: list[tuple[str, str]]
    ) -> dict[str, dict[str, float | None]]:
        """tokens: list of (exchange, token). Returns {token: {"ltp":..,"atp":..}}."""
        if not tokens:
            return {}
        payload = [{"exchange": exch, "token": token} for exch, token in tokens]
        body = self._post("open-api/od/ChartAPIService/chart/get/multi/ohlc", payload)
        out: dict[str, dict[str, float | None]] = {}
        rows = body.get("result") or []
        for i, row in enumerate(rows):
            if not isinstance(row, dict):
                exch, token = tokens[i] if i < len(tokens) else ("?", "?")
                logger.warning(
                    "Market data row %d (exchange=%s token=%s) was %r, skipping",
                    i, exch, token, row,
                )
                continue
            tk = str(row.get("tk"))
            out[tk] = {"ltp": _num(row.get("ltp")), "atp": _num(row.get("avg"))}
        return out

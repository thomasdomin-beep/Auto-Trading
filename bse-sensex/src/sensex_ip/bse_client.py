from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from bse import BSE

from sensex_ip.config import DailyLowMode, PremiumField
from sensex_ip.models import OptionLeg, StrikeRow


def parse_bse_number(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip().replace(",", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


class BseSensexClient:
    """BSE India API client (same backend as bseindia.com option chain UI)."""

    def __init__(
        self,
        api_base: str,
        referer: str,
        sensex_scrip_cd: str = "1",
        request_delay: float = 0.12,
    ) -> None:
        self.api_base = api_base.rstrip("/")
        self.referer = referer
        self.sensex_scrip_cd = sensex_scrip_cd
        self.request_delay = request_delay
        self._bse = BSE(download_folder="/tmp/bse_sensex_ip")
        self._session = self._bse.session
        self._session.headers["Referer"] = referer

    def close(self) -> None:
        self._bse.exit()

    def __enter__(self) -> BseSensexClient:
        self.warm_session()
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def warm_session(self) -> None:
        self._session.headers["Referer"] = self.referer
        # Spot header call validates API access without relying on www redirects.
        self._get_json(
            "getScripHeaderData/w",
            {"scripcode": self.sensex_scrip_cd},
        )

    def _get_json(self, path: str, params: dict[str, Any]) -> Any:
        url = f"{self.api_base}/{path.lstrip('/')}"
        r = self._session.get(url, params=params, timeout=30)
        r.raise_for_status()
        text = r.text.strip()
        if not text.startswith("{") and not text.startswith("["):
            raise RuntimeError(
                f"BSE returned non-JSON for {path} (status {r.status_code}): {text[:160]}"
            )
        return r.json()

    def get_spot(self) -> float:
        data = self._get_json(
            "getScripHeaderData/w",
            {"scripcode": self.sensex_scrip_cd},
        )
        ltp = data.get("CurrRate", {}).get("LTP")
        val = parse_bse_number(ltp)
        if val is None:
            raise RuntimeError("Could not parse Sensex spot LTP from BSE header")
        return val

    def nearest_expiry(self) -> str:
        data = self._get_json(
            "ddlExpiry_New/w",
            {"scrip_cd": self.sensex_scrip_cd},
        )
        table = data.get("Table1") or []
        if not table:
            raise RuntimeError("No Sensex option expiries returned by BSE")
        return str(table[0]["ExpiryDate"])

    def get_option_chain(self, expiry: str) -> list[dict[str, Any]]:
        data = self._get_json(
            "DerivOptionChain_IV/w",
            {
                "Expiry": expiry,
                "scrip_cd": self.sensex_scrip_cd,
                "strprice": "",
            },
        )
        table = data.get("Table") or []
        if not table:
            raise RuntimeError(f"Empty option chain for expiry {expiry}")
        return table

    @staticmethod
    def _premium_from_row(row: dict[str, Any], side: str, field: PremiumField) -> float | None:
        if side == "CE":
            ltp = row.get("C_Last_Trd_Price")
            bid = row.get("C_BidPrice")
            ask = row.get("C_OfferPrice")
        else:
            ltp = row.get("Last_Trd_Price")
            bid = row.get("BidPrice")
            ask = row.get("OfferPrice")

        if field == "mid":
            b, a = parse_bse_number(bid), parse_bse_number(ask)
            if b is not None and a is not None:
                return (b + a) / 2.0
            return parse_bse_number(ltp)
        if field == "close":
            return parse_bse_number(row.get("PrevClose"))
        return parse_bse_number(ltp)

    def merge_chain_by_strike(
        self, rows: list[dict[str, Any]], premium_field: PremiumField
    ) -> list[StrikeRow]:
        merged: dict[float, StrikeRow] = {}
        for row in rows:
            strike = parse_bse_number(row.get("Strike_Price"))
            if strike is None:
                continue
            ce_code = row.get("C_Series_Code") or ""
            pe_code = (
                row.get("Series_Code")
                or row.get("P_Series_Code")
                or row.get("PE_Series_Code")
                or ""
            )
            ce_id = str(row.get("C_Series_Id") or "")
            pe_id = str(row.get("Series_Id") or "")
            ce_p = self._premium_from_row(row, "CE", premium_field)
            pe_p = self._premium_from_row(row, "PE", premium_field)
            entry = merged.get(strike)
            if entry is None:
                entry = StrikeRow(strike=strike)
                merged[strike] = entry
            if ce_p is not None and ce_id:
                entry.ce = OptionLeg(symbol=ce_code or ce_id, scrip_id=ce_id, premium=ce_p)
            if pe_p is not None and pe_id:
                sym = pe_code if pe_code else f"PE-{int(strike)}"
                entry.pe = OptionLeg(symbol=sym, scrip_id=pe_id, premium=pe_p)
        return sorted(merged.values(), key=lambda r: r.strike)

    def _daily_low_from_chart(
        self, scrip_id: str, mode: DailyLowMode
    ) -> float | None:
        """Session low from BSE StockReachGraph (option quote chart on bseindia.com)."""
        now = datetime.now(timezone.utc)
        # BSE chart API uses DD/MM/YYYY in IST-aligned session dates.
        today = now.strftime("%d/%m/%Y")
        if mode == "last_closed":
            from_dt = (now - timedelta(days=10)).strftime("%d/%m/%Y")
            to_dt = (now - timedelta(days=1)).strftime("%d/%m/%Y")
        else:
            from_dt = today
            to_dt = today

        option_ref = (
            f"https://www.bseindia.com/stock-share-price/future-options/derivatives/"
            f"{self.sensex_scrip_cd}/{scrip_id}/"
        )
        prev_ref = self._session.headers.get("Referer")
        self._session.headers["Referer"] = option_ref
        try:
            graph = self._get_json(
                "StockReachGraph/w",
                {
                    "scripcode": scrip_id,
                    "flag": "0",
                    "fromdate": from_dt,
                    "todate": to_dt,
                    "seriesid": "",
                },
            )
        finally:
            if prev_ref:
                self._session.headers["Referer"] = prev_ref

        low_val = parse_bse_number(graph.get("LowVal"))
        raw = graph.get("Data") or "[]"
        points = json.loads(raw) if isinstance(raw, str) else raw
        lows: list[float] = []
        if low_val is not None:
            lows.append(low_val)
        if isinstance(points, list):
            for pt in points:
                if not isinstance(pt, dict):
                    continue
                for key in ("low", "Low", "l", "close", "Close"):
                    v = parse_bse_number(pt.get(key))
                    if v is not None:
                        lows.append(v)
        if not lows:
            return None
        return min(lows)

    def fetch_daily_low(
        self,
        scrip_id: str,
        mode: DailyLowMode,
    ) -> float | None:
        time.sleep(self.request_delay)
        return self._daily_low_from_chart(scrip_id, mode)

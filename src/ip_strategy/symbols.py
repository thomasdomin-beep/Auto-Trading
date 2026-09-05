from __future__ import annotations

import re
from datetime import datetime

SYMBOL_RE = re.compile(
    r"^(?P<side>[CP])-(?P<underlying>[A-Z]+)-(?P<strike>\d+(?:\.\d+)?)-(?P<expiry>\d{6})$"
)


def parse_option_symbol(symbol: str) -> dict[str, str | float] | None:
    m = SYMBOL_RE.match(symbol)
    if not m:
        return None
    return {
        "side": m.group("side"),
        "underlying": m.group("underlying"),
        "strike": float(m.group("strike")),
        "expiry": m.group("expiry"),
    }


def expiry_dd_mm_yyyy_from_symbol(symbol: str) -> str | None:
    parsed = parse_option_symbol(symbol)
    if not parsed:
        return None
    dd, mm, yy = parsed["expiry"][:2], parsed["expiry"][2:4], parsed["expiry"][4:6]
    return f"{dd}-{mm}-20{yy}"


def product_expiry_to_api(expiry_iso: str) -> str:
    """Convert product settlement_time or date to DD-MM-YYYY for tickers API."""
    if "T" in expiry_iso:
        dt = datetime.fromisoformat(expiry_iso.replace("Z", "+00:00"))
    else:
        dt = datetime.strptime(expiry_iso[:10], "%Y-%m-%d")
    return dt.strftime("%d-%m-%Y")

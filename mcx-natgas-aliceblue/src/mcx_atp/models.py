from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field, computed_field

IST = ZoneInfo("Asia/Kolkata")


def format_computed_at_ist(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(IST).strftime("%d %b %Y, %H:%M:%S IST")


class Leg(BaseModel):
    """One CE or PE contract at a given strike."""

    token: str
    symbol: str
    ltp: float | None = None
    atp: float | None = None

    @computed_field
    @property
    def atp_minus_ltp(self) -> float | None:
        if self.atp is None or self.ltp is None:
            return None
        return self.atp - self.ltp


class StrikeRow(BaseModel):
    strike: float
    ce: Leg | None = None
    pe: Leg | None = None


class ChainSnapshot(BaseModel):
    """Latest ITM/ATM CE & PE legs, ready for the dashboard."""

    success: bool = True
    error: str | None = None
    computed_at: datetime
    underlying: str | None = None
    expiry_date: str | None = None

    atm_strike: float | None = None
    ce_itm_strike: float | None = None
    pe_itm_strike: float | None = None

    ce_atm: Leg | None = None
    ce_itm: Leg | None = None
    pe_atm: Leg | None = None
    pe_itm: Leg | None = None

    # Carried over from the Delta ETH order-flow feature: same "ITM's
    # (ATP-LTP) below ATM's" rule, kept as a bonus signal alongside the
    # requested LTP / ATP-LTP table.
    buy_ce: bool = False
    buy_pe: bool = False
    messages: list[str] = Field(default_factory=list)

    @computed_field
    @property
    def computed_at_ist(self) -> str:
        return format_computed_at_ist(self.computed_at)

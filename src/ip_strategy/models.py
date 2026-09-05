from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field, computed_field

IST = ZoneInfo("Asia/Kolkata")


def format_computed_at_ist(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(IST).strftime("%d %b %Y, %H:%M:%S IST")


class OptionLeg(BaseModel):
    symbol: str
    premium: float


class StrikeRow(BaseModel):
    strike: float
    ce: OptionLeg | None = None
    pe: OptionLeg | None = None

    def ce_premium(self) -> float | None:
        return self.ce.premium if self.ce else None

    def pe_premium(self) -> float | None:
        return self.pe.premium if self.pe else None


class OrderFlowLeg(BaseModel):
    symbol: str
    atp: float | None = None
    ltp: float | None = None

    @computed_field
    @property
    def atp_minus_ltp(self) -> float | None:
        if self.atp is None or self.ltp is None:
            return None
        return self.atp - self.ltp


class OrderFlowStrikeRow(BaseModel):
    strike: float
    ce: OrderFlowLeg | None = None
    pe: OrderFlowLeg | None = None


class OrderFlowSignal(BaseModel):
    success: bool = True
    error: str | None = None
    computed_at: datetime
    expiry_date: str | None = None
    spot: float | None = None
    atm_strike: float | None = None
    ce_itm_strike: float | None = None
    pe_itm_strike: float | None = None
    ce_atm: OrderFlowLeg | None = None
    ce_itm: OrderFlowLeg | None = None
    pe_atm: OrderFlowLeg | None = None
    pe_itm: OrderFlowLeg | None = None
    buy_ce: bool = False
    buy_pe: bool = False
    messages: list[str] = Field(default_factory=list)

    @computed_field
    @property
    def computed_at_ist(self) -> str:
        return format_computed_at_ist(self.computed_at)


class CrossoverPair(BaseModel):
    strike_a: float
    strike_b: float
    symbol_ce_a: str
    symbol_pe_a: str
    symbol_ce_b: str
    symbol_pe_b: str


class StrategyLevels(BaseModel):
    success: bool = True
    error: str | None = None
    computed_at: datetime
    expiry_date: str | None = None
    spot: float | None = None
    strike_a: float | None = None
    strike_b: float | None = None
    ideal_premium: float | None = None
    lhs: float | None = None
    rhs: float | None = None
    premium_field: str = "mark_price"
    daily_lows: dict[str, float] = Field(default_factory=dict)
    meta: dict[str, Any] = Field(default_factory=dict)

    @computed_field
    @property
    def computed_at_ist(self) -> str:
        return format_computed_at_ist(self.computed_at)

    def to_pine_inputs(self) -> dict[str, float | None]:
        return {
            "lhs": self.lhs,
            "rhs": self.rhs,
            "ideal_premium": self.ideal_premium,
            "strike_a": self.strike_a,
            "strike_b": self.strike_b,
        }


class TargetOrder(BaseModel):
    """One of the ETHUSD entry orders (4-rung ladder per account) the
    auto-trader wants resting.

    `slot` is a stable identifier (e.g. "main_1") used to tag orders (via
    client_order_id) so the trader can recognise its own resting orders on
    later cycles for cancel/replace when levels move.
    """

    slot: str
    account: str  # "main" or "scalper"
    side: str  # "buy" or "sell"
    price: float
    take_profit_price: float

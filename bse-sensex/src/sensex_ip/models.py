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
    scrip_id: str
    premium: float


class StrikeRow(BaseModel):
    strike: float
    ce: OptionLeg | None = None
    pe: OptionLeg | None = None

    def ce_premium(self) -> float | None:
        return self.ce.premium if self.ce else None

    def pe_premium(self) -> float | None:
        return self.pe.premium if self.pe else None


class CrossoverPair(BaseModel):
    strike_a: float
    strike_b: float
    symbol_ce_a: str
    symbol_pe_a: str
    symbol_ce_b: str
    symbol_pe_b: str
    scrip_ce_a: str
    scrip_pe_a: str
    scrip_ce_b: str
    scrip_pe_b: str


class StrategyLevels(BaseModel):
    success: bool = True
    error: str | None = None
    computed_at: datetime
    expiry_date: str | None = None
    spot: float | None = None
    strike_a: float | None = None
    strike_b: float | None = None
    ideal_premium: float | None = None
    support: float | None = None
    resistance: float | None = None
    premium_field: str = "ltp"
    daily_lows: dict[str, float] = Field(default_factory=dict)
    meta: dict[str, Any] = Field(default_factory=dict)

    @computed_field
    @property
    def computed_at_ist(self) -> str:
        return format_computed_at_ist(self.computed_at)

    def to_pine_inputs(self) -> dict[str, float | None]:
        return {
            "support": self.support,
            "resistance": self.resistance,
            "ideal_premium": self.ideal_premium,
            "strike_a": self.strike_a,
            "strike_b": self.strike_b,
        }

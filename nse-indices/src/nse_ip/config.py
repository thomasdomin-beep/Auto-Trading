from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PremiumField = Literal["ltp", "mid"]
DailyLowMode = Literal["current_session", "last_closed"]
Underlying = Literal["NIFTY", "BANKNIFTY"]

TV_SYMBOLS = {"NIFTY": "NSE:NIFTY", "BANKNIFTY": "NSE:BANKNIFTY"}


class AppConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="NSE_IP_", extra="ignore")

    interval_minutes: int = 5
    underlying: Underlying = "NIFTY"
    premium_field: PremiumField = "ltp"
    daily_low_mode: DailyLowMode = "current_session"
    daily_low_use_premium_fallback: bool = True
    nse_base_url: str = "https://www.nseindia.com"
    output_dir: str = "output"
    preserve_levels_on_failure: bool = True
    chart_request_delay_seconds: float = 0.2
    bridge_host: str = "127.0.0.1"
    bridge_port: int = 8767
    auto_clipboard: bool = False

    config_path: Path | None = Field(default=None, exclude=True)

    @field_validator("underlying", mode="before")
    @classmethod
    def upper_underlying(cls, v: object) -> object:
        if isinstance(v, str):
            return v.strip().upper()
        return v

    @classmethod
    def load(cls, config_path: Path | None = None) -> AppConfig:
        path = config_path or Path("config.nifty.yaml")
        data: dict = {}
        if path.is_file():
            with path.open() as f:
                data = yaml.safe_load(f) or {}
        cfg = cls(**data)
        cfg.config_path = path if path.is_file() else None
        return cfg

    @property
    def output_path(self) -> Path:
        return Path(self.output_dir)

    @property
    def tradingview_symbol(self) -> str:
        return TV_SYMBOLS[self.underlying]

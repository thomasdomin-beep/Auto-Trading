from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


PremiumField = Literal["mark_price", "close", "mid"]
DailyLowMode = Literal["current_session", "last_closed"]


class AppConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="IP_STRATEGY_", extra="ignore")

    interval_minutes: int = 5
    underlying: str = "ETH"
    perp_symbol: str = "ETHUSD"
    expiry_date: str | None = None  # DD-MM-YYYY; None = nearest live expiry
    premium_field: PremiumField = "mark_price"
    daily_low_mode: DailyLowMode = "current_session"
    delta_base_url: str = "https://api.india.delta.exchange"
    output_dir: str = "output"
    preserve_levels_on_failure: bool = True
    candle_request_delay_seconds: float = 0.15
    bridge_host: str = "127.0.0.1"
    bridge_port: int = 8765
    auto_clipboard: bool = False
    order_flow_enabled: bool = True
    order_flow_poll_seconds: float = 3.0

    config_path: Path | None = Field(default=None, exclude=True)

    @classmethod
    def load(cls, config_path: Path | None = None) -> AppConfig:
        path = config_path or Path("config.yaml")
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

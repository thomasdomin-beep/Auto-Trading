from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PremiumField = Literal["ltp", "mid", "close"]
DailyLowMode = Literal["current_session", "last_closed"]


class AppConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SENSEX_IP_", extra="ignore")

    interval_minutes: int = 5
    sensex_scrip_cd: str = "1"
    premium_field: PremiumField = "ltp"
    daily_low_mode: DailyLowMode = "current_session"
    daily_low_use_premium_fallback: bool = True
    bse_api_base: str = "https://api.bseindia.com/BseIndiaAPI/api"
    bse_referer: str = (
        "https://www.bseindia.com/stock-share-price/future-options/derivatives/1/"
    )
    output_dir: str = "output"
    preserve_levels_on_failure: bool = True
    header_request_delay_seconds: float = 0.12
    bridge_host: str = "127.0.0.1"
    bridge_port: int = 8766
    auto_clipboard: bool = False
    tradingview_symbol: str = "BSE:SENSEX"

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

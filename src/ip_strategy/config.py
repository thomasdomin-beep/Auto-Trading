from __future__ import annotations

import os
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

    # Auto-trading (ETHUSD futures). Off by default; must be explicitly
    # enabled since this places real live orders with real capital.
    trading_enabled: bool = False
    trading_leverage: int = 25
    trading_capital_fraction: float = 0.25
    # $ offsets for the 4-rung entry ladder: support-offset[i] (buy) /
    # resistance+offset[i] (sell), in order (1st..4th order).
    trading_entry_offsets: list[float] = [2.0, 8.0, 18.0, 28.0]
    # $ offset used for every order's take-profit: resistance-offset (buy) /
    # support+offset (sell), recomputed fresh from current levels each cycle.
    trading_tp_offset: float = 2.0
    trading_poll_minutes: int = 5

    # Credentials are secrets: only ever set via environment variables
    # (IP_STRATEGY_DELTA_*_API_KEY/SECRET), never via config.yaml.
    delta_main_api_key: str | None = None
    delta_main_api_secret: str | None = None
    delta_scalper_api_key: str | None = None
    delta_scalper_api_secret: str | None = None

    config_path: Path | None = Field(default=None, exclude=True)

    @classmethod
    def load(cls, config_path: Path | None = None) -> AppConfig:
        path = config_path or Path("config.yaml")
        data: dict = {}
        if path.is_file():
            with path.open() as f:
                data = yaml.safe_load(f) or {}
        # pydantic-settings gives init kwargs top priority over env vars, so
        # passing every YAML key straight through as **data would let
        # config.yaml silently shadow environment variables (e.g. Render's
        # $PORT-derived IP_STRATEGY_BRIDGE_PORT). Drop any YAML key that has
        # a corresponding env var set, so env vars win as expected.
        prefix = cls.model_config.get("env_prefix", "")
        data = {
            key: value
            for key, value in data.items()
            if f"{prefix}{key}".upper() not in os.environ
        }
        cfg = cls(**data)
        cfg.config_path = path if path.is_file() else None
        return cfg

    @property
    def output_path(self) -> Path:
        return Path(self.output_dir)

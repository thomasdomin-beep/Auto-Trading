from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PremiumField = Literal["ltp"]
Instrument = Literal["optfut", "optidx"]


class AppConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MCX_IP_", extra="ignore")

    interval_minutes: int = 5
    underlying: str = "NATURALGAS"
    instrument: Instrument = "optfut"
    premium_field: PremiumField = "ltp"
    mcx_proxy_base_url: str = "http://127.0.0.1:3001"
    output_dir: str = "output"
    preserve_levels_on_failure: bool = True
    bridge_host: str = "127.0.0.1"
    bridge_port: int = 8769
    auto_clipboard: bool = False

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

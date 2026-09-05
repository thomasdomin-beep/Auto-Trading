from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppConfig(BaseSettings):
    """Config for the MCX Natural Gas Aliceblue ATP dashboard.

    `app_code` / `api_secret` are only ever read from environment variables
    (MCX_ATP_APP_CODE / MCX_ATP_API_SECRET) or a local .env file, never from
    config.yaml, so they can't accidentally end up committed to git.
    """

    model_config = SettingsConfigDict(env_prefix="MCX_ATP_", extra="ignore", env_file=".env")

    underlying: str = "NATURALGAS"
    exch: str = "mcx_fo"
    strike_interval: int = 10
    poll_seconds: float = 5.0

    bridge_host: str = "127.0.0.1"
    bridge_port: int = 8770

    session_path: str = ".aliceblue_session.json"
    output_dir: str = "output"

    redirect_host: str = "127.0.0.1"
    redirect_port: int = 8771

    # Secrets: env / .env only (see model_config above).
    app_code: SecretStr | None = None
    api_secret: SecretStr | None = None

    config_path: Path | None = Field(default=None, exclude=True)

    @classmethod
    def load(cls, config_path: Path | None = None) -> "AppConfig":
        path = config_path or Path("config.yaml")
        data: dict = {}
        if path.is_file():
            with path.open() as f:
                data = yaml.safe_load(f) or {}
        # Never allow secrets to come from config.yaml.
        data.pop("app_code", None)
        data.pop("api_secret", None)
        cfg = cls(**data)
        cfg.config_path = path if path.is_file() else None
        return cfg

    @property
    def output_path(self) -> Path:
        return Path(self.output_dir)

    @property
    def session_file(self) -> Path:
        return Path(self.session_path)

    @property
    def exch_market_data(self) -> str:
        """Map the Option Chain `exch` code (e.g. mcx_fo) to the exchange code
        expected by the Market Data endpoint (e.g. MCX)."""
        return {
            "nse_fo": "NFO",
            "bse_fo": "BFO",
            "mcx_fo": "MCX",
        }.get(self.exch, self.exch.upper())

from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path

import pyperclip

from ip_strategy.config import AppConfig
from ip_strategy.delta_client import DeltaClient
from ip_strategy.history import append_levels_history
from ip_strategy.ip_strategy import (
    compute_ip,
    compute_lhs_rhs,
    find_crossover_strikes,
)
from ip_strategy.models import StrategyLevels

logger = logging.getLogger(__name__)

# Sentinel distinguishing "no override given" (fall back to cfg.expiry_date / RunState)
# from an explicit `None` override (force nearest live expiry).
_UNSET: object = object()


class RunState:
    """Thread-safe holder for the currently selected expiry.

    Shared between the scheduler job and the bridge UI (same process) so that
    picking an expiry in the dashboard also applies to subsequent scheduled runs.
    """

    def __init__(self, initial_expiry: str | None = None) -> None:
        self._expiry = initial_expiry
        self._lock = threading.Lock()

    def get_expiry(self) -> str | None:
        with self._lock:
            return self._expiry

    def set_expiry(self, expiry: str | None) -> None:
        with self._lock:
            self._expiry = expiry


def run_strategy(cfg: AppConfig, expiry_override: str | None | object = _UNSET) -> StrategyLevels:
    """Compute strategy levels.

    expiry_override (DD-MM-YYYY) takes precedence over `cfg.expiry_date` when given.
    Passing expiry_override=None explicitly forces the nearest live expiry, ignoring
    `cfg.expiry_date`. Omitting it falls back to `cfg.expiry_date`, or the nearest
    live expiry if that isn't set either.
    """
    now = datetime.now(timezone.utc)
    requested_expiry = cfg.expiry_date if expiry_override is _UNSET else expiry_override
    with DeltaClient(cfg.delta_base_url, cfg.candle_request_delay_seconds) as client:
        if requested_expiry:
            live_expiries = client.list_live_expiries(cfg.underlying)
            if requested_expiry not in live_expiries:
                return StrategyLevels(
                    success=False,
                    error=(
                        f"Requested expiry {requested_expiry} is not a live "
                        f"{cfg.underlying} option expiry. Available: "
                        f"{', '.join(live_expiries) or 'none'}"
                    ),
                    computed_at=now,
                    premium_field=cfg.premium_field,
                )
            expiry = requested_expiry
        else:
            expiry = client.nearest_expiry_date(cfg.underlying)
        if not expiry:
            return StrategyLevels(
                success=False,
                error="No live ETH option expiry found",
                computed_at=now,
                premium_field=cfg.premium_field,
            )

        perp = client.get_ticker(cfg.perp_symbol)
        spot_raw = perp.get("spot_price") or perp.get("mark_price")
        if spot_raw is None:
            return StrategyLevels(
                success=False,
                error=f"Could not read spot from {cfg.perp_symbol}",
                computed_at=now,
                expiry_date=expiry,
                premium_field=cfg.premium_field,
            )
        spot = float(spot_raw)

        tickers = client.get_option_chain_tickers(cfg.underlying, expiry)
        chain = client.merge_chain_by_strike(tickers, cfg.premium_field)
        if len(chain) < 2:
            return StrategyLevels(
                success=False,
                error="Option chain too small",
                computed_at=now,
                expiry_date=expiry,
                spot=spot,
                premium_field=cfg.premium_field,
            )

        pair = find_crossover_strikes(chain, spot)
        if pair is None:
            return StrategyLevels(
                success=False,
                error="No CE/PE premium crossover pair (A,B) found",
                computed_at=now,
                expiry_date=expiry,
                spot=spot,
                premium_field=cfg.premium_field,
            )

        symbols = [
            pair.symbol_ce_a,
            pair.symbol_pe_a,
            pair.symbol_ce_b,
            pair.symbol_pe_b,
        ]
        daily_lows: dict[str, float] = {}
        for sym in symbols:
            low = client.fetch_daily_low(sym, cfg.daily_low_mode)
            if low is None:
                return StrategyLevels(
                    success=False,
                    error=f"Missing daily low for {sym}",
                    computed_at=now,
                    expiry_date=expiry,
                    spot=spot,
                    strike_a=pair.strike_a,
                    strike_b=pair.strike_b,
                    premium_field=cfg.premium_field,
                    daily_lows=daily_lows,
                )
            daily_lows[sym] = low

        ip = compute_ip(daily_lows)
        lhs, rhs = compute_lhs_rhs(chain, spot, ip)

        return StrategyLevels(
            success=True,
            computed_at=now,
            expiry_date=expiry,
            spot=spot,
            strike_a=pair.strike_a,
            strike_b=pair.strike_b,
            ideal_premium=ip,
            lhs=lhs,
            rhs=rhs,
            premium_field=cfg.premium_field,
            daily_lows=daily_lows,
            meta={"perp_symbol": cfg.perp_symbol},
        )


def write_levels(cfg: AppConfig, levels: StrategyLevels) -> Path:
    out_dir = cfg.output_path
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "levels.json"
    levels_path = path

    if not levels.success and cfg.preserve_levels_on_failure and path.is_file():
        logger.warning("Run failed (%s); preserving previous levels.json", levels.error)
        failure_path = out_dir / "last_failure.json"
        failure_path.write_text(
            levels.model_dump_json(indent=2),
            encoding="utf-8",
        )
        return path

    path.write_text(levels.model_dump_json(indent=2), encoding="utf-8")
    return levels_path


def maybe_clipboard(cfg: AppConfig, levels: StrategyLevels) -> None:
    if not cfg.auto_clipboard or not levels.success:
        return
    if levels.lhs is None or levels.rhs is None:
        return
    text = f"{levels.lhs}\n{levels.rhs}"
    try:
        pyperclip.copy(text)
        logger.info("Copied LHS/RHS to clipboard")
    except pyperclip.PyperclipException as e:
        logger.warning("Clipboard copy failed: %s", e)


def execute_run(
    cfg: AppConfig,
    expiry_override: str | None | object = _UNSET,
    state: RunState | None = None,
    persist: bool = True,
) -> StrategyLevels:
    # If no explicit override was passed (e.g. a scheduled run), fall back to the
    # shared RunState so a dashboard expiry selection persists across runs.
    if expiry_override is _UNSET and state is not None:
        expiry_override = state.get_expiry()
    try:
        levels = run_strategy(cfg, expiry_override)
    except Exception as e:
        logger.exception("IP strategy run crashed: %s", e)
        levels = StrategyLevels(
            success=False,
            error=str(e),
            computed_at=datetime.now(timezone.utc),
            premium_field=cfg.premium_field,
        )
    if levels.success:
        logger.info(
            "IP strategy OK expiry=%s spot=%s A=%s B=%s IP=%s lhs=%s rhs=%s",
            levels.expiry_date,
            levels.spot,
            levels.strike_a,
            levels.strike_b,
            levels.ideal_premium,
            levels.lhs,
            levels.rhs,
        )
    else:
        logger.error("IP strategy failed: %s", levels.error)
    if persist:
        write_levels(cfg, levels)
        if levels.success:
            append_levels_history(cfg.output_path, levels)
        maybe_clipboard(cfg, levels)
    return levels

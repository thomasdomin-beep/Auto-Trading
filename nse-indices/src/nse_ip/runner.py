from __future__ import annotations

import logging
from datetime import datetime, timezone

from nse_ip.config import AppConfig
from nse_ip.ip_strategy import (
    compute_ip,
    compute_support_resistance,
    find_crossover_strikes,
)
from nse_ip.history import append_levels_history
from nse_ip.models import StrategyLevels
from nse_ip.nse_client import NseIndexClient
from nse_ip.runner_io import maybe_clipboard, write_levels

logger = logging.getLogger(__name__)


def run_strategy(cfg: AppConfig) -> StrategyLevels:
    now = datetime.now(timezone.utc)
    try:
        with NseIndexClient(
            cfg.nse_base_url,
            cfg.underlying,
            cfg.chart_request_delay_seconds,
        ) as client:
            expiry = client.nearest_expiry()
            payload = client.fetch_option_chain(expiry)
            chain, spot = client.merge_chain_by_strike(
                payload, expiry, cfg.premium_field
            )
            if len(chain) < 2:
                return StrategyLevels(
                    success=False,
                    error="Option chain too small",
                    computed_at=now,
                    underlying=cfg.underlying,
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
                    underlying=cfg.underlying,
                    expiry_date=expiry,
                    spot=spot,
                    premium_field=cfg.premium_field,
                )

            ce_a_row = next(r for r in chain if r.strike == pair.strike_a)
            ce_b_row = next(r for r in chain if r.strike == pair.strike_b)
            if not (ce_a_row.ce and ce_a_row.pe and ce_b_row.ce and ce_b_row.pe):
                return StrategyLevels(
                    success=False,
                    error="Missing CE/PE legs on crossover strikes",
                    computed_at=now,
                    underlying=cfg.underlying,
                    expiry_date=expiry,
                    spot=spot,
                    premium_field=cfg.premium_field,
                )

            specs = [
                (pair.symbol_ce_a, pair.id_ce_a, ce_a_row.ce.premium),
                (pair.symbol_pe_a, pair.id_pe_a, ce_a_row.pe.premium),
                (pair.symbol_ce_b, pair.id_ce_b, ce_b_row.ce.premium),
                (pair.symbol_pe_b, pair.id_pe_b, ce_b_row.pe.premium),
            ]
            daily_lows: dict[str, float] = {}
            used_fallback = False
            for label, ident, premium in specs:
                low = client.fetch_daily_low(ident, cfg.daily_low_mode)
                if low is None:
                    if not cfg.daily_low_use_premium_fallback:
                        return StrategyLevels(
                            success=False,
                            error=f"Missing daily low for {label}",
                            computed_at=now,
                            underlying=cfg.underlying,
                            expiry_date=expiry,
                            spot=spot,
                            strike_a=pair.strike_a,
                            strike_b=pair.strike_b,
                            premium_field=cfg.premium_field,
                            daily_lows=daily_lows,
                        )
                    low = premium
                    used_fallback = True
                daily_lows[label] = low

            ip = compute_ip(daily_lows)
            support, resistance = compute_support_resistance(chain, spot, ip)

            return StrategyLevels(
                success=True,
                computed_at=now,
                underlying=cfg.underlying,
                expiry_date=expiry,
                spot=spot,
                strike_a=pair.strike_a,
                strike_b=pair.strike_b,
                ideal_premium=ip,
                support=support,
                resistance=resistance,
                premium_field=cfg.premium_field,
                daily_lows=daily_lows,
                meta={
                    "tradingview_symbol": cfg.tradingview_symbol,
                    "daily_low_premium_fallback_used": used_fallback,
                    "data_source": "nseindia.com",
                },
            )
    except Exception as exc:
        return StrategyLevels(
            success=False,
            error=str(exc),
            computed_at=now,
            underlying=cfg.underlying,
            premium_field=cfg.premium_field,
        )


def execute_run(cfg: AppConfig) -> StrategyLevels:
    levels = run_strategy(cfg)
    if levels.success:
        logger.info(
            "%s IP OK expiry=%s spot=%s A=%s B=%s IP=%s support=%s resistance=%s",
            cfg.underlying,
            levels.expiry_date,
            levels.spot,
            levels.strike_a,
            levels.strike_b,
            levels.ideal_premium,
            levels.support,
            levels.resistance,
        )
    else:
        logger.error("%s IP failed: %s", cfg.underlying, levels.error)
    write_levels(cfg, levels)
    if levels.success:
        append_levels_history(cfg.output_path, levels)
    maybe_clipboard(cfg, levels)
    return levels

from __future__ import annotations

import logging
from datetime import datetime, timezone

from mcx_ip.config import AppConfig
from mcx_ip.history import append_levels_history
from mcx_ip.ip_strategy import compute_ip, compute_lhs_rhs, find_crossover_strikes
from mcx_ip.mcx_client import McxClient, McxProxyError
from mcx_ip.models import StrategyLevels
from mcx_ip.runner_io import maybe_clipboard, write_levels

logger = logging.getLogger(__name__)


def run_strategy(cfg: AppConfig) -> StrategyLevels:
    now = datetime.now(timezone.utc)
    try:
        with McxClient(cfg.mcx_proxy_base_url, cfg.instrument, cfg.underlying) as client:
            expiry = client.nearest_expiry()
            if not expiry:
                return StrategyLevels(
                    success=False,
                    error=f"No live {cfg.underlying} option expiry found",
                    computed_at=now,
                    underlying=cfg.underlying,
                    premium_field=cfg.premium_field,
                )

            payload = client.fetch_option_chain(expiry)
            chain, spot = client.merge_chain_by_strike(payload, expiry)
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

            a_row = next(r for r in chain if r.strike == pair.strike_a)
            b_row = next(r for r in chain if r.strike == pair.strike_b)
            if not (a_row.ce and a_row.pe and b_row.ce and b_row.pe):
                return StrategyLevels(
                    success=False,
                    error="Missing CE/PE legs on crossover strikes",
                    computed_at=now,
                    underlying=cfg.underlying,
                    expiry_date=expiry,
                    spot=spot,
                    strike_a=pair.strike_a,
                    strike_b=pair.strike_b,
                    premium_field=cfg.premium_field,
                )

            # MCX has no daily-low/historical API for option premiums (unlike
            # Delta/NSE/BSE), so IP is the average of the four crossover-pair
            # legs' *current* LTP instead of a daily low.
            premiums = {
                pair.symbol_ce_a: a_row.ce.premium,
                pair.symbol_pe_a: a_row.pe.premium,
                pair.symbol_ce_b: b_row.ce.premium,
                pair.symbol_pe_b: b_row.pe.premium,
            }
            ip = compute_ip(premiums)
            lhs, rhs = compute_lhs_rhs(chain, spot, ip)

            return StrategyLevels(
                success=True,
                computed_at=now,
                underlying=cfg.underlying,
                expiry_date=expiry,
                spot=spot,
                strike_a=pair.strike_a,
                strike_b=pair.strike_b,
                ideal_premium=ip,
                lhs=lhs,
                rhs=rhs,
                premium_field=cfg.premium_field,
                premiums=premiums,
                meta={
                    "instrument": cfg.instrument,
                    "data_source": "mcxindia.com (via local mcx-proxy)",
                    "ip_source": "current_ltp",
                },
            )
    except McxProxyError as exc:
        return StrategyLevels(
            success=False,
            error=str(exc),
            computed_at=now,
            underlying=cfg.underlying,
            premium_field=cfg.premium_field,
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
            "%s IP OK expiry=%s spot=%s A=%s B=%s IP=%s lhs=%s rhs=%s",
            cfg.underlying,
            levels.expiry_date,
            levels.spot,
            levels.strike_a,
            levels.strike_b,
            levels.ideal_premium,
            levels.lhs,
            levels.rhs,
        )
    else:
        logger.error("%s IP failed: %s", cfg.underlying, levels.error)
    write_levels(cfg, levels)
    if levels.success:
        append_levels_history(cfg.output_path, levels)
    maybe_clipboard(cfg, levels)
    return levels

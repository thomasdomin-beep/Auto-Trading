from __future__ import annotations

import logging
import math
import time

from ip_strategy.config import AppConfig
from ip_strategy.delta_trading_client import DeltaTradingClient
from ip_strategy.models import StrategyLevels, TargetOrder

logger = logging.getLogger(__name__)

CLIENT_ORDER_ID_PREFIX = "ipbot"


def compute_target_orders(levels: StrategyLevels, cfg: AppConfig) -> list[TargetOrder]:
    """Translate LHS/RHS into the 8 resting ETHUSD entry orders (4-rung ladder
    per account).

    Support = min(LHS, RHS); Resistance = max(LHS, RHS). `cfg.trading_entry_offsets`
    (default [2, 8, 18, 28]) gives the $ offset for the 1st..4th order on each
    account: main (buy) entries rest at support - offset[i]; scalper (sell)
    entries rest at resistance + offset[i]. Every order's take-profit is
    `cfg.trading_tp_offset` (default 2) away from the *current* resistance/
    support - resistance - trading_tp_offset for buys, support + trading_tp_offset
    for sells - recomputed fresh from the latest levels each cycle (not fixed
    at the price the order was first placed).
    """
    if levels.lhs is None or levels.rhs is None:
        return []

    support = min(levels.lhs, levels.rhs)
    resistance = max(levels.lhs, levels.rhs)
    tp_offset = cfg.trading_tp_offset
    buy_tp = resistance - tp_offset
    sell_tp = support + tp_offset

    targets: list[TargetOrder] = []
    for i, offset in enumerate(cfg.trading_entry_offsets, start=1):
        targets.append(
            TargetOrder(
                slot=f"main_{i}",
                account="main",
                side="buy",
                price=support - offset,
                take_profit_price=buy_tp,
            )
        )
    for i, offset in enumerate(cfg.trading_entry_offsets, start=1):
        targets.append(
            TargetOrder(
                slot=f"scalper_{i}",
                account="scalper",
                side="sell",
                price=resistance + offset,
                take_profit_price=sell_tp,
            )
        )
    return targets


def round_to_tick(price: float, tick_size: float) -> float:
    if tick_size <= 0:
        return price
    steps = round(price / tick_size)
    return round(steps * tick_size, 8)


def _decimals_for_tick(tick_size: float) -> int:
    if tick_size <= 0:
        return 2
    text = f"{tick_size:.10f}".rstrip("0")
    return len(text.split(".")[1]) if "." in text else 0


def format_price(price: float, tick_size: float) -> str:
    return f"{price:.{_decimals_for_tick(tick_size)}f}"


def compute_quantity(
    balance: float,
    capital_fraction: float,
    leverage: int,
    price: float,
    contract_value: float,
) -> int:
    """Contracts affordable with `capital_fraction` of `balance` at `leverage`.

    Floors to a whole number of contracts (Delta orders are sized in
    integer contracts, not dollars).
    """
    if price <= 0 or contract_value <= 0:
        return 0
    notional = balance * capital_fraction * leverage
    return math.floor(notional / (price * contract_value))


def required_margin(price: float, size: int, contract_value: float, leverage: int) -> float:
    if leverage <= 0:
        return float("inf")
    return (price * size * contract_value) / leverage


def run_trading_cycle(
    cfg: AppConfig,
    levels: StrategyLevels,
    main_client: DeltaTradingClient,
    scalper_client: DeltaTradingClient,
) -> None:
    """One pass of the auto-trader: reconcile the 8 resting entry orders.

    For each of the 8 slots (main_1..main_4 / scalper_1..scalper_4):
    - Cancel any of our resting orders in that slot whose price no longer
      matches the current target (levels moved).
    - Place one more entry order at the current target price, sized at
      `trading_capital_fraction` (default 25%) of the account's live
      available balance, as long as the account has enough available
      margin left (this is what naturally pyramids new entries every cycle
      and stops once capital is fully deployed).
    - Filled positions (and their attached take-profit) are never touched;
      only still-open/pending entry orders are managed.
    """
    if not cfg.trading_enabled:
        logger.info("Trading disabled (trading_enabled=false); skipping cycle")
        return
    if not levels.success or levels.lhs is None or levels.rhs is None:
        logger.warning("Skipping trading cycle: no valid LHS/RHS levels")
        return

    targets = compute_target_orders(levels, cfg)
    clients = {"main": main_client, "scalper": scalper_client}

    product = main_client.get_product(cfg.perp_symbol)
    product_id = int(product["id"])
    contract_value = float(product["contract_value"])
    tick_size = float(product["tick_size"])

    for account, client in clients.items():
        try:
            client.set_leverage(product_id, cfg.trading_leverage)
        except Exception:
            logger.exception("Failed to set leverage for %s account", account)

        try:
            open_orders = client.get_open_orders([product_id])
        except Exception:
            logger.exception("Failed to fetch open orders for %s account", account)
            continue

        for target in (t for t in targets if t.account == account):
            slot_prefix = f"{CLIENT_ORDER_ID_PREFIX}-{target.slot}-"
            target_price = round_to_tick(target.price, tick_size)
            tp_price = round_to_tick(target.take_profit_price, tick_size)

            slot_orders = [
                o
                for o in open_orders
                if str(o.get("client_order_id") or "").startswith(slot_prefix)
            ]
            stale_orders = [
                o for o in slot_orders if abs(float(o["limit_price"]) - target_price) > tick_size / 2
            ]
            for stale in stale_orders:
                try:
                    client.cancel_order(int(stale["id"]), product_id)
                    logger.info(
                        "%s/%s: cancelled stale order %s at %s (new target %s)",
                        account,
                        target.slot,
                        stale["id"],
                        stale["limit_price"],
                        target_price,
                    )
                except Exception:
                    logger.exception("Failed to cancel stale order %s", stale.get("id"))

            try:
                balance = client.get_available_balance()
            except Exception:
                logger.exception("Failed to fetch balance for %s account", account)
                continue

            size = compute_quantity(
                balance, cfg.trading_capital_fraction, cfg.trading_leverage, target_price, contract_value
            )
            if size < 1:
                logger.info("%s/%s: computed size < 1 contract, skipping", account, target.slot)
                continue

            margin_needed = required_margin(target_price, size, contract_value, cfg.trading_leverage)
            if balance < margin_needed:
                logger.info(
                    "%s/%s: capital fully deployed (available=%.2f < needed=%.2f), skipping",
                    account,
                    target.slot,
                    balance,
                    margin_needed,
                )
                continue

            client_order_id = f"{slot_prefix}{int(time.time() * 1000)}"[:32]
            try:
                client.place_order(
                    product_id=product_id,
                    side=target.side,
                    size=size,
                    limit_price=format_price(target_price, tick_size),
                    client_order_id=client_order_id,
                    bracket_take_profit_price=format_price(tp_price, tick_size),
                )
                logger.info(
                    "%s/%s: placed %s order size=%s price=%s tp=%s",
                    account,
                    target.slot,
                    target.side,
                    size,
                    target_price,
                    tp_price,
                )
            except Exception:
                logger.exception("Failed to place order for %s/%s", account, target.slot)

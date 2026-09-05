from __future__ import annotations

from datetime import datetime, timezone

from ip_strategy.auto_trader import (
    compute_quantity,
    compute_target_orders,
    format_price,
    required_margin,
    round_to_tick,
)
from ip_strategy.config import AppConfig
from ip_strategy.models import StrategyLevels


def _cfg(**overrides: object) -> AppConfig:
    cfg = AppConfig()
    for key, value in overrides.items():
        setattr(cfg, key, value)
    return cfg


def _levels(lhs: float, rhs: float) -> StrategyLevels:
    return StrategyLevels(
        success=True,
        computed_at=datetime.now(timezone.utc),
        lhs=lhs,
        rhs=rhs,
    )


def test_compute_target_orders_lhs_is_resistance() -> None:
    # lhs > rhs: support = rhs, resistance = lhs
    levels = _levels(lhs=3050.0, rhs=2950.0)
    cfg = _cfg()
    targets = {t.slot: t for t in compute_target_orders(levels, cfg)}

    assert len(targets) == 8
    buy_tp = 3050.0 - 2.0
    sell_tp = 2950.0 + 2.0

    for i, offset in enumerate([2.0, 8.0, 18.0, 28.0], start=1):
        main = targets[f"main_{i}"]
        assert main.account == "main"
        assert main.side == "buy"
        assert main.price == 2950.0 - offset
        assert main.take_profit_price == buy_tp

        scalper = targets[f"scalper_{i}"]
        assert scalper.account == "scalper"
        assert scalper.side == "sell"
        assert scalper.price == 3050.0 + offset
        assert scalper.take_profit_price == sell_tp


def test_compute_target_orders_lhs_is_support() -> None:
    # lhs < rhs: support = lhs, resistance = rhs
    levels = _levels(lhs=2950.0, rhs=3050.0)
    cfg = _cfg()
    targets = {t.slot: t for t in compute_target_orders(levels, cfg)}

    assert targets["main_1"].price == 2950.0 - 2.0
    assert targets["main_4"].price == 2950.0 - 28.0
    assert targets["scalper_1"].price == 3050.0 + 2.0
    assert targets["scalper_4"].price == 3050.0 + 28.0


def test_compute_target_orders_missing_levels_returns_empty() -> None:
    levels = StrategyLevels(success=False, computed_at=datetime.now(timezone.utc))
    assert compute_target_orders(levels, _cfg()) == []


def test_compute_target_orders_custom_offsets() -> None:
    levels = _levels(lhs=2950.0, rhs=3050.0)
    cfg = _cfg(trading_entry_offsets=[5.0, 20.0], trading_tp_offset=3.0)
    targets = {t.slot: t for t in compute_target_orders(levels, cfg)}
    assert len(targets) == 4
    assert targets["main_1"].price == 2950.0 - 5.0
    assert targets["main_1"].take_profit_price == 3050.0 - 3.0
    assert targets["main_2"].price == 2950.0 - 20.0
    assert targets["scalper_1"].price == 3050.0 + 5.0
    assert targets["scalper_1"].take_profit_price == 2950.0 + 3.0
    assert targets["scalper_2"].price == 3050.0 + 20.0


def test_round_to_tick() -> None:
    assert round_to_tick(2950.37, 0.05) == 2950.35
    assert round_to_tick(2950.38, 0.05) == 2950.4
    assert round_to_tick(2950.0, 0) == 2950.0


def test_format_price_matches_tick_precision() -> None:
    assert format_price(2950.5, 0.05) == "2950.50"
    assert format_price(2950.0, 1.0) == "2950"


def test_compute_quantity_floors_to_whole_contracts() -> None:
    # balance=1000, fraction=0.25, leverage=25 -> notional=6250
    # price=3000, contract_value=0.001 -> contract notional=3
    # 6250 / 3 = 2083.33 -> floor 2083
    qty = compute_quantity(
        balance=1000.0, capital_fraction=0.25, leverage=25, price=3000.0, contract_value=0.001
    )
    assert qty == 2083


def test_compute_quantity_zero_price_or_contract_value() -> None:
    assert compute_quantity(1000.0, 0.25, 25, 0.0, 0.001) == 0
    assert compute_quantity(1000.0, 0.25, 25, 3000.0, 0.0) == 0


def test_required_margin() -> None:
    # price=3000, size=2083, contract_value=0.001, leverage=25
    margin = required_margin(price=3000.0, size=2083, contract_value=0.001, leverage=25)
    assert round(margin, 2) == round((3000.0 * 2083 * 0.001) / 25, 2)


def test_required_margin_zero_leverage() -> None:
    assert required_margin(3000.0, 100, 0.001, 0) == float("inf")

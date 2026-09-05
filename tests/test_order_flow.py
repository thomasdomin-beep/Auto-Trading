from __future__ import annotations

from datetime import datetime, timezone

from ip_strategy.models import OrderFlowLeg, OrderFlowStrikeRow
from ip_strategy.order_flow import evaluate_order_flow_signal, select_atm_and_itm_rows


def _row(strike: float, ce: tuple[float, float] | None, pe: tuple[float, float] | None) -> OrderFlowStrikeRow:
    ce_leg = OrderFlowLeg(symbol=f"C-ETH-{int(strike)}-010126", atp=ce[0], ltp=ce[1]) if ce else None
    pe_leg = OrderFlowLeg(symbol=f"P-ETH-{int(strike)}-010126", atp=pe[0], ltp=pe[1]) if pe else None
    return OrderFlowStrikeRow(strike=strike, ce=ce_leg, pe=pe_leg)


def test_select_atm_and_itm_picks_neighbours() -> None:
    rows = [
        _row(2400, (10, 9), (5, 4)),
        _row(2450, (8, 7), (7, 6)),
        _row(2500, (6, 5), (9, 8)),
        _row(2550, (4, 3), (11, 10)),
    ]
    atm, ce_itm, pe_itm = select_atm_and_itm_rows(rows, spot=2498)
    assert atm.strike == 2500
    assert ce_itm.strike == 2450
    assert pe_itm.strike == 2550


def test_select_atm_and_itm_boundary_has_no_neighbour_on_one_side() -> None:
    rows = [
        _row(2400, (10, 9), (5, 4)),
        _row(2450, (8, 7), (7, 6)),
    ]
    atm, ce_itm, pe_itm = select_atm_and_itm_rows(rows, spot=2400)
    assert atm.strike == 2400
    assert ce_itm is None
    assert pe_itm.strike == 2450


def test_buy_ce_signal_when_itm_diff_drops_below_atm_diff() -> None:
    rows = [
        _row(2400, ce=(100, 98), pe=(50, 49)),  # CE ITM: atp-ltp = 2
        _row(2450, ce=(100, 95), pe=(50, 48)),  # ATM: CE atp-ltp = 5, PE atp-ltp = 2
        _row(2500, ce=(50, 49), pe=(100, 90)),  # PE ITM: atp-ltp = 10
    ]
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    signal = evaluate_order_flow_signal(rows, spot=2450, expiry_date="01-01-26", computed_at=now)
    assert signal.success
    assert signal.atm_strike == 2450
    assert signal.buy_ce is True
    assert signal.buy_pe is False
    assert signal.messages == ["Buy CE"]


def test_no_signal_when_itm_diff_not_below_atm_diff() -> None:
    rows = [
        _row(2400, ce=(100, 90), pe=(50, 49)),  # CE ITM: atp-ltp = 10 (not below ATM's 5)
        _row(2450, ce=(100, 95), pe=(50, 48)),  # ATM: CE atp-ltp = 5, PE atp-ltp = 2
        _row(2500, ce=(50, 49), pe=(100, 99)),  # PE ITM: atp-ltp = 1 (below ATM's 2 -> Buy PE)
    ]
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    signal = evaluate_order_flow_signal(rows, spot=2450, expiry_date="01-01-26", computed_at=now)
    assert signal.buy_ce is False
    assert signal.buy_pe is True
    assert signal.messages == ["Buy PE"]


def test_empty_chain_returns_failed_signal() -> None:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    signal = evaluate_order_flow_signal([], spot=2450, expiry_date=None, computed_at=now)
    assert signal.success is False
    assert signal.error is not None

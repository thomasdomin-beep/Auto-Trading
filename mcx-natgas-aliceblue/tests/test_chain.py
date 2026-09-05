from __future__ import annotations

from datetime import datetime, timezone

from mcx_atp.chain import build_snapshot, detect_atm_strike_by_parity, select_atm_and_itm_rows
from mcx_atp.models import Leg, StrikeRow


def _row(strike: float, ce_ltp: float | None, pe_ltp: float | None) -> StrikeRow:
    ce = Leg(token=f"C{int(strike)}", symbol=f"NATGASC{int(strike)}", ltp=ce_ltp) if ce_ltp is not None else None
    pe = Leg(token=f"P{int(strike)}", symbol=f"NATGASP{int(strike)}", ltp=pe_ltp) if pe_ltp is not None else None
    return StrikeRow(strike=strike, ce=ce, pe=pe)


def test_detect_atm_strike_by_parity_picks_smallest_ce_pe_gap() -> None:
    rows = [
        _row(240, 10, 5),
        _row(250, 8, 7),  # smallest |CE-PE| gap (1) -> ATM
        _row(260, 6, 9),
    ]
    assert detect_atm_strike_by_parity(rows) == 250


def test_select_atm_and_itm_picks_neighbours() -> None:
    rows = [_row(240, 10, 5), _row(250, 8, 7), _row(260, 6, 9), _row(270, 4, 11)]
    atm, ce_itm, pe_itm = select_atm_and_itm_rows(rows, atm_strike=260)
    assert atm.strike == 260
    assert ce_itm.strike == 250
    assert pe_itm.strike == 270


def test_select_atm_and_itm_boundary_has_no_neighbour_on_one_side() -> None:
    rows = [_row(240, 10, 5), _row(250, 8, 7)]
    atm, ce_itm, pe_itm = select_atm_and_itm_rows(rows, atm_strike=240)
    assert atm.strike == 240
    assert ce_itm is None
    assert pe_itm.strike == 250


def _market(token: str, ltp: float, atp: float) -> dict[str, float | None]:
    return {"ltp": ltp, "atp": atp}


def test_build_snapshot_buy_ce_when_itm_diff_drops_below_atm_diff() -> None:
    rows = [_row(240, 10, 5), _row(250, 8, 7), _row(260, 6, 9)]
    market = {
        "C240": _market("C240", 98, 100),  # CE ITM: atp-ltp = 2
        "C250": _market("C250", 95, 100),  # CE ATM: atp-ltp = 5
        "P250": _market("P250", 48, 50),  # PE ATM: atp-ltp = 2
        "P260": _market("P260", 90, 100),  # PE ITM: atp-ltp = 10
    }
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    snapshot = build_snapshot(rows, market, "MCX", "NATURALGAS", "27FEB26", now)
    assert snapshot.success
    assert snapshot.atm_strike == 250
    assert snapshot.buy_ce is True
    assert snapshot.buy_pe is False
    assert snapshot.messages == ["Buy CE"]
    assert snapshot.ce_atm.atp_minus_ltp == 5
    assert snapshot.ce_itm.atp_minus_ltp == 2


def test_build_snapshot_no_signal_when_itm_diff_not_below_atm_diff() -> None:
    rows = [_row(240, 10, 5), _row(250, 8, 7), _row(260, 6, 9)]
    market = {
        "C240": _market("C240", 90, 100),  # CE ITM: atp-ltp = 10 (not below ATM's 5)
        "C250": _market("C250", 95, 100),  # CE ATM: atp-ltp = 5
        "P250": _market("P250", 48, 50),  # PE ATM: atp-ltp = 2
        "P260": _market("P260", 99, 100),  # PE ITM: atp-ltp = 1 (below ATM's 2 -> Buy PE)
    }
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    snapshot = build_snapshot(rows, market, "MCX", "NATURALGAS", "27FEB26", now)
    assert snapshot.buy_ce is False
    assert snapshot.buy_pe is True
    assert snapshot.messages == ["Buy PE"]


def test_empty_chain_returns_failed_snapshot() -> None:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    snapshot = build_snapshot([], {}, "MCX", "NATURALGAS", "27FEB26", now)
    assert snapshot.success is False
    assert snapshot.error is not None

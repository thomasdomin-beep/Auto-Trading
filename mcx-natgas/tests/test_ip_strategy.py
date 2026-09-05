from __future__ import annotations

from mcx_ip.ip_strategy import compute_ip, compute_lhs_rhs, find_crossover_strikes
from mcx_ip.models import OptionLeg, StrikeRow


def _row(strike: float, ce_p: float, pe_p: float) -> StrikeRow:
    return StrikeRow(
        strike=strike,
        ce=OptionLeg(symbol=f"NATURALGAS23SEP2026C{strike:g}", premium=ce_p),
        pe=OptionLeg(symbol=f"NATURALGAS23SEP2026P{strike:g}", premium=pe_p),
    )


def test_find_crossover_closest_to_spot() -> None:
    chain = [
        _row(280, ce_p=50, pe_p=80),
        _row(290, ce_p=55, pe_p=70),
        _row(300, ce_p=60, pe_p=55),  # CE > PE
        _row(310, ce_p=45, pe_p=50),  # CE < PE
        _row(320, ce_p=40, pe_p=60),
    ]
    pair = find_crossover_strikes(chain, spot=305)
    assert pair is not None
    assert pair.strike_a == 300
    assert pair.strike_b == 310


def test_compute_ip_average() -> None:
    premiums = {"a": 10.0, "b": 20.0, "c": 30.0, "d": 40.0}
    assert compute_ip(premiums) == 25.0


def test_lhs_rhs_scans_whole_ce_and_pe_columns() -> None:
    chain = [
        _row(280, ce_p=100, pe_p=10),
        _row(290, ce_p=24, pe_p=15),
        _row(300, ce_p=30, pe_p=28),
        _row(310, ce_p=20, pe_p=26),
        _row(320, ce_p=10, pe_p=100),
    ]
    lhs, rhs = compute_lhs_rhs(chain, spot=300, ideal_premium=25.0)
    assert lhs == 290
    assert rhs == 310


def test_lhs_rhs_not_restricted_to_below_above_spot() -> None:
    # LHS/RHS must scan the entire CE (left) and PE (right) columns for the
    # closest premium to IP - not just strikes below/above spot.
    chain = [
        _row(2380, ce_p=66.60, pe_p=3.20),
        _row(2400, ce_p=49.50, pe_p=6.30),
        _row(2420, ce_p=34.55, pe_p=10.90),
        _row(2430, ce_p=28.00, pe_p=14.60),
        _row(2440, ce_p=22.20, pe_p=18.65),
        _row(2450, ce_p=17.35, pe_p=23.85),
        _row(2460, ce_p=13.40, pe_p=29.16),
        _row(2470, ce_p=9.80, pe_p=36.35),
        _row(2480, ce_p=7.10, pe_p=43.65),
        _row(2490, ce_p=5.15, pe_p=51.65),
    ]
    lhs, rhs = compute_lhs_rhs(chain, spot=2440.83, ideal_premium=10.475)
    assert lhs == 2470
    assert rhs == 2420

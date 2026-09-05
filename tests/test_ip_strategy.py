from __future__ import annotations

from ip_strategy.models import OptionLeg, StrikeRow
from ip_strategy.ip_strategy import (
    compute_ip,
    compute_lhs_rhs,
    find_crossover_strikes,
)


def _row(strike: float, ce_p: float, pe_p: float) -> StrikeRow:
    return StrikeRow(
        strike=strike,
        ce=OptionLeg(symbol=f"C-ETH-{int(strike)}-010126", premium=ce_p),
        pe=OptionLeg(symbol=f"P-ETH-{int(strike)}-010126", premium=pe_p),
    )


def test_find_crossover_closest_to_spot() -> None:
    chain = [
        _row(2800, ce_p=50, pe_p=80),
        _row(2900, ce_p=55, pe_p=70),
        _row(3000, ce_p=60, pe_p=55),  # CE > PE
        _row(3100, ce_p=45, pe_p=50),  # CE < PE
        _row(3200, ce_p=40, pe_p=60),
    ]
    pair = find_crossover_strikes(chain, spot=3050)
    assert pair is not None
    assert pair.strike_a == 3000
    assert pair.strike_b == 3100


def test_find_crossover_picks_nearest_midpoint() -> None:
    chain = [
        _row(2700, ce_p=70, pe_p=30),
        _row(2800, ce_p=60, pe_p=40),
        _row(2900, ce_p=55, pe_p=45),
        _row(3000, ce_p=50, pe_p=48),
        _row(3100, ce_p=40, pe_p=55),
        _row(3200, ce_p=30, pe_p=65),
    ]
    pair = find_crossover_strikes(chain, spot=2950)
    assert pair is not None
    assert pair.strike_a == 3000
    assert pair.strike_b == 3100


def test_compute_ip_average() -> None:
    lows = {"a": 10.0, "b": 20.0, "c": 30.0, "d": 40.0}
    assert compute_ip(lows) == 25.0


def test_lhs_rhs_scans_whole_ce_and_pe_columns() -> None:
    chain = [
        _row(2800, ce_p=100, pe_p=10),
        _row(2900, ce_p=24, pe_p=15),
        _row(3000, ce_p=30, pe_p=28),
        _row(3100, ce_p=20, pe_p=26),
        _row(3200, ce_p=10, pe_p=100),
    ]
    ip = 25.0
    lhs, rhs = compute_lhs_rhs(chain, spot=3000, ideal_premium=ip)
    assert lhs == 2900
    assert rhs == 3100


def test_lhs_rhs_not_restricted_to_below_above_spot() -> None:
    # Regression test: LHS/RHS must scan the entire CE (left) and PE (right)
    # columns for the closest premium to IP - not just strikes below/above
    # spot. Here the best CE match (LHS) sits above spot and the best PE
    # match (RHS) sits below spot.
    chain = [
        _row(2900, ce_p=25, pe_p=5),
        _row(3100, ce_p=5, pe_p=25),
    ]
    lhs, rhs = compute_lhs_rhs(chain, spot=3000, ideal_premium=25)
    assert lhs == 2900
    assert rhs == 3100


def test_lhs_rhs_matches_reported_option_chain_example() -> None:
    # Derived from a real ETH option chain snapshot (spot ~2440.83, IP=10.475):
    # LHS should be 2470 (CE premium ~9.8 is the closest CE match to IP, even
    # though 2470 is above spot) and RHS should be 2420 (PE premium ~10.9 is
    # the closest PE match to IP, even though 2420 is below spot).
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

from nse_ip.models import OptionLeg, StrikeRow
from nse_ip.ip_strategy import compute_ip, compute_support_resistance, find_crossover_strikes


def _row(strike: float, ce: float, pe: float) -> StrikeRow:
    return StrikeRow(
        strike=strike,
        ce=OptionLeg(symbol=f"CE{strike}", identifier=f"CE{strike}", premium=ce),
        pe=OptionLeg(symbol=f"PE{strike}", identifier=f"PE{strike}", premium=pe),
    )


def test_crossover_and_sr() -> None:
    chain = [
        _row(24500, 50, 80),
        _row(24600, 60, 55),
        _row(24700, 45, 50),
    ]
    pair = find_crossover_strikes(chain, spot=24650)
    assert pair and pair.strike_a == 24600 and pair.strike_b == 24700
    ip = compute_ip({"a": 10.0, "b": 20.0, "c": 30.0, "d": 40.0})
    assert ip == 25.0
    s, r = compute_support_resistance(chain, 24650, 25.0)
    assert s == 24500 and r == 24700

from sensex_ip.models import OptionLeg, StrikeRow
from sensex_ip.ip_strategy import (
    compute_ip,
    compute_support_resistance,
    find_crossover_strikes,
)


def _row(strike: float, ce_p: float, pe_p: float, ce_id: str, pe_id: str) -> StrikeRow:
    return StrikeRow(
        strike=strike,
        ce=OptionLeg(symbol=f"CE-{int(strike)}", scrip_id=ce_id, premium=ce_p),
        pe=OptionLeg(symbol=f"PE-{int(strike)}", scrip_id=pe_id, premium=pe_p),
    )


def test_find_crossover_closest_to_spot() -> None:
    chain = [
        _row(78000, ce_p=50, pe_p=80, ce_id="1", pe_id="2"),
        _row(78500, ce_p=55, pe_p=70, ce_id="3", pe_id="4"),
        _row(79000, ce_p=60, pe_p=55, ce_id="5", pe_id="6"),
        _row(79500, ce_p=45, pe_p=50, ce_id="7", pe_id="8"),
    ]
    pair = find_crossover_strikes(chain, spot=79200)
    assert pair is not None
    assert pair.strike_a == 79000
    assert pair.strike_b == 79500


def test_compute_ip_average() -> None:
    assert compute_ip({"a": 10.0, "b": 20.0, "c": 30.0, "d": 40.0}) == 25.0


def test_support_resistance() -> None:
    chain = [
        _row(78000, 100, 10, "a", "b"),
        _row(78500, 24, 15, "c", "d"),
        _row(79000, 30, 28, "e", "f"),
        _row(79500, 20, 26, "g", "h"),
    ]
    support, resistance = compute_support_resistance(chain, spot=79000, ideal_premium=25.0)
    assert support == 78500
    assert resistance == 79500

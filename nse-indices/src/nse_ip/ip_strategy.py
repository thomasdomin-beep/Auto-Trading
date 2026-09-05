from __future__ import annotations

from nse_ip.models import CrossoverPair, StrikeRow


def find_crossover_strikes(
    chain: list[StrikeRow], spot: float
) -> CrossoverPair | None:
    candidates: list[tuple[float, CrossoverPair]] = []
    for i in range(len(chain) - 1):
        k1, k2 = chain[i], chain[i + 1]
        ce1, pe1 = k1.ce_premium(), k1.pe_premium()
        ce2, pe2 = k2.ce_premium(), k2.pe_premium()
        if ce1 is None or pe1 is None or ce2 is None or pe2 is None:
            continue
        if not (k1.ce and k1.pe and k2.ce and k2.pe):
            continue
        if ce1 > pe1 and ce2 < pe2:
            mid = (k1.strike + k2.strike) / 2.0
            dist = abs(mid - spot)
            pair = CrossoverPair(
                strike_a=k1.strike,
                strike_b=k2.strike,
                symbol_ce_a=k1.ce.symbol,
                symbol_pe_a=k1.pe.symbol,
                symbol_ce_b=k2.ce.symbol,
                symbol_pe_b=k2.pe.symbol,
                id_ce_a=k1.ce.identifier,
                id_pe_a=k1.pe.identifier,
                id_ce_b=k2.ce.identifier,
                id_pe_b=k2.pe.identifier,
            )
            candidates.append((dist, pair))
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0])
    return candidates[0][1]


def compute_ip(daily_lows: dict[str, float]) -> float:
    if not daily_lows:
        raise ValueError("No daily lows provided for IP calculation")
    return sum(daily_lows.values()) / len(daily_lows)


def compute_support_resistance(
    chain: list[StrikeRow],
    spot: float,
    ideal_premium: float,
) -> tuple[float, float]:
    best_below: tuple[float, float] | None = None
    best_above: tuple[float, float] | None = None

    for row in chain:
        if row.strike < spot:
            ce = row.ce_premium()
            if ce is None:
                continue
            dist = abs(ce - ideal_premium)
            if best_below is None or dist < best_below[0] or (
                dist == best_below[0]
                and abs(row.strike - spot) < abs(best_below[1] - spot)
            ):
                best_below = (dist, row.strike)
        elif row.strike > spot:
            pe = row.pe_premium()
            if pe is None:
                continue
            dist = abs(pe - ideal_premium)
            if best_above is None or dist < best_above[0] or (
                dist == best_above[0]
                and abs(row.strike - spot) < abs(best_above[1] - spot)
            ):
                best_above = (dist, row.strike)

    if best_below is None or best_above is None:
        raise ValueError(
            "Could not find support/resistance strikes (need strikes both below and above spot)"
        )

    return min(best_below[1], best_above[1]), max(best_below[1], best_above[1])

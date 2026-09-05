from __future__ import annotations

from ip_strategy.models import CrossoverPair, StrikeRow

def find_crossover_strikes(
    chain: list[StrikeRow], spot: float
) -> CrossoverPair | None:
    """Find adjacent K1 < K2 with CE(K1) > PE(K1) and CE(K2) < PE(K2); closest to spot."""
    candidates: list[tuple[float, CrossoverPair]] = []
    for i in range(len(chain) - 1):
        k1, k2 = chain[i], chain[i + 1]
        ce1, pe1 = k1.ce_premium(), k1.pe_premium()
        ce2, pe2 = k2.ce_premium(), k2.pe_premium()
        if ce1 is None or pe1 is None or ce2 is None or pe2 is None:
            continue
        if k1.ce is None or k1.pe is None or k2.ce is None or k2.pe is None:
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


def compute_lhs_rhs(
    chain: list[StrikeRow],
    spot: float,
    ideal_premium: float,
) -> tuple[float, float]:
    """
    Scan the left side of the option chain (the CE/Calls column, across every
    strike) and find the premium closest to IP; LHS = the strike price for
    that closest match.
    Scan the right side of the option chain (the PE/Puts column, across every
    strike) and find the premium closest to IP; RHS = the strike price for
    that closest match.

    The scan is over the whole CE/PE columns, not restricted to strikes below
    or above spot - a strike above spot can still win on the CE (left) side,
    and vice versa for PE (right). Spot is only used to break ties between two
    equally-close premiums.
    """
    best_ce: tuple[float, float] | None = None  # (distance, strike)
    best_pe: tuple[float, float] | None = None

    for row in chain:
        ce = row.ce_premium()
        if ce is not None:
            dist = abs(ce - ideal_premium)
            if best_ce is None or dist < best_ce[0] or (
                dist == best_ce[0] and abs(row.strike - spot) < abs(best_ce[1] - spot)
            ):
                best_ce = (dist, row.strike)

        pe = row.pe_premium()
        if pe is not None:
            dist = abs(pe - ideal_premium)
            if best_pe is None or dist < best_pe[0] or (
                dist == best_pe[0] and abs(row.strike - spot) < abs(best_pe[1] - spot)
            ):
                best_pe = (dist, row.strike)

    if best_ce is None or best_pe is None:
        raise ValueError(
            "Could not find LHS/RHS strikes (need at least one CE and one PE premium)"
        )

    return best_ce[1], best_pe[1]

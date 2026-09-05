from __future__ import annotations

from datetime import datetime
from typing import Any

from mcx_atp.models import ChainSnapshot, Leg, StrikeRow


def _num(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_option_chain(raw_rows: list[dict[str, Any]]) -> list[StrikeRow]:
    """Convert Aliceblue's getOptionChain `data` array into StrikeRow objects,
    sorted ascending by strike."""
    rows: list[StrikeRow] = []
    for raw in raw_rows:
        strike = _num(raw.get("strikeprice"))
        if strike is None:
            continue
        ce_raw = raw.get("CE") or {}
        pe_raw = raw.get("PE") or {}
        ce = (
            Leg(token=str(ce_raw["token"]), symbol=ce_raw.get("tradingsymbol", ""), ltp=_num(ce_raw.get("ltp")))
            if ce_raw.get("token") is not None
            else None
        )
        pe = (
            Leg(token=str(pe_raw["token"]), symbol=pe_raw.get("tradingsymbol", ""), ltp=_num(pe_raw.get("ltp")))
            if pe_raw.get("token") is not None
            else None
        )
        rows.append(StrikeRow(strike=strike, ce=ce, pe=pe))
    rows.sort(key=lambda r: r.strike)
    return rows


def detect_atm_strike_by_parity(rows: list[StrikeRow]) -> float | None:
    """Approximate the at-the-money strike using put-call parity: at the
    strike closest to the underlying (future) price, CE and PE premiums
    should be closest to each other. Used because Aliceblue's Option Chain
    response doesn't include a separate underlying/spot price field."""
    best_strike: float | None = None
    best_diff: float | None = None
    for row in rows:
        if row.ce is None or row.pe is None or row.ce.ltp is None or row.pe.ltp is None:
            continue
        diff = abs(row.ce.ltp - row.pe.ltp)
        if best_diff is None or diff < best_diff:
            best_diff = diff
            best_strike = row.strike
    return best_strike


def select_atm_and_itm_rows(
    rows: list[StrikeRow], atm_strike: float
) -> tuple[StrikeRow | None, StrikeRow | None, StrikeRow | None]:
    """Pick the ATM strike row and its nearest in-the-money neighbour for CE and PE.

    CE ITM = the next lower strike than ATM (deeper in-the-money for calls).
    PE ITM = the next higher strike than ATM (deeper in-the-money for puts).
    `rows` must already be sorted ascending by strike.
    """
    if not rows:
        return None, None, None

    best_idx = 0
    best_dist: float | None = None
    for i, row in enumerate(rows):
        dist = abs(row.strike - atm_strike)
        if best_dist is None or dist < best_dist:
            best_dist = dist
            best_idx = i

    atm_row = rows[best_idx]
    ce_itm_row = rows[best_idx - 1] if best_idx > 0 else None
    pe_itm_row = rows[best_idx + 1] if best_idx < len(rows) - 1 else None
    return atm_row, ce_itm_row, pe_itm_row


def market_data_tokens(
    atm_row: StrikeRow, ce_itm_row: StrikeRow | None, pe_itm_row: StrikeRow | None, exchange: str
) -> list[tuple[str, str]]:
    tokens: list[tuple[str, str]] = []
    for leg in (
        atm_row.ce,
        atm_row.pe,
        ce_itm_row.ce if ce_itm_row else None,
        pe_itm_row.pe if pe_itm_row else None,
    ):
        if leg is not None:
            tokens.append((exchange, leg.token))
    return tokens


def apply_market_data(leg: Leg | None, market: dict[str, dict[str, float | None]]) -> Leg | None:
    if leg is None:
        return None
    data = market.get(leg.token)
    if not data:
        return leg
    return leg.model_copy(update={"ltp": data.get("ltp") or leg.ltp, "atp": data.get("atp")})


def build_snapshot(
    rows: list[StrikeRow],
    market: dict[str, dict[str, float | None]],
    exchange: str,
    underlying: str,
    expiry_date: str,
    computed_at: datetime,
) -> ChainSnapshot:
    atm_strike = detect_atm_strike_by_parity(rows)
    if atm_strike is None:
        return ChainSnapshot(
            success=False,
            error="Could not detect ATM strike (no rows with both CE and PE LTP)",
            computed_at=computed_at,
            underlying=underlying,
            expiry_date=expiry_date,
        )

    atm_row, ce_itm_row, pe_itm_row = select_atm_and_itm_rows(rows, atm_strike)
    if atm_row is None:
        return ChainSnapshot(
            success=False,
            error="Option chain is empty",
            computed_at=computed_at,
            underlying=underlying,
            expiry_date=expiry_date,
        )

    ce_atm = apply_market_data(atm_row.ce, market)
    pe_atm = apply_market_data(atm_row.pe, market)
    ce_itm = apply_market_data(ce_itm_row.ce if ce_itm_row else None, market)
    pe_itm = apply_market_data(pe_itm_row.pe if pe_itm_row else None, market)

    snapshot = ChainSnapshot(
        success=True,
        computed_at=computed_at,
        underlying=underlying,
        expiry_date=expiry_date,
        atm_strike=atm_row.strike,
        ce_itm_strike=ce_itm_row.strike if ce_itm_row else None,
        pe_itm_strike=pe_itm_row.strike if pe_itm_row else None,
        ce_atm=ce_atm,
        ce_itm=ce_itm,
        pe_atm=pe_atm,
        pe_itm=pe_itm,
    )

    messages: list[str] = []
    ce_atm_diff = ce_atm.atp_minus_ltp if ce_atm else None
    ce_itm_diff = ce_itm.atp_minus_ltp if ce_itm else None
    if ce_atm_diff is not None and ce_itm_diff is not None and ce_itm_diff < ce_atm_diff:
        snapshot.buy_ce = True
        messages.append("Buy CE")

    pe_atm_diff = pe_atm.atp_minus_ltp if pe_atm else None
    pe_itm_diff = pe_itm.atp_minus_ltp if pe_itm else None
    if pe_atm_diff is not None and pe_itm_diff is not None and pe_itm_diff < pe_atm_diff:
        snapshot.buy_pe = True
        messages.append("Buy PE")

    snapshot.messages = messages
    return snapshot

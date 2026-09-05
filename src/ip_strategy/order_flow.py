from __future__ import annotations

from datetime import datetime

from ip_strategy.models import OrderFlowSignal, OrderFlowStrikeRow


def select_atm_and_itm_rows(
    rows: list[OrderFlowStrikeRow], spot: float
) -> tuple[OrderFlowStrikeRow | None, OrderFlowStrikeRow | None, OrderFlowStrikeRow | None]:
    """Pick the ATM strike and its nearest in-the-money neighbour for CE and PE.

    ATM = strike closest to spot (ties broken by the lower strike).
    CE ITM = the next lower strike than ATM (deeper in-the-money for calls).
    PE ITM = the next higher strike than ATM (deeper in-the-money for puts).

    `rows` must already be sorted ascending by strike.
    """
    if not rows:
        return None, None, None

    best_idx = 0
    best_dist: float | None = None
    for i, row in enumerate(rows):
        dist = abs(row.strike - spot)
        if best_dist is None or dist < best_dist:
            best_dist = dist
            best_idx = i

    atm_row = rows[best_idx]
    ce_itm_row = rows[best_idx - 1] if best_idx > 0 else None
    pe_itm_row = rows[best_idx + 1] if best_idx < len(rows) - 1 else None
    return atm_row, ce_itm_row, pe_itm_row


def evaluate_order_flow_signal(
    rows: list[OrderFlowStrikeRow],
    spot: float,
    expiry_date: str | None,
    computed_at: datetime,
) -> OrderFlowSignal:
    """Compare ITM vs ATM (ATP - LTP) for CE and PE and raise Buy CE / Buy PE signals.

    For CE: signal when (ATP - LTP) of the nearest ITM call is less than that of
    the ATM call. For PE: signal when (ATP - LTP) of the nearest ITM put is less
    than that of the ATM put.
    """
    atm_row, ce_itm_row, pe_itm_row = select_atm_and_itm_rows(rows, spot)
    if atm_row is None:
        return OrderFlowSignal(
            success=False,
            error="Option chain is empty",
            computed_at=computed_at,
            expiry_date=expiry_date,
            spot=spot,
        )

    ce_atm = atm_row.ce
    pe_atm = atm_row.pe
    ce_itm = ce_itm_row.ce if ce_itm_row else None
    pe_itm = pe_itm_row.pe if pe_itm_row else None

    signal = OrderFlowSignal(
        success=True,
        computed_at=computed_at,
        expiry_date=expiry_date,
        spot=spot,
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
        signal.buy_ce = True
        messages.append("Buy CE")

    pe_atm_diff = pe_atm.atp_minus_ltp if pe_atm else None
    pe_itm_diff = pe_itm.atp_minus_ltp if pe_itm else None
    if pe_atm_diff is not None and pe_itm_diff is not None and pe_itm_diff < pe_atm_diff:
        signal.buy_pe = True
        messages.append("Buy PE")

    signal.messages = messages
    return signal

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone

from mcx_atp.aliceblue_client import AliceblueApiError, AliceblueClient
from mcx_atp.chain import (
    build_snapshot,
    detect_atm_strike_by_parity,
    market_data_tokens,
    parse_option_chain,
    select_atm_and_itm_rows,
)
from mcx_atp.config import AppConfig
from mcx_atp.models import ChainSnapshot

logger = logging.getLogger(__name__)


def _nearest_expiry(expiries: list[str]) -> str | None:
    if not expiries:
        return None
    parsed: list[tuple[datetime, str]] = []
    for e in expiries:
        try:
            parsed.append((datetime.strptime(e, "%d%b%y"), e))
        except ValueError:
            continue
    if not parsed:
        return expiries[0]
    parsed.sort(key=lambda t: t[0])
    return parsed[0][1]


def fetch_snapshot(cfg: AppConfig, client: AliceblueClient) -> ChainSnapshot:
    now = datetime.now(timezone.utc)
    try:
        expiries = client.get_underlying_expiry(cfg.underlying, cfg.exch)
        expiry = _nearest_expiry(expiries)
        if not expiry:
            return ChainSnapshot(
                success=False,
                error=f"No live expiries found for {cfg.underlying}",
                computed_at=now,
                underlying=cfg.underlying,
            )

        raw = client.get_option_chain(cfg.underlying, expiry, cfg.exch, cfg.strike_interval)
        rows = parse_option_chain(raw)
        if len(rows) < 2:
            return ChainSnapshot(
                success=False,
                error="Option chain too small",
                computed_at=now,
                underlying=cfg.underlying,
                expiry_date=expiry,
            )

        atm_strike = detect_atm_strike_by_parity(rows)
        if atm_strike is None:
            return ChainSnapshot(
                success=False,
                error="Could not detect ATM strike",
                computed_at=now,
                underlying=cfg.underlying,
                expiry_date=expiry,
            )
        atm_row, ce_itm_row, pe_itm_row = select_atm_and_itm_rows(rows, atm_strike)
        if atm_row is None:
            return ChainSnapshot(
                success=False,
                error="Option chain is empty",
                computed_at=now,
                underlying=cfg.underlying,
                expiry_date=expiry,
            )

        tokens = market_data_tokens(atm_row, ce_itm_row, pe_itm_row, cfg.exch_market_data)
        market = client.get_market_data(tokens)

        return build_snapshot(rows, market, cfg.exch_market_data, cfg.underlying, expiry, now)
    except AliceblueApiError as e:
        return ChainSnapshot(success=False, error=str(e), computed_at=now, underlying=cfg.underlying)


class ChainState:
    """Thread-safe holder for the latest chain snapshot, shared between the
    background poller and the bridge UI (same process)."""

    def __init__(self) -> None:
        self._snapshot: ChainSnapshot | None = None
        self._lock = threading.Lock()

    def get(self) -> ChainSnapshot | None:
        with self._lock:
            return self._snapshot

    def set(self, snapshot: ChainSnapshot) -> None:
        with self._lock:
            self._snapshot = snapshot


def poll_loop(
    cfg: AppConfig,
    client: AliceblueClient,
    state: ChainState,
    stop_event: threading.Event | None = None,
) -> None:
    while stop_event is None or not stop_event.is_set():
        try:
            snapshot = fetch_snapshot(cfg, client)
            if snapshot.success:
                if snapshot.messages:
                    logger.info("Signal: %s (expiry=%s)", ", ".join(snapshot.messages), snapshot.expiry_date)
            else:
                logger.warning("Poll failed: %s", snapshot.error)
        except Exception as e:
            logger.exception("Poll crashed: %s", e)
            snapshot = ChainSnapshot(success=False, error=str(e), computed_at=datetime.now(timezone.utc))
        state.set(snapshot)

        wait_seconds = max(cfg.poll_seconds, 1.0)
        if stop_event is not None:
            stop_event.wait(wait_seconds)
        else:
            time.sleep(wait_seconds)


def start_poll_thread(
    cfg: AppConfig, client: AliceblueClient, state: ChainState
) -> tuple[threading.Thread, threading.Event]:
    stop_event = threading.Event()
    thread = threading.Thread(
        target=poll_loop, args=(cfg, client, state, stop_event), name="mcx-atp-poll", daemon=True
    )
    thread.start()
    return thread, stop_event

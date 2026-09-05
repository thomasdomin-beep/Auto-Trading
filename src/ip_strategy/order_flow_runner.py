from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone

from ip_strategy.config import AppConfig
from ip_strategy.delta_client import DeltaClient
from ip_strategy.models import OrderFlowSignal
from ip_strategy.order_flow import evaluate_order_flow_signal
from ip_strategy.runner import RunState

logger = logging.getLogger(__name__)


class OrderFlowState:
    """Thread-safe holder for the latest order-flow signal.

    Shared between the background poller and the bridge UI (same process).
    """

    def __init__(self) -> None:
        self._signal: OrderFlowSignal | None = None
        self._lock = threading.Lock()

    def get(self) -> OrderFlowSignal | None:
        with self._lock:
            return self._signal

    def set(self, signal: OrderFlowSignal) -> None:
        with self._lock:
            self._signal = signal


def run_order_flow_once(cfg: AppConfig, expiry_override: str | None = None) -> OrderFlowSignal:
    now = datetime.now(timezone.utc)
    with DeltaClient(cfg.delta_base_url, cfg.candle_request_delay_seconds) as client:
        expiry = expiry_override or client.nearest_expiry_date(cfg.underlying)
        if not expiry:
            return OrderFlowSignal(
                success=False,
                error="No live option expiry found",
                computed_at=now,
            )

        perp = client.get_ticker(cfg.perp_symbol)
        spot_raw = perp.get("spot_price") or perp.get("mark_price")
        if spot_raw is None:
            return OrderFlowSignal(
                success=False,
                error=f"Could not read spot from {cfg.perp_symbol}",
                computed_at=now,
                expiry_date=expiry,
            )
        spot = float(spot_raw)

        tickers = client.get_option_chain_tickers(cfg.underlying, expiry)
        rows = client.merge_chain_by_strike_atp_ltp(tickers)
        if len(rows) < 2:
            return OrderFlowSignal(
                success=False,
                error="Option chain too small",
                computed_at=now,
                expiry_date=expiry,
                spot=spot,
            )

        return evaluate_order_flow_signal(rows, spot, expiry, now)


def order_flow_poll_loop(
    cfg: AppConfig,
    of_state: OrderFlowState,
    run_state: RunState | None = None,
    stop_event: threading.Event | None = None,
) -> None:
    """Continuously poll Delta's option chain and update `of_state` with the latest signal."""
    while stop_event is None or not stop_event.is_set():
        expiry_override = run_state.get_expiry() if run_state is not None else None
        try:
            signal = run_order_flow_once(cfg, expiry_override)
            if signal.success:
                if signal.buy_ce:
                    logger.info(
                        "Order-flow signal: Buy CE (expiry=%s spot=%s)",
                        signal.expiry_date,
                        signal.spot,
                    )
                if signal.buy_pe:
                    logger.info(
                        "Order-flow signal: Buy PE (expiry=%s spot=%s)",
                        signal.expiry_date,
                        signal.spot,
                    )
            else:
                logger.warning("Order-flow poll failed: %s", signal.error)
        except Exception as e:
            logger.exception("Order-flow poll crashed: %s", e)
            signal = OrderFlowSignal(success=False, error=str(e), computed_at=datetime.now(timezone.utc))
        of_state.set(signal)

        wait_seconds = max(cfg.order_flow_poll_seconds, 0.5)
        if stop_event is not None:
            stop_event.wait(wait_seconds)
        else:
            time.sleep(wait_seconds)


def start_order_flow_thread(
    cfg: AppConfig,
    of_state: OrderFlowState,
    run_state: RunState | None = None,
) -> tuple[threading.Thread, threading.Event]:
    stop_event = threading.Event()
    thread = threading.Thread(
        target=order_flow_poll_loop,
        args=(cfg, of_state, run_state, stop_event),
        name="ip-strategy-order-flow",
        daemon=True,
    )
    thread.start()
    return thread, stop_event

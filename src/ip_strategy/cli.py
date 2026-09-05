from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from apscheduler.schedulers.blocking import BlockingScheduler

from ip_strategy.config import AppConfig
from ip_strategy.order_flow_runner import OrderFlowState, start_order_flow_thread
from ip_strategy.runner import RunState, execute_run


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def main(argv: list[str] | None = None) -> int:
    _setup_logging()
    parser = argparse.ArgumentParser(description="ETHUSD.P Ideal Premium strategy")
    parent = argparse.ArgumentParser(add_help=False)
    parent.add_argument(
        "-c",
        "--config",
        type=Path,
        default=Path("config.yaml"),
        help="Path to config.yaml",
    )
    parent.add_argument(
        "--expiry",
        type=str,
        default=None,
        help="Override the option expiry date (DD-MM-YYYY); default is the nearest live expiry",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("run-once", parents=[parent], help="Run strategy once and write levels.json")

    sched = sub.add_parser("schedule", parents=[parent], help="Run on interval from config")
    sched.add_argument(
        "--with-bridge",
        action="store_true",
        help="Also start local web UI (same process, background thread)",
    )

    sub.add_parser("serve-bridge", parents=[parent], help="Serve local levels UI only")

    sub.add_parser(
        "trade",
        parents=[parent],
        help=(
            "Run the ETHUSD auto-trader continuously: recompute levels and "
            "reconcile the 4 resting entry orders on an interval. Places "
            "real live orders; requires trading_enabled: true and the "
            "IP_STRATEGY_DELTA_MAIN_*/DELTA_SCALPER_* API key env vars."
        ),
    )

    args = parser.parse_args(argv)
    cfg = AppConfig.load(args.config)
    if args.expiry:
        cfg.expiry_date = args.expiry

    if args.command == "run-once":
        levels = execute_run(cfg)
        return 0 if levels.success else 1

    if args.command == "serve-bridge":
        from ip_strategy.bridge import serve

        state = RunState(cfg.expiry_date)
        of_state = OrderFlowState()
        if cfg.order_flow_enabled:
            start_order_flow_thread(cfg, of_state, state)
        serve(cfg, state, of_state)
        return 0

    if args.command == "trade":
        from ip_strategy.auto_trader import run_trading_cycle
        from ip_strategy.delta_trading_client import DeltaTradingClient

        if not cfg.trading_enabled:
            logging.getLogger(__name__).error(
                "trading_enabled is false; refusing to start the trader. "
                "Set trading_enabled: true in config.yaml once you're ready to trade live."
            )
            return 1
        missing = [
            name
            for name, value in (
                ("delta_main_api_key", cfg.delta_main_api_key),
                ("delta_main_api_secret", cfg.delta_main_api_secret),
                ("delta_scalper_api_key", cfg.delta_scalper_api_key),
                ("delta_scalper_api_secret", cfg.delta_scalper_api_secret),
            )
            if not value
        ]
        if missing:
            logging.getLogger(__name__).error(
                "Missing required credentials: %s. Set them via IP_STRATEGY_* env vars.",
                ", ".join(missing),
            )
            return 1

        state = RunState(cfg.expiry_date)
        main_client = DeltaTradingClient(
            cfg.delta_base_url, cfg.delta_main_api_key, cfg.delta_main_api_secret
        )
        scalper_client = DeltaTradingClient(
            cfg.delta_base_url, cfg.delta_scalper_api_key, cfg.delta_scalper_api_secret
        )

        def trading_job() -> None:
            levels = execute_run(cfg, state=state)
            try:
                run_trading_cycle(cfg, levels, main_client, scalper_client)
            except Exception:
                logging.getLogger(__name__).exception("Trading cycle failed")

        scheduler = BlockingScheduler()
        scheduler.add_job(
            trading_job,
            "interval",
            minutes=cfg.trading_poll_minutes,
            id="ip_strategy_trade",
            max_instances=1,
            coalesce=True,
        )
        logging.getLogger(__name__).info(
            "Auto-trader started; interval=%s minutes", cfg.trading_poll_minutes
        )
        trading_job()
        try:
            scheduler.start()
        except (KeyboardInterrupt, SystemExit):
            pass
        finally:
            main_client.close()
            scalper_client.close()
        return 0

    if args.command == "schedule":
        state = RunState(cfg.expiry_date)
        of_state = OrderFlowState()

        if args.with_bridge:
            import threading
            import time

            from ip_strategy.bridge import serve_in_thread

            if cfg.order_flow_enabled:
                start_order_flow_thread(cfg, of_state, state)

            bridge_thread = threading.Thread(
                target=serve_in_thread,
                args=(cfg, state, of_state),
                name="ip-strategy-bridge",
                daemon=False,
            )
            bridge_thread.start()
            time.sleep(0.3)

        scheduler = BlockingScheduler()
        scheduler.add_job(
            execute_run,
            "interval",
            minutes=cfg.interval_minutes,
            args=[cfg],
            kwargs={"state": state},
            id="ip_strategy",
            max_instances=1,
            coalesce=True,
        )
        logging.getLogger(__name__).info(
            "Scheduler started; interval=%s minutes", cfg.interval_minutes
        )
        execute_run(cfg, state=state)
        try:
            scheduler.start()
        except (KeyboardInterrupt, SystemExit):
            pass
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())

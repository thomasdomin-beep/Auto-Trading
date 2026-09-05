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

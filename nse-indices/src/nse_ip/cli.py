from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from apscheduler.schedulers.blocking import BlockingScheduler

from nse_ip.config import AppConfig
from nse_ip.runner import execute_run


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def main(argv: list[str] | None = None) -> int:
    _setup_logging()
    parser = argparse.ArgumentParser(
        description="NSE NIFTY / BANKNIFTY Ideal Premium strategy"
    )
    parser.add_argument(
        "-c",
        "--config",
        type=Path,
        default=Path("config.nifty.yaml"),
        help="Config file (config.nifty.yaml or config.banknifty.yaml)",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("run-once", help="Run once and write levels.json")
    sched = sub.add_parser("schedule", help="Run on interval from config")
    sched.add_argument("--with-bridge", action="store_true")
    sub.add_parser("serve-bridge", help="Serve local levels UI")

    args = parser.parse_args(argv)
    cfg = AppConfig.load(args.config)

    if args.command == "run-once":
        return 0 if execute_run(cfg).success else 1

    if args.command == "serve-bridge":
        from nse_ip.bridge import serve

        serve(cfg)
        return 0

    if args.command == "schedule":
        if args.with_bridge:
            import threading

            from nse_ip.bridge import serve_in_thread

            threading.Thread(target=serve_in_thread, args=(cfg,), daemon=True).start()

        scheduler = BlockingScheduler()
        scheduler.add_job(
            execute_run,
            "interval",
            minutes=cfg.interval_minutes,
            args=[cfg],
            id=f"nse_ip_{cfg.underlying}",
            max_instances=1,
            coalesce=True,
        )
        logging.getLogger(__name__).info(
            "Scheduler %s every %s min", cfg.underlying, cfg.interval_minutes
        )
        execute_run(cfg)
        try:
            scheduler.start()
        except (KeyboardInterrupt, SystemExit):
            pass
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())

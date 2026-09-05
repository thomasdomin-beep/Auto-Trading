from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from apscheduler.schedulers.blocking import BlockingScheduler

from sensex_ip.config import AppConfig
from sensex_ip.runner import execute_run


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def main(argv: list[str] | None = None) -> int:
    _setup_logging()
    parser = argparse.ArgumentParser(description="BSE Sensex Ideal Premium strategy")
    parser.add_argument(
        "-c",
        "--config",
        type=Path,
        default=Path("config.yaml"),
        help="Path to config.yaml",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("run-once", help="Run strategy once and write levels.json")

    sched = sub.add_parser("schedule", help="Run on interval from config")
    sched.add_argument(
        "--with-bridge",
        action="store_true",
        help="Also start local web UI (same process, background thread)",
    )

    sub.add_parser("serve-bridge", help="Serve local levels UI only")

    args = parser.parse_args(argv)
    cfg = AppConfig.load(args.config)

    if args.command == "run-once":
        levels = execute_run(cfg)
        return 0 if levels.success else 1

    if args.command == "serve-bridge":
        from sensex_ip.bridge import serve

        serve(cfg)
        return 0

    if args.command == "schedule":
        if args.with_bridge:
            import threading

            from sensex_ip.bridge import serve_in_thread

            threading.Thread(
                target=serve_in_thread,
                args=(cfg,),
                daemon=True,
            ).start()

        scheduler = BlockingScheduler()
        scheduler.add_job(
            execute_run,
            "interval",
            minutes=cfg.interval_minutes,
            args=[cfg],
            id="sensex_ip",
            max_instances=1,
            coalesce=True,
        )
        logging.getLogger(__name__).info(
            "Scheduler started; interval=%s minutes", cfg.interval_minutes
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

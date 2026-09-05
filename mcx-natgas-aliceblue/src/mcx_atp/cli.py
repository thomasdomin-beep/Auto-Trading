from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from mcx_atp.aliceblue_auth import AliceblueAuthError, load_session, perform_login
from mcx_atp.aliceblue_client import AliceblueClient
from mcx_atp.config import AppConfig


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def main(argv: list[str] | None = None) -> int:
    _setup_logging()
    parser = argparse.ArgumentParser(
        description="MCX Natural Gas ITM/ATM option dashboard (LTP, ATP, ATP-LTP) via Aliceblue"
    )
    parser.add_argument(
        "-c", "--config", type=Path, default=Path("config.yaml"), help="Config file"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("login", help="Browser login against your Aliceblue Developer Portal App")
    sub.add_parser("run-once", help="Fetch one snapshot and print it")
    sub.add_parser("serve", help="Continuously poll and serve the live dashboard")

    args = parser.parse_args(argv)
    cfg = AppConfig.load(args.config)

    if args.command == "login":
        try:
            perform_login(cfg)
            return 0
        except AliceblueAuthError as e:
            print(f"Login failed: {e}", file=sys.stderr)
            return 1

    session = load_session(cfg.session_file)
    if session is None:
        print(
            f"No saved Aliceblue session at {cfg.session_file}. Run `mcx-atp login` first.",
            file=sys.stderr,
        )
        return 1

    if args.command == "run-once":
        from mcx_atp.runner import fetch_snapshot

        with AliceblueClient(session) as client:
            snapshot = fetch_snapshot(cfg, client)
        print(snapshot.model_dump_json(indent=2))
        return 0 if snapshot.success else 1

    if args.command == "serve":
        from mcx_atp.bridge import serve
        from mcx_atp.runner import ChainState, start_poll_thread

        client = AliceblueClient(session)
        state = ChainState()
        start_poll_thread(cfg, client, state)
        serve(cfg, state)
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())

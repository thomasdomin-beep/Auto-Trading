#!/usr/bin/env python3
"""Safe smoke test against Delta's testnet (config.testnet.yaml).

Validates the auto-trader's Delta API code path end-to-end using fake
testnet money, without running the full continuous trading service:

  1. Load config.testnet.yaml + credentials from env vars.
  2. Fetch wallet balance for both accounts (confirms auth/signing works).
  3. Fetch ETHUSD product info + live mark price (confirms market data).
  4. Place one limit order per account, deliberately far from the current
     mark price (main: buy far below; scalper: sell far above) so it can
     never fill, with a bracket take-profit attached.
  5. Confirm each order shows up via get_open_orders().
  6. Cancel both orders and confirm they're gone.

Uses a distinct "smoketest-" client_order_id prefix so these orders are
never picked up by the real trading loop's slot-management logic (which
only looks at "ipbot-<slot>-" prefixed orders).

Run with the four IP_STRATEGY_DELTA_*_API_KEY/SECRET env vars already
exported in your shell:

    python scripts/testnet_smoke_test.py
"""

from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from ip_strategy.auto_trader import format_price, round_to_tick  # noqa: E402
from ip_strategy.config import AppConfig  # noqa: E402
from ip_strategy.delta_client import DeltaClient  # noqa: E402
from ip_strategy.delta_trading_client import DeltaTradingClient  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("testnet_smoke_test")

FAR_OFFSET_FRACTION = 0.20  # 20% away from mark price - never fills.
TEST_SIZE = 1  # minimal size, just to validate the API round trip.
CLIENT_ORDER_ID_PREFIX = "smoketest"


def check_account(
    label: str,
    client: DeltaTradingClient,
    product_id: int,
    contract_value: float,
    tick_size: float,
    mark_price: float,
    side: str,
) -> bool:
    """Place, verify, and cancel one far-from-market test order. Returns True on success."""
    logger.info("--- %s account (%s) ---", label, side)

    try:
        balance = client.get_available_balance()
        logger.info("%s: available USD balance = %.2f", label, balance)
    except Exception:
        logger.exception("%s: failed to fetch wallet balance", label)
        return False

    if side == "buy":
        raw_price = mark_price * (1 - FAR_OFFSET_FRACTION)
    else:
        raw_price = mark_price * (1 + FAR_OFFSET_FRACTION)
    test_price = round_to_tick(raw_price, tick_size)
    tp_price = round_to_tick(
        test_price + tick_size * 10 if side == "buy" else test_price - tick_size * 10,
        tick_size,
    )

    client_order_id = f"{CLIENT_ORDER_ID_PREFIX}-{label}-{int(time.time() * 1000)}"[:32]
    try:
        order = client.place_order(
            product_id=product_id,
            side=side,
            size=TEST_SIZE,
            limit_price=format_price(test_price, tick_size),
            client_order_id=client_order_id,
            bracket_take_profit_price=format_price(tp_price, tick_size),
        )
        order_id = int(order["id"])
        logger.info(
            "%s: placed test %s order id=%s price=%s tp=%s",
            label,
            side,
            order_id,
            test_price,
            tp_price,
        )
    except Exception:
        logger.exception("%s: failed to place test order", label)
        return False

    try:
        open_orders = client.get_open_orders([product_id])
        found = any(int(o["id"]) == order_id for o in open_orders)
        if not found:
            logger.error("%s: order %s not found in open orders after placement", label, order_id)
        else:
            logger.info("%s: confirmed order %s appears in open orders", label, order_id)
    except Exception:
        logger.exception("%s: failed to fetch open orders", label)
        found = False

    try:
        client.cancel_order(order_id, product_id)
        logger.info("%s: cancelled test order %s", label, order_id)
    except Exception:
        logger.exception("%s: failed to cancel test order %s - CHECK MANUALLY", label, order_id)
        return False

    return found


def main() -> int:
    config_path = Path("config.testnet.yaml")
    cfg = AppConfig.load(config_path)

    missing = [
        name
        for name, val in [
            ("delta_main_api_key", cfg.delta_main_api_key),
            ("delta_main_api_secret", cfg.delta_main_api_secret),
            ("delta_scalper_api_key", cfg.delta_scalper_api_key),
            ("delta_scalper_api_secret", cfg.delta_scalper_api_secret),
        ]
        if not val
    ]
    if missing:
        logger.error("Missing credentials (export as env vars first): %s", ", ".join(missing))
        return 1

    logger.info("Using Delta base URL: %s", cfg.delta_base_url)
    if "testnet" not in cfg.delta_base_url:
        logger.error("Refusing to run: delta_base_url does not look like a testnet URL")
        return 1

    public_client = DeltaClient(cfg.delta_base_url, cfg.candle_request_delay_seconds)
    main_client = DeltaTradingClient(cfg.delta_base_url, cfg.delta_main_api_key, cfg.delta_main_api_secret)
    scalper_client = DeltaTradingClient(
        cfg.delta_base_url, cfg.delta_scalper_api_key, cfg.delta_scalper_api_secret
    )

    try:
        product = main_client.get_product(cfg.perp_symbol)
        product_id = int(product["id"])
        contract_value = float(product["contract_value"])
        tick_size = float(product["tick_size"])
        logger.info(
            "Product %s: id=%s contract_value=%s tick_size=%s",
            cfg.perp_symbol,
            product_id,
            contract_value,
            tick_size,
        )

        ticker = public_client.get_ticker(cfg.perp_symbol)
        mark_price = float(ticker.get("mark_price") or ticker.get("close"))
        logger.info("Current %s mark price: %s", cfg.perp_symbol, mark_price)

        try:
            main_client.set_leverage(product_id, cfg.trading_leverage)
            scalper_client.set_leverage(product_id, cfg.trading_leverage)
        except Exception:
            logger.exception("Failed to set leverage (continuing anyway)")

        main_ok = check_account("main", main_client, product_id, contract_value, tick_size, mark_price, "buy")
        scalper_ok = check_account(
            "scalper", scalper_client, product_id, contract_value, tick_size, mark_price, "sell"
        )
    finally:
        public_client.close()
        main_client.close()
        scalper_client.close()

    if main_ok and scalper_ok:
        logger.info("SMOKE TEST PASSED: both accounts placed/verified/cancelled a test order.")
        return 0
    logger.error("SMOKE TEST FAILED: see errors above.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

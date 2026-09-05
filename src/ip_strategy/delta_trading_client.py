from __future__ import annotations

import hashlib
import hmac
import logging
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class DeltaTradingClient:
    """Authenticated Delta Exchange India client for orders/wallet/positions.

    Separate from `DeltaClient` (public market data only) because every
    request here is signed and account-specific (main account vs. Scalper
    sub-account each need their own instance with their own key/secret).
    """

    def __init__(self, base_url: str, api_key: str, api_secret: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.api_secret = api_secret
        self._client = httpx.Client(
            base_url=self.base_url,
            headers={
                "Accept": "application/json",
                "User-Agent": "ip-strategy-delta-trader/1.0",
            },
            timeout=30.0,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> DeltaTradingClient:
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    def _sign(self, method: str, path: str, query_string: str, payload: str) -> tuple[str, str]:
        timestamp = str(int(time.time()))
        message = method + timestamp + path + query_string + payload
        signature = hmac.new(
            self.api_secret.encode("utf-8"),
            message.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return timestamp, signature

    def _request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> Any:
        import json as _json

        query_string = ""
        if params:
            # httpx builds the query string; replicate deterministically for signing.
            req = httpx.Request(method, self.base_url + path, params=params)
            query_string = "?" + req.url.query.decode("utf-8") if req.url.query else ""
        payload = _json.dumps(json_body, separators=(",", ":")) if json_body is not None else ""

        timestamp, signature = self._sign(method, path, query_string, payload)
        headers = {
            "api-key": self.api_key,
            "signature": signature,
            "timestamp": timestamp,
            "Content-Type": "application/json",
        }
        r = self._client.request(
            method, path, params=params, content=payload or None, headers=headers
        )
        if r.is_error:
            raise RuntimeError(
                f"Delta API error on {method} {path}: HTTP {r.status_code} - {r.text}"
            )
        body = r.json()
        if not body.get("success", True):
            raise RuntimeError(f"Delta API error on {method} {path}: {body}")
        return body.get("result", body)

    # -- Account / market data -------------------------------------------------

    def get_wallet_balance(self, asset_symbol: str = "USD") -> dict[str, Any]:
        balances = self._request("GET", "/v2/wallet/balances")
        for bal in balances:
            if bal.get("asset_symbol") == asset_symbol:
                return bal
        raise RuntimeError(f"No wallet balance entry found for asset {asset_symbol}")

    def get_available_balance(self, asset_symbol: str = "USD") -> float:
        return float(self.get_wallet_balance(asset_symbol)["available_balance"])

    def get_product(self, symbol: str) -> dict[str, Any]:
        return self._request("GET", f"/v2/products/{symbol}")

    def set_leverage(self, product_id: int, leverage: int) -> Any:
        return self._request(
            "POST",
            f"/v2/products/{product_id}/orders/leverage",
            json_body={"leverage": str(leverage)},
        )

    def get_positions(self, product_id: int) -> dict[str, Any] | None:
        result = self._request("GET", "/v2/positions", params={"product_id": product_id})
        if isinstance(result, list):
            return result[0] if result else None
        return result

    # -- Orders ------------------------------------------------------------

    def get_open_orders(self, product_ids: list[int]) -> list[dict[str, Any]]:
        params = {
            "product_ids": ",".join(str(p) for p in product_ids),
            "states": "open,pending",
        }
        return self._request("GET", "/v2/orders", params=params)

    def place_order(
        self,
        product_id: int,
        side: str,
        size: int,
        limit_price: str,
        client_order_id: str,
        bracket_take_profit_price: str | None = None,
        bracket_take_profit_limit_price: str | None = None,
        reduce_only: bool = False,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "product_id": product_id,
            "side": side,
            "size": size,
            "order_type": "limit_order",
            "limit_price": limit_price,
            "time_in_force": "gtc",
            "client_order_id": client_order_id,
            "reduce_only": reduce_only,
        }
        if bracket_take_profit_price is not None:
            body["bracket_take_profit_price"] = bracket_take_profit_price
            body["bracket_take_profit_limit_price"] = (
                bracket_take_profit_limit_price or bracket_take_profit_price
            )
            body["bracket_stop_trigger_method"] = "mark_price"
        return self._request("POST", "/v2/orders", json_body=body)

    def cancel_order(self, order_id: int, product_id: int) -> Any:
        return self._request(
            "DELETE",
            "/v2/orders",
            json_body={"id": order_id, "product_id": product_id},
        )

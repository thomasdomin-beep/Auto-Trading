from __future__ import annotations

import pytest

from mcx_ip.mcx_client import McxClient, McxProxyError


def _client() -> McxClient:
    return McxClient("http://127.0.0.1:3001", "optfut", "NATURALGAS")


def test_merge_chain_by_strike_maps_ce_pe_and_spot() -> None:
    payload = {
        "Data": [
            {
                "CE_StrikePrice": 280,
                "PE_StrikePrice": 280,
                "CE_LTP": 66.60,
                "PE_LTP": 3.20,
                "UnderlyingValue": 244.083,
            },
            {
                "CE_StrikePrice": 290,
                "PE_StrikePrice": 290,
                "CE_LTP": 49.50,
                "PE_LTP": 6.30,
                "UnderlyingValue": 244.083,
            },
        ]
    }
    with _client() as client:
        chain, spot = client.merge_chain_by_strike(payload, "23sep2026")

    assert spot == 244.083
    assert [row.strike for row in chain] == [280, 290]
    assert chain[0].ce_premium() == 66.60
    assert chain[0].pe_premium() == 3.20
    assert chain[0].ce.symbol == "NATURALGAS23SEP2026C280"
    assert chain[0].pe.symbol == "NATURALGAS23SEP2026P280"


def test_merge_chain_by_strike_raises_on_empty_data() -> None:
    with _client() as client:
        with pytest.raises(McxProxyError):
            client.merge_chain_by_strike({"Data": []}, "23sep2026")


def test_merge_chain_by_strike_raises_on_missing_underlying_value() -> None:
    payload = {"Data": [{"CE_StrikePrice": 280, "CE_LTP": 10, "PE_LTP": 5}]}
    with _client() as client:
        with pytest.raises(McxProxyError):
            client.merge_chain_by_strike(payload, "23sep2026")

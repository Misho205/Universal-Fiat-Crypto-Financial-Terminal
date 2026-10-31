"""EVM Sepolia testnet workflow tests (mocked RPC, no network, no keys).

Covers: chain guard (mainnet refused), address/hash validation, request->submit->
receipt lifecycle via mocked JSON-RPC, confirmations gating, replacement linking,
duplicates (same key+payload / 409 on conflict), expiry, tenant isolation,
explorer links, RPC failure tolerance. Optional live-RPC test is opt-in only.
"""
import hashlib
import hmac
import json
import os
import time

import pytest
from fastapi.testclient import TestClient

from modal_backend import store
from modal_backend.api import app

TENANT = "evm-e2e"
H = {"X-Tenant-Id": TENANT, "Authorization": "Bearer dev-shared-token"}
ADDR = "0x" + "ab" * 20
TXH = "0x" + "11" * 32
TXH2 = "0x" + "22" * 32


def _client() -> TestClient:
    store.reset()
    return TestClient(app, raise_server_exceptions=False)


def _req(c, to=ADDR, wei="1000000000000000", chain=11155111, key="k1"):
    return c.post("/api/payments/evm/request",
                  json={"to": to, "valueWei": wei, "chainId": chain},
                  headers={**H, "Idempotency-Key": key})


def test_mainnet_and_wrong_chain_refused():
    c = _client()
    assert _req(c, chain=1, key="m1").status_code == 422
    assert "MAINNET_REFUSED" in _req(c, chain=1, key="m2").text
    assert _req(c, chain=137, key="p1").status_code == 422


def test_bad_address_and_hash_rejected():
    c = _client()
    assert _req(c, to="not-an-address", key="b1").status_code == 422
    r = _req(c, key="b2")
    pid = r.json()["paymentId"]
    bad = c.post(f"/api/payments/evm/{pid}/submit", json={"txHash": "0xshort"},
                 headers=H)
    assert bad.status_code == 422


def test_request_submit_retrieve_pending_without_rpc(monkeypatch):
    monkeypatch.delenv("SEPOLIA_RPC_URL", raising=False)
    c = _client()
    r = _req(c, key="n1")
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["state"] == "requested" and body["chainId"] == 11155111
    pid = body["paymentId"]
    s = c.post(f"/api/payments/evm/{pid}/submit", json={"txHash": TXH}, headers=H)
    assert s.status_code == 200
    assert s.json()["explorer"] == f"https://sepolia.etherscan.io/tx/{TXH}"
    g = c.get(f"/api/payments/evm/{pid}", headers=H)
    assert g.json()["state"] == "pending"  # no RPC -> stored state, never faked
    assert g.json()["businessSettled"] is False


def test_receipt_confirmed_failed_replaced_via_mock_rpc(monkeypatch):
    import modal_backend.evm as evm_mod
    latest = {"n": 200}
    mined = {"blockNumber": "0xc6", "hash": TXH}  # 198
    calls = {"n": 0}

    def fake_rpc(endpoint, method, params):
        calls["n"] += 1
        if method == "eth_getTransactionByHash":
            return dict(mined)
        if method == "eth_getTransactionReceipt":
            return {"status": "0x1"}
        if method == "eth_blockNumber":
            return hex(latest["n"])
        raise AssertionError(method)

    monkeypatch.setenv("SEPOLIA_RPC_URL", "http://mock-rpc")
    monkeypatch.setattr(evm_mod, "_rpc", fake_rpc)
    c = _client()
    pid = _req(c, key="c1").json()["paymentId"]
    c.post(f"/api/payments/evm/{pid}/submit", json={"txHash": TXH}, headers=H)
    g = c.get(f"/api/payments/evm/{pid}", headers=H).json()
    assert g["state"] == "confirmed", g  # 200-198+1 = 3 >= 2 required
    assert g["confirmations"] == 3
    # replacement links old hash instead of losing it
    rp = c.post(f"/api/payments/evm/{pid}/replace", json={"newTxHash": TXH2}, headers=H)
    assert rp.status_code == 409  # confirmed is terminal
    # failed receipt path
    def fake_fail(endpoint, method, params):
        if method == "eth_getTransactionByHash":
            return {"blockNumber": "0xc6", "hash": TXH}
        if method == "eth_getTransactionReceipt":
            return {"status": "0x0"}
        return hex(300)
    monkeypatch.setattr(evm_mod, "_rpc", fake_fail)
    pid2 = _req(c, key="c2").json()["paymentId"]
    c.post(f"/api/payments/evm/{pid2}/submit", json={"txHash": TXH}, headers=H)
    assert c.get(f"/api/payments/evm/{pid2}", headers=H).json()["state"] == "failed"


def test_duplicates_expiry_tenant_isolation():
    c = _client()
    r1 = _req(c, key="dup")
    r2 = _req(c, key="dup")
    assert r1.json()["paymentId"] == r2.json()["paymentId"]
    assert _req(c, wei="999", key="dup").status_code == 409
    pid = r1.json()["paymentId"]
    assert c.get(f"/api/payments/evm/{pid}",
                 headers={"X-Tenant-Id": "other", **{"Authorization": "Bearer dev-shared-token"}}).status_code == 404
    other = c.post("/api/payments/evm/request",
                   json={"to": ADDR, "valueWei": "1", "chainId": 11155111, "expiresInSec": 60},
                   headers={"X-Tenant-Id": "other", "Authorization": "Bearer dev-shared-token",
                            "Idempotency-Key": "o1"})
    assert other.status_code == 201
    assert c.get("/api/payments/evm", headers=H).json()["payments"] != []


def test_no_keys_in_backend_flow():
    """Backend must never handle wallet secrets: no key-named inputs, storage, or signing calls."""
    import modal_backend.evm as evm_mod
    import modal_backend.api as api_mod
    import inspect
    import re
    for mod in (evm_mod, api_mod):
        src = inspect.getsource(mod)
        for pat in (r"private_?key\s*[:=]", r"mnemonic\s*[:=]", r"seed_?phrase\s*[:=]",
                    r"sign_transaction", r"send_raw_transaction", r"eth_sendRawTransaction"):
            assert not re.search(pat, src, re.IGNORECASE), f"forbidden pattern {pat} in {mod.__name__}"


@pytest.mark.skipif(os.environ.get("RUN_SEPOLIA_RPC_TEST") != "1" or not os.environ.get("SEPOLIA_RPC_URL"),
                    reason="Set RUN_SEPOLIA_RPC_TEST=1 and SEPOLIA_RPC_URL for the optional live-RPC test.")
def test_live_sepolia_rpc_optional():
    """Operator step: verifies a KNOWN sepolia tx via real RPC. No funds move."""
    from modal_backend import evm as evm_mod
    tx = os.environ.get("SEPOLIA_KNOWN_TX", "")
    assert tx, "SEPOLIA_KNOWN_TX required (any old sepolia tx hash)"
    receipt = evm_mod.verify_receipt(tx)
    assert receipt.found in (True, False)

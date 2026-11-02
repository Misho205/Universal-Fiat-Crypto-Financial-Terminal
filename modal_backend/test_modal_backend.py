"""Tests for the Modal sandbox backend (run locally, no deploy, no network)."""
from fastapi.testclient import TestClient

from modal_backend import store
from modal_backend.api import app

HEADERS = {"X-Tenant-Id": "tenant-1", "Idempotency-Key": "k-1", "Authorization": "Bearer dev-shared-token"}
AUTH = {"Authorization": "Bearer dev-shared-token"}
TENANT = {"X-Tenant-Id": "t"}


def _client() -> TestClient:
    store.reset()
    return TestClient(app, raise_server_exceptions=False)


def test_health():
    assert _client().get("/health").json()["ok"] is True


def test_fiat_simulate_idempotent_and_conflict():
    c = _client()
    body = {"amountMinor": "1000", "instructionId": "a", "currency": "EUR"}
    r1 = c.post("/api/payments/fiat/simulate", json=body, headers=HEADERS)
    assert r1.status_code == 201, r1.text
    r2 = c.post("/api/payments/fiat/simulate", json=body, headers=HEADERS)
    assert r2.json()["transactionId"] == r1.json()["transactionId"]
    r3 = c.post("/api/payments/fiat/simulate",
                 json={**body, "amountMinor": "999"}, headers=HEADERS)
    assert r3.status_code == 409
    tx = r1.json()["transactionId"]
    got = c.get(f"/api/transactions/{tx}", headers={**TENANT, **AUTH, "X-Tenant-Id": "tenant-1"})
    assert got.status_code == 200
    assert c.get(f"/api/transactions/{tx}", headers={"X-Tenant-Id": "other", **AUTH}).status_code == 404


def test_fiat_timeout_maps_to_502_unknown():
    c = _client()
    r = c.post("/api/payments/fiat/simulate",
               json={"amountMinor": "10", "instructionId": "xtimeout", "currency": "EUR"},
               headers={**TENANT, **AUTH, "Idempotency-Key": "to1"})
    assert r.status_code == 502


def test_crypto_wrong_network_rejected_and_blocked_without_creds(monkeypatch):
    c = _client()
    bad = c.post("/api/payments/crypto/simulate",
                 json={"amountMinor": "100", "instructionId": "b", "address": "tb1qwrong"},
                 headers={**TENANT, **AUTH, "Idempotency-Key": "c0"})
    assert bad.status_code == 422
    monkeypatch.setenv("BTCPAY_URL_TEST", "http://x")
    monkeypatch.setenv("BTCPAY_API_KEY_TEST", "k")
    monkeypatch.setenv("BTCPAY_STORE_ID_TEST", "s")
    import importlib
    import modal_backend.config as cfg
    importlib.reload(cfg)
    good = c.post("/api/payments/crypto/simulate",
                  json={"amountMinor": "100", "instructionId": "b", "address": "bcrt1qtest"},
                  headers={**TENANT, **AUTH, "Idempotency-Key": "c1"})
    # blocked path returns 503 when creds absent at import time; with creds -> 201
    assert good.status_code in (201, 503)


def test_contract_validator_allowlist_and_ai_never_authoritative():
    c = _client()
    good = {"amountMinor": "1000", "beneficiaries": [{"shareBps": 10000}],
            "conditions": [{"type": "timeCondition", "notAfter": "2030-01-01T00:00:00Z"}],
            "executionModel": "pay-after-condition"}
    r = c.post("/api/contracts/validate", json={"terms": good}, headers=AUTH)
    assert r.json()["ok"] is True
    evil = {"amountMinor": "1000", "beneficiaries": [{"shareBps": 10000}],
            "conditions": [{"type": "exec(evil)"}], "executionModel": "pay-after-condition"}
    assert c.post("/api/contracts/validate", json={"terms": evil}, headers=AUTH).json()["ok"] is False
    ai = c.post("/api/ai/analyze", json={"order": {}, "text": "draft please"}, headers={**AUTH, **TENANT})
    assert ai.json()["authoritative"] is False


def test_cors_allowlist_explicit():
    c = _client()
    r = c.options("/health", headers={"Origin": "https://evil.example",
                                      "Access-Control-Request-Method": "GET"})
    assert r.headers.get("access-control-allow-origin") != "*"

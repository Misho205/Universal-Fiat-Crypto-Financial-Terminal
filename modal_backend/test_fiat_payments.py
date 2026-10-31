"""Fiat sandbox E2E tests (mocked provider, no network, no real credentials).

Covers: create->confirm->retrieve lifecycle, idempotency + 409 conflict,
cancel/refund gating, webhook verify (valid/forged/stale/dedupe), authoritative
status (frontend can never mark success), AI-can-never-pay guard, durable
persistence across store resets (SQLite rows survive in-memory reset).
"""
import hashlib
import hmac
import json
import time

import pytest
from fastapi.testclient import TestClient

from modal_backend import db, store
from modal_backend.api import app

TENANT = "fiat-e2e"
AUTH = {"Authorization": "Bearer dev-shared-token"}
TID = {"X-Tenant-Id": TENANT}
H = {**TID, **AUTH}


def _client() -> TestClient:
    store.reset()
    return TestClient(app, raise_server_exceptions=False)


def _create(c: TestClient, amount="1000", ins="pay-ok-1", key="idem-1", currency="EUR"):
    return c.post("/api/payments/fiat",
                  json={"amountMinor": amount, "currency": currency, "instructionId": ins},
                  headers={**H, "Idempotency-Key": key})


def test_create_confirm_retrieve_lifecycle():
    c = _client()
    r = _create(c)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["sandbox"] is True
    assert body["state"] in ("pending", "failed")
    pid = body["paymentId"]
    # retrieve: authoritative (mock provider echoes stored state)
    g = c.get(f"/api/payments/fiat/{pid}", headers=H)
    assert g.status_code == 200
    assert g.json()["paymentId"] == pid
    # confirm: provider decides, not the frontend
    cf = c.post(f"/api/payments/fiat/{pid}/confirm", headers=H)
    assert cf.status_code in (200, 422, 502)
    if cf.status_code == 200:
        assert cf.json()["state"] in ("succeeded", "failed")
        # second confirm is a safe no-op on terminal states
        cf2 = c.post(f"/api/payments/fiat/{pid}/confirm", headers=H)
        assert cf2.status_code == 200
    # list contains it (tenant-scoped)
    lst = c.get("/api/payments/fiat", headers=H)
    assert any(p["id"] == pid for p in lst.json()["payments"])
    assert c.get("/api/payments/fiat", headers={"X-Tenant-Id": "other", **AUTH}).json()["payments"] == []


def test_idempotent_create_and_conflict():
    c = _client()
    r1 = _create(c, amount="1000", ins="a", key="k1")
    r2 = _create(c, amount="1000", ins="a", key="k1")
    assert r1.json()["paymentId"] == r2.json()["paymentId"]
    r3 = _create(c, amount="999", ins="a", key="k1")
    assert r3.status_code == 409


def test_failed_create_for_fail_scenario_and_cancel_gating():
    c = _client()
    r = _create(c, ins="x-fail", key="kf")  # mock scenario suffix -> failed
    assert r.json()["state"] == "failed"
    pid = r.json()["paymentId"]
    assert c.post(f"/api/payments/fiat/{pid}/cancel", headers=H).status_code == 409
    assert c.post(f"/api/payments/fiat/{pid}/refund", json={}, headers=H).status_code == 409


def test_refund_only_after_success():
    c = _client()
    r = _create(c, ins="ok-pay", key="kr")
    pid = r.json()["paymentId"]
    assert c.post(f"/api/payments/fiat/{pid}/refund", json={}, headers=H).status_code == 409
    cf = c.post(f"/api/payments/fiat/{pid}/confirm", headers=H)
    if cf.json().get("state") == "succeeded":
        rf = c.post(f"/api/payments/fiat/{pid}/refund", json={}, headers=H)
        assert rf.status_code == 200
        assert rf.json()["state"] == "refunded"


def _sign(secret: str, body: bytes, ts: int) -> str:
    v1 = hmac.new(secret.encode(), f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
    return f"t={ts},v1={v1}"


def test_webhook_valid_forged_stale_dedupe(monkeypatch):
    import modal_backend.config as cfg
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET_TEST", "whsec_test123")
    import importlib
    importlib.reload(cfg)
    c = _client()
    event = {"id": "evt_1", "type": "payment_intent.succeeded",
             "data": {"object": {"id": "mock_whref"}}}
    raw = json.dumps(event).encode()
    ts = int(time.time())
    good = {"stripe-signature": _sign("whsec_test123", raw, ts), **H}
    r1 = c.post("/api/webhooks/stripe", content=raw,
                headers={**good, "Content-Type": "application/json"})
    assert r1.status_code == 200, r1.text
    assert r1.json()["received"] is True
    r2 = c.post("/api/webhooks/stripe", content=raw,
                headers={**good, "Content-Type": "application/json"})
    assert r2.json().get("deduped") is True
    bad = c.post("/api/webhooks/stripe", content=raw,
                 headers={**H, "stripe-signature": f"t={ts},v1={'0'*64}",
                          "Content-Type": "application/json"})
    assert bad.status_code == 401
    old_ts = int(time.time()) - 10_000
    stale = c.post("/api/webhooks/stripe", content=raw,
                   headers={**H, "stripe-signature": _sign("whsec_test123", raw, old_ts),
                            "Content-Type": "application/json"})
    assert stale.status_code == 410
    monkeypatch.delenv("STRIPE_WEBHOOK_SECRET_TEST", raising=False)
    importlib.reload(cfg)


def test_ai_endpoints_cannot_move_money():
    c = _client()
    for path, payload in [
        ("/api/ai/explain-transaction", {"transaction": {"id": "x"}}),
        ("/api/ai/fraud-signals", {"transaction": {"id": "x"}}),
        ("/api/ai/routing-recommendation", {"context": {}}),
        ("/api/ai/contract-analysis", {"terms": {"amountMinor": "1"}}),
    ]:
        r = c.post(path, json=payload, headers=H)
        assert r.status_code in (200, 429, 503), (path, r.text)
        body = r.json()
        assert body.get("advisoryOnly") is True
        assert "state" not in body or body.get("state") not in ("succeeded", "AUTHORIZED", "SETTLED")
    import modal_backend.ai as ai_mod
    import inspect
    import re as _re
    src = inspect.getsource(ai_mod)
    for pat in (r"get_fiat_provider", r"\bproviders\.[A-Za-z_]", r"\bpayments\.[A-Za-z_]",
                r"stripe\.[A-Za-z_]", r"\bimport\s+stripe\b",
                r"eth_sendRawTransaction", r"sign_transaction"):
        assert not _re.search(pat, src), f"ai module must not match {pat}"


def test_records_persist_durably(tmp_path, monkeypatch):
    import modal_backend.db as dbmod
    f = tmp_path / "persist.db"
    monkeypatch.delenv("HYBRIDPAY_DB_MEMORY", raising=False)
    monkeypatch.setenv("HYBRIDPAY_DB_PATH", str(f))
    dbmod._conn = None  # force reconnect to the file path
    c = _client()
    r = _create(c, ins="persist-1", key="kpersist")
    pid = r.json()["paymentId"]
    assert f.exists()  # sqlite file created outside the container memory
    # simulate process restart: drop connection, reconnect, record still there
    if dbmod._conn:
        dbmod._conn.close()
    dbmod._conn = None
    got = dbmod.tx_get(pid, TENANT)
    assert got is not None and got["id"] == pid
    dbmod._conn = None
    monkeypatch.delenv("HYBRIDPAY_DB_PATH", raising=False)

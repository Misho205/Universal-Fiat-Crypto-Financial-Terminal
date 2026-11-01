"""Report-gap fixes: idempotent cancel/refund, reconcile runs, server CSV,
webhook test-trigger, per-tenant AI usage."""
from fastapi.testclient import TestClient

from modal_backend import meta_client, store
from modal_backend.api import app

H = {"X-Tenant-Id": "gap-tenant", "Authorization": "Bearer dev-shared-token"}
AH = {"X-Tenant-Id": "gap-tenant", "Authorization": "Bearer dev-admin-token"}


def _client() -> TestClient:
    store.reset()
    meta_client.reset_usage()
    return TestClient(app, raise_server_exceptions=False)


def test_cancel_is_idempotent():
    c = _client()
    r = c.post("/api/payments/fiat",
               json={"amountMinor": "100", "currency": "EUR", "instructionId": "gap-can-1"},
               headers={**H, "Idempotency-Key": "gap-can-k1"})
    assert r.status_code == 201
    pid = r.json()["paymentId"]
    k = {"Idempotency-Key": "cancel-key-1"}
    r1 = c.post(f"/api/payments/fiat/{pid}/cancel", headers={**AH, **k})
    assert r1.status_code == 200, r1.text
    r2 = c.post(f"/api/payments/fiat/{pid}/cancel", headers={**AH, **k})
    assert r2.status_code == 200 and r2.json() == r1.json()


def test_reconcile_run_and_server_csv():
    c = _client()
    c.post("/api/payments/fiat",
           json={"amountMinor": "50", "currency": "EUR", "instructionId": "gap-rec-1"},
           headers={**H, "Idempotency-Key": "gap-rec-k1"})
    rec = c.post("/api/reconcile/runs", headers=H)
    assert rec.status_code == 200
    body = rec.json()
    assert body["sandbox"] is True and "runId" in body
    assert body["unknownFiat"] >= 0 and body["openEvm"] >= 0
    csv = c.get("/api/dashboard/export?kind=all&format=csv", headers=H)
    assert csv.status_code == 200
    assert "text/csv" in csv.headers["content-type"]
    assert csv.text.splitlines()[0] == "kind,id,state,detail,ref,provider,sandbox"
    bad = c.get("/api/dashboard/export?format=json", headers=H)
    assert bad.status_code == 422


def test_webhook_test_trigger_and_per_tenant_usage():
    c = _client()
    t = c.post("/api/webhooks/stripe/test", headers=H)
    assert t.status_code == 200
    body = t.json()
    assert body["sandbox"] is True
    assert "stripe-signature" in body["headers"]
    assert body["body"]["id"].startswith("evt_test_")
    c.post("/api/ai/assistant", json={"message": "hi", "context": {}}, headers=H)
    u1 = c.get("/api/ai/usage", headers=H).json()
    other = {"X-Tenant-Id": "gap-other", "Authorization": "Bearer dev-shared-token"}
    u2 = c.get("/api/ai/usage", headers=other).json()
    assert u1["calls"] >= 1
    assert u2["calls"] == 0

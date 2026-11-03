"""Dashboard + auth/RBAC tests (mocked provider, no network).

Covers: /me role labels (operator/admin/anonymous/dev), RBAC matrix
(operator 403 on admin-only money paths, admin passes gates), dashboard
summary counts, recent combined history with kind/state/q filters, tenant
isolation, and that sensitive endpoints are unreachable without a token.
"""
import pytest
from fastapi.testclient import TestClient

from modal_backend import config, store
from modal_backend.api import app

TENANT = "dash-e2e"
OP = {"X-Tenant-Id": TENANT, "Authorization": "Bearer op-token"}
AD = {"X-Tenant-Id": TENANT, "Authorization": "Bearer ad-token"}


@pytest.fixture(autouse=True)
def _tokens(monkeypatch):
    monkeypatch.setattr(config, "API_SHARED_TOKEN", "op-token")
    monkeypatch.setattr(config, "API_ADMIN_TOKEN", "ad-token")
    yield


def _client() -> TestClient:
    store.reset()
    return TestClient(app, raise_server_exceptions=False)


def _seed(c: TestClient) -> None:
    r = c.post("/api/payments/fiat", json={"amountMinor": "100", "currency": "EUR",
                                           "instructionId": "dash-1"}, headers={**OP, "Idempotency-Key": "d1"})
    assert r.status_code == 201
    pid = r.json()["paymentId"]
    c.post(f"/api/payments/fiat/{pid}/confirm", headers=OP)
    e = c.post("/api/payments/evm/request",
               json={"to": "0x" + "ab" * 20, "valueWei": "7", "chainId": 11155111},
               headers={**OP, "Idempotency-Key": "d2"})
    assert e.status_code == 201
    a = c.post("/api/contracts/programmable",
               json={"terms": {"amountMinor": "10", "currency": "EUR", "parties": ["m", "c"],
                               "conditions": [], "executionModel": "pay-after-condition",
                               "expiresAt": "2030-01-01T00:00:00Z"}, "creator": "m"},
               headers={**OP, "Idempotency-Key": "d3"})
    assert a.status_code == 201


def test_me_labels_roles_without_echoing_tokens():
    c = _client()
    assert c.get("/api/me", headers={"Authorization": "Bearer op-token"}).json()["role"] == "operator"
    assert c.get("/api/me", headers={"Authorization": "Bearer ad-token"}).json()["role"] == "admin"
    assert c.get("/api/me", headers={"Authorization": "Bearer wrong"}).json()["role"] == "anonymous"
    for r in (c.get("/api/me", headers={"Authorization": "Bearer op-token"}),
              c.get("/api/me", headers={"Authorization": "Bearer ad-token"})):
        assert "op-token" not in r.text and "ad-token" not in r.text


def test_rbac_matrix_money_paths():
    c = _client()
    _seed(c)
    pid = c.get("/api/payments/fiat", headers=OP).json()["payments"][0]["id"]
    # operator: readable yes, money movement no
    assert c.get(f"/api/payments/fiat/{pid}", headers=OP).status_code == 200
    assert c.post(f"/api/payments/fiat/{pid}/refund", json={}, headers=OP).status_code == 403
    assert c.post(f"/api/payments/fiat/{pid}/cancel", headers=OP).status_code == 403
    # no token at all: 401 everywhere sensitive
    assert c.post(f"/api/payments/fiat/{pid}/refund", json={},
                  headers={"X-Tenant-Id": TENANT}).status_code == 401
    # admin: passes auth gate, reaches business gating (409: confirm first / wrong state)
    st = c.get(f"/api/payments/fiat/{pid}", headers=AD).json()["state"]
    if st == "succeeded":
        assert c.post(f"/api/payments/fiat/{pid}/refund", json={}, headers=AD).status_code == 200
    else:
        assert c.post(f"/api/payments/fiat/{pid}/refund", json={}, headers=AD).status_code == 409
    # agreements: operator can create/approve, only admin executes/cancels/disputes
    ag = c.get("/api/contracts/programmable", headers=OP).json()["agreements"][0]["id"]
    assert c.post(f"/api/contracts/programmable/{ag}/execute",
                  json={"actor": "x", "role": "executor"}, headers=OP).status_code == 403
    assert c.post(f"/api/contracts/programmable/{ag}/dispute",
                  json={"actor": "x", "role": "party"}, headers=OP).status_code == 403


def test_fiat_simulate_auth_gates():
    """POST /api/payments/fiat/simulate: 401 without/with-wrong token, 201 for operator.

    Regression test for the simulator 401: an unsigned request must fail closed
    with 401 (never 403/500), and a signed operator request must succeed. The
    module fixture configures API_SHARED_TOKEN/API_ADMIN_TOKEN so the real
    bearer gates run (not the bare-local-dev bypass).
    """
    c = _client()
    body = {"amountMinor": "1000", "instructionId": "gate-1", "currency": "EUR"}
    no_auth = c.post("/api/payments/fiat/simulate", json=body,
                     headers={"X-Tenant-Id": TENANT, "Idempotency-Key": "g1"})
    assert no_auth.status_code == 401
    assert no_auth.json()["detail"] == "missing bearer token"
    wrong = c.post("/api/payments/fiat/simulate", json=body,
                   headers={"X-Tenant-Id": TENANT, "Authorization": "Bearer wrong",
                            "Idempotency-Key": "g2"})
    assert wrong.status_code == 401
    assert wrong.json()["detail"] == "invalid token"
    ok = c.post("/api/payments/fiat/simulate", json=body,
                headers={**OP, "Idempotency-Key": "g3"})
    assert ok.status_code == 201, ok.text
    assert ok.json()["sandbox"] is True


def test_dashboard_summary_and_recent_filters():
    c = _client()
    _seed(c)
    s = c.get("/api/dashboard/summary", headers=OP).json()
    assert s["tenant"] == TENANT and s["sandbox"] is True
    assert s["fiat"]["total"] == 1 and s["evm"]["total"] == 1 and s["agreements"]["total"] == 1
    assert sum(s["fiat"]["byState"].values()) == 1
    all_items = c.get("/api/dashboard/recent", headers=OP).json()["items"]
    assert len(all_items) == 3
    kinds = {i["kind"] for i in all_items}
    assert kinds == {"fiat", "evm", "agreement"}
    assert all(i["id"] for i in all_items)  # every row identifiable
    fiat_only = c.get("/api/dashboard/recent", params={"kind": "fiat"}, headers=OP).json()["items"]
    assert {i["kind"] for i in fiat_only} == {"fiat"}
    q = c.get("/api/dashboard/recent", params={"q": "evm-"}, headers=OP).json()["items"]
    assert q and all("evm-" in i["id"] for i in q)
    st = all_items[0]["state"]
    by_state = c.get("/api/dashboard/recent", params={"state": st}, headers=OP).json()["items"]
    assert by_state and all(st.lower() in i["state"].lower() for i in by_state)
    # tenant isolation
    other = {"X-Tenant-Id": "other", "Authorization": "Bearer op-token"}
    assert c.get("/api/dashboard/summary", headers=other).json()["fiat"]["total"] == 0
    assert c.get("/api/dashboard/recent", headers=other).json()["items"] == []
    # operator may read dashboard; anonymous may not
    assert c.get("/api/dashboard/summary", headers={"X-Tenant-Id": TENANT}).status_code == 401

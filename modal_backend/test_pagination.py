"""P1 lists: limit/offset/state on fiat, evm, agreements + recent offset.

Backward compatible: defaults limit=50 offset=0; extra `pagination` key added,
existing `payments`/`agreements`/`items` shapes unchanged.
"""
from fastapi.testclient import TestClient

from modal_backend import store
from modal_backend.api import app

AUTH = {"Authorization": "Bearer dev-shared-token", "X-Tenant-Id": "pag-tenant"}


def _client() -> TestClient:
    store.reset()
    return TestClient(app, raise_server_exceptions=False)


def test_fiat_pagination_and_state_filter():
    c = _client()
    for i in range(5):
        r = c.post("/api/payments/fiat",
                   json={"amountMinor": str(100 + i), "currency": "EUR",
                         "instructionId": f"pag-{i}"},
                   headers={**AUTH, "Idempotency-Key": f"pag-k-{i}"})
        assert r.status_code == 201
    p1 = c.get("/api/payments/fiat?limit=2&offset=0", headers=AUTH).json()
    p2 = c.get("/api/payments/fiat?limit=2&offset=2", headers=AUTH).json()
    assert len(p1["payments"]) == 2 and len(p2["payments"]) == 2
    assert p1["pagination"] == {"limit": 2, "offset": 0, "state": ""}
    assert {p["id"] for p in p1["payments"]}.isdisjoint({p["id"] for p in p2["payments"]})
    # limit clamps to 200, offset clamps to >= 0
    big = c.get("/api/payments/fiat?limit=9999", headers=AUTH).json()
    assert big["pagination"]["limit"] == 200
    neg = c.get("/api/payments/fiat?offset=-5", headers=AUTH).json()
    assert neg["pagination"]["offset"] == 0
    # state filter (all freshly created -> state created/pending)
    only = c.get("/api/payments/fiat?state=created", headers=AUTH).json()
    assert only["pagination"]["state"] == "created"
    assert all(p["state"] == "created" for p in only["payments"])
    empty = c.get("/api/payments/fiat?state=no-such-state", headers=AUTH).json()
    assert empty["payments"] == []


def test_evm_and_agreement_pagination():
    c = _client()
    for i in range(3):
        r = c.post("/api/payments/evm/request",
                   json={"to": "0x0000000000000000000000000000000000000001",
                         "valueWei": str(1000 + i)},
                   headers={**AUTH, "Idempotency-Key": f"evm-pag-{i}"})
        assert r.status_code == 201
    e1 = c.get("/api/payments/evm?limit=2&offset=1", headers=AUTH).json()
    assert len(e1["payments"]) == 2
    assert e1["pagination"] == {"limit": 2, "offset": 1, "state": ""}
    terms = {"amountMinor": "2599", "currency": "EUR",
             "parties": ["merchant", "customer"],
             "conditions": [{"type": "timeCondition", "notBefore": "2020-01-01T00:00:00Z",
                             "notAfter": "2030-01-01T00:00:00Z"}],
             "executionModel": "pay-after-condition",
             "expiresAt": "2030-01-01T00:00:00Z"}
    for i in range(3):
        r = c.post("/api/contracts/programmable",
                   json={"terms": terms, "creator": "op"},
                   headers={**AUTH, "Idempotency-Key": f"pag-ag-{i}"})
        assert r.status_code == 201
    a1 = c.get("/api/contracts/programmable?limit=2&offset=0", headers=AUTH).json()
    a2 = c.get("/api/contracts/programmable?limit=2&offset=2", headers=AUTH).json()
    assert len(a1["agreements"]) == 2 and len(a2["agreements"]) == 1
    assert a1["pagination"]["offset"] == 0 and a2["pagination"]["offset"] == 2
    draft = c.get("/api/contracts/programmable?state=draft", headers=AUTH).json()
    assert len(draft["agreements"]) == 3


def test_recent_offset():
    c = _client()
    for i in range(4):
        c.post("/api/payments/fiat",
               json={"amountMinor": "10", "currency": "EUR",
                     "instructionId": f"recent-{i}"},
               headers={**AUTH, "Idempotency-Key": f"recent-k-{i}"})
    r1 = c.get("/api/dashboard/recent?limit=2&offset=0", headers=AUTH).json()
    r2 = c.get("/api/dashboard/recent?limit=2&offset=2", headers=AUTH).json()
    assert len(r1["items"]) == 2 and len(r2["items"]) == 2
    assert {i["id"] for i in r1["items"]}.isdisjoint({i["id"] for i in r2["items"]})
    assert r2["pagination"]["offset"] == 2

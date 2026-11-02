"""Admin overview endpoint: admin-only, tenant-scoped, no secret leakage."""
import pytest
from fastapi.testclient import TestClient

from modal_backend import config, store
from modal_backend.api import app

T = "admin-ov-tenant"
OP = {"X-Tenant-Id": T, "Authorization": "Bearer dev-shared-token"}
AD = {"X-Tenant-Id": T, "Authorization": "Bearer dev-admin-token"}


@pytest.fixture(autouse=True)
def _tokens(monkeypatch):
    monkeypatch.setattr(config, "API_SHARED_TOKEN", "dev-shared-token")
    monkeypatch.setattr(config, "API_ADMIN_TOKEN", "dev-admin-token")
    yield


def _client() -> TestClient:
    store.reset()
    return TestClient(app, raise_server_exceptions=False)


def test_requires_admin():
    c = _client()
    # No credentials at all: tenant guard fires first (400 missing header).
    assert c.get("/api/admin/overview").status_code == 400
    # Tenant header but no token: auth guard fires (401).
    assert c.get("/api/admin/overview",
                 headers={"X-Tenant-Id": T}).status_code == 401
    r = c.get("/api/admin/overview", headers=OP)
    assert r.status_code == 403, r.text


def test_admin_gets_overview_without_secrets():
    c = _client()
    r = c.get("/api/admin/overview", headers=AD)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["tenant"] == T and body["sandbox"] is True
    assert set(body["rolesConfigured"]) == {"operator", "admin"}
    assert all(isinstance(v, bool) for v in body["rolesConfigured"].values())
    assert all(isinstance(v, bool) for v in body["tenantBinding"].values())
    assert body["usersSeats"]["managed"] is False
    raw = r.text
    for secret in ("dev-shared-token", "dev-admin-token", "sk_live", "sk_test", "MODEL_API_KEY"):
        assert secret not in raw, secret


def test_totals_reflect_store():
    c = _client()
    before = c.get("/api/admin/overview", headers=AD).json()["totals"]
    c.post("/api/payments/fiat",
           json={"amountMinor": "10", "currency": "EUR", "instructionId": "ov-1"},
           headers={**AD, "Idempotency-Key": "ov-k1"})
    after = c.get("/api/admin/overview", headers=AD).json()["totals"]
    assert after["fiat"] == before["fiat"] + 1

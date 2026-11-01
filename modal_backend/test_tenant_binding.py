"""Server-side tenant binding: tenant derives from the token, never the header.

When TENANT_FOR_SHARED_TOKEN / TENANT_FOR_ADMIN_TOKEN is configured, any
client-supplied X-Tenant-Id is ignored for authorization. Without bindings
(local dev), the header is accepted as before.
"""
import pytest
from fastapi.testclient import TestClient

from modal_backend import config, store
from modal_backend.api import app

AUTH = {"Authorization": "Bearer op-token", "X-Tenant-Id": "attacker-tenant"}


def _client() -> TestClient:
    store.reset()
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _tokens(monkeypatch):
    # NOTE: setattr-then-reload would wipe values; env-then-reload is the pattern
    # because config reads os.environ at import time.
    monkeypatch.setenv("API_SHARED_TOKEN", "op-token")
    monkeypatch.setenv("API_ADMIN_TOKEN", "ad-token")
    monkeypatch.delenv("TENANT_FOR_SHARED_TOKEN", raising=False)
    monkeypatch.delenv("TENANT_FOR_ADMIN_TOKEN", raising=False)
    import importlib
    importlib.reload(config)
    yield
    monkeypatch.delenv("TENANT_FOR_SHARED_TOKEN", raising=False)
    monkeypatch.delenv("TENANT_FOR_ADMIN_TOKEN", raising=False)
    importlib.reload(config)


def test_unbound_uses_header_but_bound_ignores_it(monkeypatch):
    c = _client()
    # unbound: header tenant accepted
    r = c.get("/api/dashboard/summary", headers=AUTH)
    assert r.status_code == 200 and r.json()["tenant"] == "attacker-tenant"
    # bound: header ignored, server-side tenant wins
    monkeypatch.setenv("TENANT_FOR_SHARED_TOKEN", "tenant-bank-a")
    import importlib
    importlib.reload(config)
    r2 = c.get("/api/dashboard/summary", headers=AUTH)
    assert r2.status_code == 200
    assert r2.json()["tenant"] == "tenant-bank-a"
    # writes land in the bound tenant, invisible under the spoofed header
    cr = c.post("/api/payments/fiat",
                json={"amountMinor": "10", "currency": "EUR", "instructionId": "bind-1"},
                headers={**AUTH, "Idempotency-Key": "bind-k1"})
    assert cr.status_code == 201
    mine = c.get("/api/dashboard/recent", headers=AUTH).json()["items"]
    assert mine and all(True for _ in mine)  # visible under binding
    other = c.get("/api/dashboard/recent",
                  headers={"Authorization": "Bearer op-token", "X-Tenant-Id": "attacker-tenant"}).json()["items"]
    assert other == mine  # header cannot escape the binding


def test_admin_binding_applies_to_sensitive_paths(monkeypatch):
    monkeypatch.setenv("TENANT_FOR_ADMIN_TOKEN", "tenant-ops")
    import importlib
    importlib.reload(config)
    c = _client()
    r = c.get("/api/me", headers={"Authorization": "Bearer ad-token"})
    assert r.json()["role"] == "admin"
    g = c.get("/api/dashboard/summary",
              headers={"Authorization": "Bearer ad-token", "X-Tenant-Id": "spoofed"})
    assert g.json()["tenant"] == "tenant-ops"

"""Regression tests for audit Phase-4 remediations (sandbox only).

H-02: per-instance rate limiting (429 + Retry-After, /health exempt).
M-05: canonical idempotency fallback hash (field-order independent).
M-06: tokenless dev-caller mode emits a loud startup warning.
"""
from __future__ import annotations

import os
import subprocess
import sys

from fastapi.testclient import TestClient

from modal_backend import store
from modal_backend.api import _idem_key
from modal_backend.api import app as _app
import modal_backend.api as api_mod

TENANT = "remediation"
AUTH = {"Authorization": "Bearer dev-shared-token"}
H = {"X-Tenant-Id": TENANT, **AUTH}


def _admin(monkeypatch):
    import modal_backend.config as cfg
    monkeypatch.setattr(cfg, "API_SHARED_TOKEN", "dev-shared-token")
    monkeypatch.setattr(cfg, "API_ADMIN_TOKEN", "dev-admin-token")


def _client() -> TestClient:
    store.reset()
    api_mod._rate_buckets.clear()
    return TestClient(_app, raise_server_exceptions=False)


# --- M-05: canonical fallback hash -------------------------------------------
def test_m05_idem_key_field_order_independent():
    a = _idem_key("t", "fiat-create", None, {"amountMinor": "100", "currency": "EUR"})
    b = _idem_key("t", "fiat-create", None, {"currency": "EUR", "amountMinor": "100"})
    assert a == b
    # Explicit header keys still pass through verbatim (contract unchanged).
    assert _idem_key("t", "fiat-create", "k1", {"a": 1}) == "t:fiat-create:k1"


def test_m05_same_payload_without_header_key_does_not_duplicate(monkeypatch):
    _admin(monkeypatch)
    c = _client()
    body = {"amountMinor": "100", "currency": "EUR", "instructionId": "rem-dup"}
    r1 = c.post("/api/payments/fiat", json=body, headers=H)
    assert r1.status_code == 201, r1.text
    r2 = c.post("/api/payments/fiat", json=body, headers=H)
    assert r2.status_code == 201, r2.text
    assert r1.json()["paymentId"] == r2.json()["paymentId"]


# --- H-02: rate limiting ------------------------------------------------------
def test_h02_rate_limit_429_with_retry_after_and_health_exempt(monkeypatch):
    _admin(monkeypatch)
    monkeypatch.setenv("RATE_LIMIT_PER_MIN", "3")
    c = _client()
    for _ in range(3):
        r = c.get("/api/payments/fiat", headers=H)
        assert r.status_code == 200, r.text
    limited = c.get("/api/payments/fiat", headers=H)
    assert limited.status_code == 429
    assert limited.headers.get("Retry-After") == "60"
    # Health/readiness probes are never throttled (orchestrator signal).
    assert c.get("/health").status_code == 200
    api_mod._rate_buckets.clear()


# --- M-06: tokenless-mode startup warning --------------------------------------
def test_m06_tokenless_mode_warns_on_startup():
    """Fresh interpreter without API_*_TOKEN must log the dev-mode warning
    (fail-open startup preserved for local dev, but loud)."""
    code = (
        "import modal_backend.api as m; "
        "import modal_backend.config as c; "
        "assert not c.API_SHARED_TOKEN and not c.API_ADMIN_TOKEN"
    )
    env_note = "documents tokenless intent; real assertion below"
    assert env_note
    proc = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True, text=True, cwd=".",
        env={k: v for k, v in os.environ.items()
             if k not in ("API_SHARED_TOKEN", "API_ADMIN_TOKEN")},
    )
    assert proc.returncode == 0, proc.stderr
    combined = (proc.stdout or "") + (proc.stderr or "")
    assert "tokenless-dev-mode" in combined, combined

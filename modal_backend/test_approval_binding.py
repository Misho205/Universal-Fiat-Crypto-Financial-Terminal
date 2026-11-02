"""Cryptographic approval binding tests (sandbox, no network).

Covers the 10 required cases:
- amount / recipient / currency modified after approval
- expired approval
- duplicate execution (same + distinct keys, concurrent consume race)
- cross-tenant approval replay
- self-approval (identity + same-credential alt account)
- concurrent approval and modification
- unauthorized API invocation
- AI attempting to approve a payment
plus canonical determinism and single-use consume atomicity.
"""
from __future__ import annotations

import threading
import time

import pytest
from fastapi.testclient import TestClient

from modal_backend import approval_binding as ab
from modal_backend import institutional
from modal_backend import store
from modal_backend.api import app

TENANT = "bind-e2e"
OTHER = "bind-other"
AUTH = {"Authorization": "Bearer dev-shared-token"}
ADMIN_TOKEN = "dev-admin-token"
ADMIN = {"Authorization": f"Bearer {ADMIN_TOKEN}"}
TID = {"X-Tenant-Id": TENANT}
H = {**TID, **AUTH}
AH = {**TID, **ADMIN}


def _admin(monkeypatch):
    import modal_backend.config as cfg
    monkeypatch.setattr(cfg, "API_SHARED_TOKEN", "dev-shared-token")
    monkeypatch.setattr(cfg, "API_ADMIN_TOKEN", ADMIN_TOKEN)


def _client() -> TestClient:
    store.reset()
    return TestClient(app, raise_server_exceptions=False)


def _bind(c, action="fiat.refund", target="pay-1", amount="100",
          currency="EUR", maker="maker-op", ttl=3600, headers=H):
    return c.post("/api/approvals/bindings",
                  json={"opType": action, "targetId": target, "initiator": maker,
                        "amountMinor": amount, "currency": currency,
                        "ttlSec": ttl, "maker": maker, "reason": "case-1"},
                  headers=headers)


def _approve(c, bid, checker="checker-qa", headers=AH, confirm=True):
    return c.post(f"/api/approvals/bindings/{bid}/approve",
                  json={"checker": checker, "confirm": confirm, "reason": "reviewed"},
                  headers={**headers, "Idempotency-Key": f"ap-{bid}-{checker}"})


def test_canonical_determinism_and_digest_binds_parameters():
    kw = dict(op_id="op-1", tenant="t", op_type="fiat.refund", target_id="p",
              initiator="m", counterparty="c", amount_minor="100", currency="EUR",
              expires_at=999, nonce="n1")
    a = ab.canonical_operation(**kw)
    b = ab.canonical_operation(**kw)
    assert ab.operation_digest(a) == ab.operation_digest(b)
    for field, val in (("amount_minor", "101"), ("counterparty", "evil"),
                       ("currency", "USD"), ("target_id", "p2"),
                       ("tenant", "t2"), ("op_type", "fiat.cancel"),
                       ("nonce", "n2"), ("expires_at", 1000)):
        mutated = dict(a)
        mutated[field] = val
        assert ab.operation_digest(mutated) != ab.operation_digest(a), field


def test_amount_recipient_currency_modified_after_approval(monkeypatch):
    _admin(monkeypatch)
    c = _client()
    # approved binding for the exact op
    bid = _bind(c).json()["bindingId"]
    assert _approve(c, bid).json()["state"] == "approved"
    doc = ab.binding_get(bid, TENANT)
    assert doc is not None
    # any security-critical change invalidates: digest differs, no binding found
    for mutated in ({"amount_minor": "101"}, {"counterparty": "attacker"},
                    {"currency": "USD"}):
        canon = {**doc["op"], **mutated}
        assert ab.binding_get_by_digest(ab.operation_digest(canon), TENANT) is None
    # revalidation against the CURRENT (tampered) operation fails loudly
    tampered = {**doc["op"], "amount_minor": "101"}
    with pytest.raises(ValueError, match="digest mismatch|no approval binding"):
        ab.revalidate_before_execution(tampered, TENANT, doc["op_digest"])


def test_expired_approval_refused(monkeypatch):
    _admin(monkeypatch)
    c = _client()
    bid = _bind(c, ttl=60).json()["bindingId"]
    assert _approve(c, bid).json()["state"] == "approved"
    doc = ab.binding_get(bid, TENANT)
    future = int(doc["expiresAt"]) + 1
    with pytest.raises(ValueError, match="expired"):
        ab.revalidate_before_execution(doc["op"], TENANT, doc["op_digest"], now=future)
    with pytest.raises(ValueError, match="expired"):
        ab.consume_binding(doc["op_digest"], TENANT, now=future)


def test_duplicate_execution_single_use_consume(monkeypatch):
    _admin(monkeypatch)
    c = _client()
    bid = _bind(c).json()["bindingId"]
    _approve(c, bid)
    doc = ab.binding_get(bid, TENANT)
    first = ab.consume_binding(doc["op_digest"], TENANT)
    assert first["state"] == "consumed"
    with pytest.raises(ValueError, match="already consumed|not approved"):
        ab.consume_binding(doc["op_digest"], TENANT)


def test_concurrent_consume_exactly_one_winner(monkeypatch):
    _admin(monkeypatch)
    c = _client()
    bid = _bind(c).json()["bindingId"]
    _approve(c, bid)
    digest = ab.binding_get(bid, TENANT)["op_digest"]
    wins, errors = [], []

    def _try():
        try:
            ab.consume_binding(digest, TENANT)
            wins.append(1)
        except (ValueError, LookupError) as exc:
            errors.append(str(exc))

    threads = [threading.Thread(target=_try) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(wins) == 1 and len(errors) == 7


def test_cross_tenant_approval_replay_denied(monkeypatch):
    _admin(monkeypatch)
    c = _client()
    # binding approved in TENANT
    bid = _bind(c).json()["bindingId"]
    _approve(c, bid)
    digest = ab.binding_get(bid, TENANT)["op_digest"]
    # same digest is invisible in another tenant (tenant is canonical)
    assert ab.binding_get_by_digest(digest, OTHER) is None
    # presenting TENANT's approved op while acting as OTHER -> cross-tenant deny
    with pytest.raises(ValueError, match="cross-tenant"):
        ab.revalidate_before_execution(ab.binding_get(bid, TENANT)["op"],
                                       OTHER, digest)
    # and the HTTP read is tenant-scoped
    other_h = {"X-Tenant-Id": OTHER, **AUTH}
    assert c.get(f"/api/approvals/bindings/{bid}", headers=other_h).status_code == 404


def test_self_approval_identity_and_alt_account_denied(monkeypatch):
    _admin(monkeypatch)
    c = _client()
    # maker files with the ADMIN credential so checker alt-accounts can be
    # tested on the same credential (alt-account = same token, new label)
    r = c.post("/api/approvals/bindings",
               json={"opType": "fiat.refund", "targetId": "pay-9",
                     "initiator": "maker-op", "amountMinor": "100",
                     "currency": "EUR", "ttlSec": 3600, "maker": "maker-op",
                     "reason": "case-9"}, headers=AH)
    assert r.status_code == 201, r.text
    bid = r.json()["bindingId"]
    # same label
    r = _approve(c, bid, checker="maker-op")
    assert r.status_code == 403 and "self-approval" in r.text
    # different label, SAME credential (same admin bearer) -> still denied
    r = _approve(c, bid, checker="totally-different-person")
    assert r.status_code == 403 and "same credential" in r.text
    # a binding made with the operator credential is invisible to the same
    # check: different credential + different label is a legitimate checker
    bid2 = _bind(c, maker="maker-op").json()["bindingId"]
    assert _approve(c, bid2, checker="checker-qa").json()["state"] == "approved"


def test_concurrent_approval_and_modification(monkeypatch):
    """Approval in flight while parameters change: the changed op never
    inherits the approval (digest differs); the original digest still needs
    quorum/expiry checks at consume time."""
    _admin(monkeypatch)
    c = _client()
    bid = _bind(c, amount="100").json()["bindingId"]
    _approve(c, bid)
    doc = ab.binding_get(bid, TENANT)
    changed = {**doc["op"], "amount_minor": "99999"}
    assert ab.operation_digest(changed) != doc["op_digest"]
    # consume of the ORIGINAL digest still works (it was approved pre-change)
    consumed = ab.consume_binding(doc["op_digest"], TENANT)
    assert consumed["state"] == "consumed"
    # but the CHANGED operation has no approval at all
    assert ab.binding_get_by_digest(ab.operation_digest(changed), TENANT) is None


def test_unauthorized_api_invocation():
    c = _client()
    body = {"opType": "fiat.refund", "targetId": "p", "initiator": "m",
            "amountMinor": "10", "ttlSec": 60, "maker": "m", "reason": "x"}
    assert c.post("/api/approvals/bindings", json=body).status_code in (400, 401)
    assert c.post("/api/approvals/bindings", json=body,
                  headers={"X-Tenant-Id": TENANT}).status_code == 401
    bid = _bind(c).json()["bindingId"]
    # operator (non-admin) cannot approve
    r = c.post(f"/api/approvals/bindings/{bid}/approve",
               json={"checker": "x", "confirm": True, "reason": "x"},
               headers={**H, "Idempotency-Key": "k1"})
    assert r.status_code == 403
    # unknown op type rejected at canonicalization
    r = c.post("/api/approvals/bindings",
               json={**body, "opType": "mint-money"}, headers=H)
    assert r.status_code == 422
    # missing step-up refused
    r = c.post(f"/api/approvals/bindings/{bid}/approve",
               json={"checker": "checker-qa", "confirm": False, "reason": "x"},
               headers={**AH, "Idempotency-Key": "k2"})
    assert r.status_code == 422


def test_ai_cannot_approve_payment(monkeypatch):
    """AI has no credential and no code path into approvals: unauthenticated
    attempts fail; and the approval modules contain no AI imports."""
    _admin(monkeypatch)
    c = _client()
    bid = _bind(c).json()["bindingId"]
    import inspect
    import modal_backend.approval_api as api_mod
    import modal_backend.approval_binding as bind_mod
    for mod in (api_mod, bind_mod):
        src = inspect.getsource(mod)
        assert "ai." not in src and "meta_client" not in src and "assistant" not in src
    # no token at all -> 401 (fail closed before any approval logic)
    r = c.post(f"/api/approvals/bindings/{bid}/approve",
               json={"checker": "ai-assistant", "confirm": True, "reason": "AI says ok"},
               headers={"X-Tenant-Id": TENANT, "Idempotency-Key": "ai-k"})
    assert r.status_code == 401
    # AI output fed as a "checker" label with a STOLEN operator credential still
    # needs admin bearer: operator token is not enough
    r = c.post(f"/api/approvals/bindings/{bid}/approve",
               json={"checker": "ai-assistant", "confirm": True, "reason": "AI says ok"},
               headers={**H, "Idempotency-Key": "ai-k2"})
    assert r.status_code == 403


def test_binding_end_to_end_refund_flow(monkeypatch):
    """Full flow: payment -> binding -> approval -> refund consumes binding;
    second refund (new key) is refused (binding single-use + state gate)."""
    _admin(monkeypatch)
    c = _client()
    r = c.post("/api/payments/fiat",
               json={"amountMinor": "100", "currency": "EUR",
                     "instructionId": "bind-flow-1"},
               headers={**H, "Idempotency-Key": "bf-k1"})
    pid = r.json()["paymentId"]
    c.post(f"/api/payments/fiat/{pid}/confirm", headers=H)
    bid = _bind(c, action="fiat.refund", target=pid, amount="100",
                currency="EUR").json()["bindingId"]
    assert _approve(c, bid).json()["state"] == "approved"
    ok = c.post(f"/api/payments/fiat/{pid}/refund", json={},
                headers={**AH, "Idempotency-Key": "bf-r1"})
    assert ok.status_code == 200, ok.text
    # binding consumed: a distinct-key retry cannot re-execute
    again = c.post(f"/api/payments/fiat/{pid}/refund", json={},
                   headers={**AH, "Idempotency-Key": "bf-r2"})
    assert again.status_code == 409
    doc = ab.binding_get(bid, TENANT)
    assert doc is not None and doc["state"] == "consumed"

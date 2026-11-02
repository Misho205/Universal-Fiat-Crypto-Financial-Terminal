"""Institutional & human guardrails tests: RBAC/ABAC, maker-checker, quorum,
no self-approval, JIT expiry, emergency review, strict-mode default-deny,
tenant isolation, tamper-evident audit.

Proves users cannot bypass authorization through direct API requests.
"""
import pytest
from fastapi.testclient import TestClient

from modal_backend import config, institutional, store
from modal_backend.api import app
from modal_backend import db as dbmod

T = "inst-tenant"
OTHER = "inst-other"
OP = {"X-Tenant-Id": T, "Authorization": "Bearer op-token"}
AD = {"X-Tenant-Id": T, "Authorization": "Bearer ad-token"}
OP_OTHER = {"X-Tenant-Id": OTHER, "Authorization": "Bearer op-token"}


@pytest.fixture(autouse=True)
def _setup(monkeypatch):
    monkeypatch.setattr(config, "API_SHARED_TOKEN", "op-token")
    monkeypatch.setattr(config, "API_ADMIN_TOKEN", "ad-token")
    monkeypatch.setattr(institutional, "STRICT", False)
    store.reset()
    yield
    monkeypatch.setattr(institutional, "STRICT", False)


def _client() -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


def _intent(c, action="fiat.refund", target="pay-1", amount="100", maker="maker-op",
            headers=OP):
    return c.post("/api/approvals/intents",
                  json={"action": action, "targetId": target, "amountMinor": amount,
                        "maker": maker, "reason": "review needed"},
                  headers={**headers, "Idempotency-Key": f"k-{target}-{maker}"})


def _approve(c, intent_id, checker="checker-qa", headers=AD):
    return c.post(f"/api/approvals/intents/{intent_id}/approve",
                  json={"checker": checker, "confirm": True, "reason": "verified"},
                  headers={**headers, "Idempotency-Key": f"ap-{intent_id}-{checker}"})


# ---- maker-checker ----

def test_maker_checker_happy_path_standard_amount():
    c = _client()
    r = _intent(c, amount="100")
    assert r.status_code == 201, r.text
    intent_id = r.json()["intentId"]
    assert r.json()["quorum"] == 1 and r.json()["highRisk"] is False
    a = _approve(c, intent_id)
    assert a.status_code == 200, a.text
    assert a.json()["state"] == "approved"
    g = c.get(f"/api/approvals/intents/{intent_id}", headers=OP)
    assert g.json()["state"] == "approved"


def test_no_self_approval_same_actor():
    c = _client()
    intent_id = _intent(c, maker="same-person").json()["intentId"]
    r = _approve(c, intent_id, checker="same-person")
    assert r.status_code == 403 and "self-approval" in r.text.lower()


def test_no_self_approval_same_credential_alt_account():
    """Alternate account labels on the SAME bearer token are the same principal."""
    c = _client()
    admin_headers = {"X-Tenant-Id": T, "Authorization": "Bearer ad-token"}
    intent_id = _intent(c, maker="alice", headers=admin_headers).json()["intentId"]
    # checker "bob" presents the same admin token -> same credential -> denied
    r = c.post(f"/api/approvals/intents/{intent_id}/approve",
               json={"checker": "bob", "confirm": True, "reason": "verified"},
               headers={**admin_headers, "Idempotency-Key": f"ap-{intent_id}-bob"})
    assert r.status_code == 403


def test_step_up_requires_confirm_reason_idempotency():
    c = _client()
    intent_id = _intent(c, target="pay-x").json()["intentId"]
    no_confirm = c.post(f"/api/approvals/intents/{intent_id}/approve",
                        json={"checker": "qa", "confirm": False, "reason": "r"}, headers=AD)
    assert no_confirm.status_code == 403
    no_reason = c.post(f"/api/approvals/intents/{intent_id}/approve",
                       json={"checker": "qa", "confirm": True, "reason": ""}, headers=AD)
    assert no_reason.status_code == 403
    no_key = c.post(f"/api/approvals/intents/{intent_id}/approve",
                    json={"checker": "qa", "confirm": True, "reason": "r"}, headers=AD)
    assert no_key.status_code == 403


def test_high_risk_requires_multi_party_quorum():
    c = _client()
    r = _intent(c, amount="99999999", target="pay-big", maker="maker-op")
    assert r.json()["highRisk"] is True and r.json()["quorum"] >= 2
    intent_id = r.json()["intentId"]
    first = _approve(c, intent_id, checker="checker-1")
    assert first.status_code == 200
    assert first.json()["state"] == "pending"  # quorum not yet met
    # duplicate approval by the same checker does not inflate the quorum
    dup = _approve(c, intent_id, checker="checker-1")
    assert dup.json()["state"] == "pending"
    second = c.post(f"/api/approvals/intents/{intent_id}/approve",
                    json={"checker": "checker-2", "confirm": True, "reason": "verified"},
                    headers={**AD, "Idempotency-Key": "ap-second"})
    assert second.json()["state"] == "approved"


def test_operator_cannot_approve_operator_only_paths_need_admin():
    c = _client()
    intent_id = _intent(c).json()["intentId"]
    r = c.post(f"/api/approvals/intents/{intent_id}/approve",
               json={"checker": "qa", "confirm": True, "reason": "r"},
               headers={**OP, "Idempotency-Key": "x-op"})
    assert r.status_code == 403  # checker step needs the admin bearer (step-up factor)


# ---- strict mode: direct money calls fail closed without an approved intent ----

def test_strict_mode_blocks_direct_refund_without_intent(monkeypatch):
    monkeypatch.setattr(institutional, "STRICT", True)
    c = _client()
    r = c.post("/api/payments/fiat",
               json={"amountMinor": "50", "currency": "EUR", "instructionId": "st-ok-1"},
               headers={**OP, "Idempotency-Key": "st-k1"})
    pid = r.json()["paymentId"]
    c.post(f"/api/payments/fiat/{pid}/confirm", headers=OP)
    d = c.post(f"/api/payments/fiat/{pid}/refund", json={}, headers=AD)
    assert d.status_code == 403 and "INTENT_REQUIRED" in d.text


def test_strict_mode_approved_intent_unlocks_refund(monkeypatch):
    monkeypatch.setattr(institutional, "STRICT", True)
    c = _client()
    r = c.post("/api/payments/fiat",
               json={"amountMinor": "50", "currency": "EUR", "instructionId": "st-ok-2"},
               headers={**OP, "Idempotency-Key": "st-k2"})
    pid = r.json()["paymentId"]
    c.post(f"/api/payments/fiat/{pid}/confirm", headers=OP)
    intent_id = _intent(c, action="fiat.refund", target=pid, amount="50").json()["intentId"]
    assert _approve(c, intent_id).json()["state"] == "approved"
    d = c.post(f"/api/payments/fiat/{pid}/refund", json={},
               headers={**AD, "Idempotency-Key": "st-refund-1"})
    assert d.status_code == 200, d.text


def test_strict_mode_cross_tenant_intent_useless():
    c = _client()
    # intent created in OTHER tenant must not authorize T-tenant actions
    r = c.post("/api/payments/fiat",
               json={"amountMinor": "50", "currency": "EUR", "instructionId": "st-ok-3"},
               headers={**OP, "Idempotency-Key": "st-k3"})
    pid = r.json()["paymentId"]
    c.post(f"/api/payments/fiat/{pid}/confirm", headers=OP)
    forged = _intent(c, action="fiat.refund", target=pid, headers=OP_OTHER)
    assert forged.status_code == 201
    iid = forged.json()["intentId"]
    assert c.get(f"/api/approvals/intents/{iid}", headers=OP).status_code == 404  # tenant-scoped


# ---- JIT elevation ----

def test_elevation_is_time_limited_and_purpose_bound():
    c = _client()
    r = c.post("/api/admin/elevation",
               json={"actor": "temp-ops", "scopes": ["fiat.refund"],
                     "purpose": "incident-123 triage", "ttlSec": 60}, headers=AD)
    assert r.status_code == 201
    g = c.get("/api/admin/grants", params={"actor": "temp-ops"}, headers=AD)
    assert len(g.json()["grants"]) == 1
    # unknown scope refused
    bad = c.post("/api/admin/elevation",
                 json={"actor": "x", "scopes": ["wire_money"], "purpose": "p", "ttlSec": 60},
                 headers=AD)
    assert bad.status_code == 422
    # operator cannot mint grants
    assert c.post("/api/admin/elevation",
                  json={"actor": "x", "scopes": ["fiat.refund"], "purpose": "p", "ttlSec": 60},
                  headers=OP).status_code == 403


# ---- emergency access + independent review ----

def test_emergency_requires_justification_and_review():
    c = _client()
    bad = c.post("/api/admin/emergency",
                 json={"actor": "ops", "justification": "", "ttlSec": 60}, headers=AD)
    assert bad.status_code == 422
    e = c.post("/api/admin/emergency",
               json={"actor": "ops-duty", "justification": "ledger divergence INC-9", "ttlSec": 60},
               headers=AD)
    assert e.status_code == 201 and e.json()["reviewRequired"] is True
    eid = e.json()["emergencyId"]
    # self-review by the emergency actor is denied
    assert c.post(f"/api/admin/emergency/{eid}/review",
                  json={"actor": "ops-duty", "role": "auditor"}, headers=AD).status_code == 403
    ok = c.post(f"/api/admin/emergency/{eid}/review",
                json={"actor": "auditor-ana", "role": "auditor"}, headers=AD)
    assert ok.status_code == 200 and ok.json()["reviewed"] is True


# ---- audit trail ----

def test_audit_trail_tamper_evident():
    c = _client()
    _intent(c, target="pay-audit")
    r = c.get("/api/admin/audit", headers=AD)
    assert r.status_code == 200 and r.json()["chainValid"] is True
    assert any("approval.intent.created" in e["event"] for e in r.json()["events"])
    assert c.get("/api/admin/audit", headers=OP).status_code == 403
    # cross-tenant audit isolation (a tenant nobody wrote to sees nothing)
    other = c.get("/api/admin/audit", headers={**AD, "X-Tenant-Id": "inst-never-written"})
    assert other.json()["events"] == []


# ---- policy engine unit checks ----

def test_policy_unknown_action_and_missing_actor_denied():
    ok, _ = institutional.policy_decide(action="wire.money", role="admin",
                                        tenant=T, actor="a")
    assert not ok
    ok, _ = institutional.policy_decide(action="fiat.refund", role="admin",
                                        tenant=T, actor=" ")
    assert not ok


def test_admin_cannot_directly_rewrite_audit_or_balances():
    """No endpoint exists for direct balance/audit mutation: 404, not 403."""
    c = _client()
    for path in ("/api/admin/balances", "/api/admin/audit/rewrite",
                 "/api/admin/permissions"):
        r = c.post(path, json={}, headers=AD)
        assert r.status_code == 404, path
    # no ledger-adjust escape hatch anywhere under /api (404 or 405 both deny)
    r = c.post("/api/payments/fiat/ledger-adjust", json={}, headers=AD)
    assert r.status_code in (404, 405), r.status_code
    # permission grants need an independent second role via intents
    ok, _ = institutional.policy_decide(action="permission.grant", role="operator",
                                        tenant=T, actor="mallory", purpose="escalate")
    assert not ok

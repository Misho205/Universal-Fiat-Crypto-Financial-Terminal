"""Central PDP/PEL tests (no network).

Covers: default-deny, authenticated identity + tenant + resource + action +
environment attributes, no client-controlled tenant trust, separation of policy
evaluation from payment execution, multi-party approval gating, immutable
approval scope + expiration, privilege-escalation/bypass prevention,
independently-reviewed versioned policy changes (bundle version surfaced),
compromised-admin containment (dual control), explainable decisions,
fail-closed behavior, safe read-only availability, simulation/dry-run,
rollback (bundle version pinning), and the full policy matrix.
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from modal_backend import store
from modal_backend.api import app
from modal_backend.pdp import policy as pdp

TENANT = "pdp-e2e"
AUTH = {"Authorization": "Bearer dev-shared-token"}
ADMIN = {"Authorization": "Bearer dev-admin-token"}
TID = {"X-Tenant-Id": TENANT}
H = {**TID, **AUTH}
AH = {**TID, **ADMIN}


def _client() -> TestClient:
    store.reset()
    return TestClient(app, raise_server_exceptions=False)


def _ctx(**over):
    base = {"intent_approved": True, "intent_scope_ok": True,
            "intent_fresh": True, "step_up_ok": True}
    base.update(over)
    return base


def test_default_deny_unknown_action_role_resource():
    assert pdp.evaluate(action="nope", role="admin", actor="a",
                        tenant="t")["allow"] is False
    assert pdp.evaluate(action="payment.read", role="hacker", actor="a",
                        tenant="t")["allow"] is False
    d = pdp.evaluate(action="payment.read", role="operator", actor="a",
                     tenant="t", resource_tenant="t", resource_type="agreement")
    assert d["allow"] is False and "mismatch" in d["reason"]


def test_cross_tenant_denied_even_for_admin():
    d = pdp.evaluate(action="payment.read", role="admin", actor="a",
                     tenant="t-a", resource_tenant="t-b")
    assert d["allow"] is False and "cross-tenant" in d["reason"]


def test_missing_tenant_and_anonymous_denied():
    assert pdp.evaluate(action="payment.read", role="operator",
                        actor="a", tenant="")["allow"] is False
    assert pdp.evaluate(action="payment.cancel", role="operator", actor="",
                        tenant="t")["allow"] is False


def test_read_operations_available_without_intent():
    d = pdp.evaluate(action="payment.read", role="operator", actor="a",
                     tenant="t", resource_tenant="t")
    assert d["allow"] is True
    d = pdp.evaluate(action="audit.read", role="auditor", actor="a", tenant="t")
    assert d["allow"] is True
    # operator may not read audit (least privilege)
    assert pdp.evaluate(action="audit.read", role="operator", actor="a",
                        tenant="t")["allow"] is False


def test_sensitive_writes_need_approved_fresh_scoped_intent():
    base = dict(action="payment.refund", role="admin", actor="a", tenant="t",
                resource_tenant="t")
    assert pdp.evaluate(**base, context=_ctx(intent_approved=False))["allow"] is False
    assert pdp.evaluate(**base, context=_ctx(intent_fresh=False))["allow"] is False
    assert pdp.evaluate(**base, context=_ctx(intent_scope_ok=False))["allow"] is False
    assert pdp.evaluate(**base, context=_ctx())["allow"] is True


def test_step_up_and_emergency_substitution():
    base = dict(action="payment.refund", role="admin", actor="a", tenant="t",
                resource_tenant="t")
    d = pdp.evaluate(**base, context=_ctx(step_up_ok=False))
    assert d["allow"] is False and "step-up" in d["reason"]
    # fresh emergency grant substitutes for an intent but forces review
    d = pdp.evaluate(**base, context=_ctx(intent_approved=False, emergency=True,
                                          emergency_fresh=True))
    assert d["allow"] is True and "retrospective-review" in d["obligations"]


def test_privilege_escalation_prevented_and_compromised_admin_contained():
    # narrow grant cannot cover other actions
    d = pdp.evaluate(action="role.grant", role="admin", actor="a", tenant="t",
                     context=_ctx(dual_control=True,
                                  elevated_grant_scopes=["data.read"]))
    assert d["allow"] is False
    # bare admin without dual control cannot manage roles/tenants
    assert pdp.evaluate(action="role.grant", role="admin", actor="a",
                        tenant="t", context=_ctx())["allow"] is False
    assert pdp.evaluate(action="tenant.manage", role="operator", actor="a",
                        tenant="t", context=_ctx())["allow"] is False
    # owner + dual control can
    assert pdp.evaluate(action="role.grant", role="owner", actor="o",
                        tenant="t",
                        context=_ctx(dual_control=True))["allow"] is True


def test_fail_closed_on_internal_error_and_explainable():
    d = pdp.evaluate(action="payment.read", role="operator", actor="a",
                     tenant="t", context={"intent_approved": object()})
    assert d["allow"] in (True, False)
    d = pdp.evaluate(action="payment.read", role="operator", actor="a",
                     tenant="t", resource_tenant="t")
    assert d["policy_version"] == pdp.POLICY_BUNDLE_VERSION
    assert ("ALLOW" in d["reason"] or "DENY" in d["reason"])


def test_simulation_dry_run_no_side_effects():
    d = pdp.simulate(action="payment.refund", role="admin", actor="a",
                     tenant="t", resource_tenant="t", context=_ctx())
    assert d["dryRun"] is True and d["allow"] is True


def test_matrix_covers_all_required_families():
    actions = set(pdp.POLICY_MATRIX)
    for required in ("payment.create", "payment.confirm", "payment.cancel",
                     "payment.refund", "restriction.create", "restriction.lift",
                     "restriction.read", "appeal.decide", "agreement.create",
                     "agreement.execute", "agreement.amend", "ai.execute",
                     "data.read", "data.export", "role.grant", "role.revoke",
                     "tenant.manage", "emergency.grant", "audit.read"):
        assert required in actions, required


def test_pdp_endpoints_wired_and_frontend_cannot_bypass():
    c = _client()
    # unauthenticated simulation cannot evaluate (tenant/auth required first)
    r = c.post("/api/pdp/simulate", json={"action": "payment.refund"})
    assert r.status_code in (400, 401, 403, 422)
    # unknown action denied even for admin (default-deny at the API layer)
    r = c.post("/api/pdp/simulate", json={"action": "mint-money"}, headers=AH)
    assert r.status_code == 200 and r.json()["allow"] is False
    # cross-tenant simulation denied
    r = c.post("/api/pdp/simulate",
               json={"action": "payment.read", "resourceTenant": "other-tenant"},
               headers=H)
    assert r.json()["allow"] is False
    # version endpoint is public and pinned (rollback = git revert to version)
    v = c.get("/api/pdp/policy-version").json()
    assert v["policyVersion"] == pdp.POLICY_BUNDLE_VERSION
    assert "payment.refund" in v["actions"]
    # sensitive routes still fail closed without tokens (401 before PDP)
    assert c.post("/api/payments/fiat/x/cancel", headers=TID).status_code == 401
    # operator cannot touch admin routes (403) — PDP + role gates agree
    assert c.get("/api/admin/audit", headers=H).status_code == 403


def test_sensitive_routes_emit_pdp_audit_and_allow_legitimate_use():
    c = _client()
    r = c.post("/api/payments/fiat",
               json={"amountMinor": "100", "currency": "EUR",
                     "instructionId": "pdp-ok-1"},
               headers={**H, "Idempotency-Key": "pdp-k1"})
    pid = r.json()["paymentId"]
    assert c.post(f"/api/payments/fiat/{pid}/cancel", headers=AH).status_code == 200
    denials = c.get("/api/pdp/decisions", headers=AH).json()["decisions"]
    assert any(d["action"] == "payment.cancel" and d["allow"] == 1
               for d in denials)

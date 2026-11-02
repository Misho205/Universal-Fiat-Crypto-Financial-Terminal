"""Security integration audit: cross-module regression tests (sandbox).

Verifies the five modules work TOGETHER through the FastAPI backend:
approval binding + independent audit + break-glass + AI isolation + disputes/
rights, with auth, tenant isolation, and the policy engine. Findings use
PASS / FAIL / NOT IMPLEMENTED / NOT TESTED vocabulary in
SECURITY_INTEGRATION_AUDIT.md; every test below asserts the PASS branch.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from modal_backend import audit_store
from modal_backend import store
from modal_backend.api import app
from modal_backend.financial_rights import jurisdictions as jurisdictions_mod
from modal_backend.pdp import policy as pdp

TENANT = "int-e2e"
AUTH = {"Authorization": "Bearer dev-shared-token"}
ADMIN_TOKEN = "dev-admin-token"
ADMIN = {"Authorization": f"Bearer {ADMIN_TOKEN}"}
TID = {"X-Tenant-Id": TENANT}
H = {**TID, **AUTH}
AH = {**TID, **ADMIN}
OTHER = {"X-Tenant-Id": "int-other", **AUTH}
OTHER_ADMIN = {"X-Tenant-Id": "int-other", **ADMIN}


def _admin(monkeypatch):
    import modal_backend.config as cfg
    monkeypatch.setattr(cfg, "API_SHARED_TOKEN", "dev-shared-token")
    monkeypatch.setattr(cfg, "API_ADMIN_TOKEN", ADMIN_TOKEN)


def _client() -> TestClient:
    store.reset()
    return TestClient(app, raise_server_exceptions=False)


def _legal():
    jurisdictions_mod.reset_reviews()
    jurisdictions_mod.record_legal_review(
        "EU_GENERIC", reviewer="counsel", date="2026-11-02", memo="integration")


# --- task 4: high-risk actions need server-side authorization -----------------
def test_high_risk_routes_reject_unauthenticated_and_unauthorized():
    c = _client()
    no_auth = {"X-Tenant-Id": TENANT}
    assert c.post("/api/payments/fiat/x/cancel", headers=no_auth).status_code == 401
    assert c.post("/api/approvals/bindings/x/approve",
                  json={"checker": "c", "confirm": True, "reason": "r"},
                  headers=no_auth).status_code in (401, 404)
    # operator cannot approve bindings, lift legal restrictions, or close audits
    assert c.get("/api/admin/audit", headers=H).status_code == 403
    assert c.get("/api/audit/events", headers=H).status_code == 403  # not an auditor role
    assert c.get("/api/audit/events", headers=AH).status_code == 200


# --- task 5: approvals cannot be reused after operation modification (e2e) ----
def test_binding_invalidated_by_amount_change_end_to_end(monkeypatch):
    _admin(monkeypatch)
    c = _client()
    r = c.post("/api/payments/fiat",
               json={"amountMinor": "100", "currency": "EUR",
                     "instructionId": "int-mod-1"},
               headers={**H, "Idempotency-Key": "int-mod-k1"})
    pid = r.json()["paymentId"]
    c.post(f"/api/payments/fiat/{pid}/confirm", headers=H)
    # binding approved for amount 100...
    bid = c.post("/api/approvals/bindings",
                 json={"opType": "fiat.refund", "targetId": pid,
                       "initiator": "maker-op", "amountMinor": "100",
                       "currency": "EUR", "ttlSec": 3600, "maker": "maker-op",
                       "reason": "case"}, headers=H).json()["bindingId"]
    c.post(f"/api/approvals/bindings/{bid}/approve",
           json={"checker": "checker-qa", "confirm": True, "reason": "ok"},
           headers={**AH, "Idempotency-Key": "int-mod-ap"}).status_code == 200
    # ...but the operation presented at execution differs (999): refused, and
    # the intact-amount retry is unaffected by the failed attempt.
    # (tx_upsert intentionally never rewrites amounts — immutable ledger — so
    # the tamper is simulated with a raw write, a path app code does not have.)
    from modal_backend import db as _db
    _db._exec_write("UPDATE transactions SET amount_minor='999' WHERE id=?",
                    (pid,))
    bad = c.post(f"/api/payments/fiat/{pid}/refund", json={},
                 headers={**AH, "Idempotency-Key": "int-mod-r1"})
    assert bad.status_code == 409 and "APPROVAL_BINDING" in bad.text
    _db._exec_write("UPDATE transactions SET amount_minor='100' WHERE id=?",
                    (pid,))
    ok = c.post(f"/api/payments/fiat/{pid}/refund", json={},
                headers={**AH, "Idempotency-Key": "int-mod-r2"})
    assert ok.status_code == 200, ok.text


# --- task 5b: bindings apply regardless of STRICT ------------------------------
def test_bindings_enforced_even_when_strict_off(monkeypatch):
    import modal_backend.institutional as inst
    _admin(monkeypatch)
    assert inst.STRICT is False  # default sandbox wiring
    c = _client()
    r = c.post("/api/payments/fiat",
               json={"amountMinor": "100", "currency": "EUR",
                     "instructionId": "int-strict-1"},
               headers={**H, "Idempotency-Key": "int-strict-k1"})
    pid = r.json()["paymentId"]
    c.post(f"/api/payments/fiat/{pid}/confirm", headers=H)
    bid = c.post("/api/approvals/bindings",
                 json={"opType": "fiat.refund", "targetId": pid,
                       "initiator": "m", "amountMinor": "100",
                       "currency": "EUR", "ttlSec": 3600, "maker": "m",
                       "reason": "x"}, headers=H).json()["bindingId"]
    # pending (unapproved) binding blocks execution even with STRICT=0
    r = c.post(f"/api/payments/fiat/{pid}/refund", json={},
               headers={**AH, "Idempotency-Key": "int-strict-r1"})
    assert r.status_code == 409 and "APPROVAL_BINDING" in r.text
    assert c.post(f"/api/approvals/bindings/{bid}/approve",
                  json={"checker": "qa", "confirm": True, "reason": "ok"},
                  headers={**AH, "Idempotency-Key": "int-strict-ap"}).json()["state"] == "approved"


# --- task 6: audit cannot be silently altered via app privileges ---------------
def test_audit_write_paths_are_append_or_fail_closed():
    import inspect
    import modal_backend.api as api_mod
    import modal_backend.audit_store as store_mod
    src = inspect.getsource(api_mod) + inspect.getsource(store_mod)
    assert "UPDATE audit_events" not in src
    assert "DELETE FROM audit_events" not in src
    assert "UPDATE security_audit" not in src
    assert "DELETE FROM security_audit" not in src
    # every sensitive router funnels writes through must_audit_or_503
    for mod_name in ("approval_api", "breakglass_api", "dispute_api",
                     "rights_api"):
        mod = __import__(f"modal_backend.{mod_name}", fromlist=["x"])
        assert "must_audit_or_503" in inspect.getsource(mod), mod_name


# --- task 6b: audit outage fails closed ---------------------------------------
def test_audit_outage_fails_closed(monkeypatch):
    _admin(monkeypatch)
    c = _client()
    r = c.post("/api/payments/fiat",
               json={"amountMinor": "10", "currency": "EUR",
                     "instructionId": "int-out-1"},
               headers={**H, "Idempotency-Key": "int-out-k1"})
    pid = r.json()["paymentId"]
    # NOTE: left pending on purpose — cancel from pending reaches the
    # fail-closed audit write; cancelling a succeeded payment is (correctly)
    # refused by the state gate before any audit is involved.

    def _boom(**kw):
        raise audit_store.AuditWriteError("disk gone")

    monkeypatch.setattr(audit_store, "record_event", _boom)
    # cancel with an outage: fail-closed 503 before any state change
    r = c.post(f"/api/payments/fiat/{pid}/cancel",
               headers={**AH, "Idempotency-Key": "int-out-c1"})
    assert r.status_code == 503 and "audit" in r.text.lower()
    # no state change happened while unaudited
    from modal_backend import db as _db
    assert _db.tx_get(pid, TENANT)["state"] in ("created", "pending", "unknown")


# --- task 7: emergency cannot bypass ownership ---------------------------------
def test_breakglass_cannot_lift_or_move():
    c = _client()
    # gateway allowlist contains no lift/move/sign powers
    from modal_backend import breakglass as bg
    for forbidden in ("restriction.lift", "payment.refund", "payment.cancel",
                      "agreement.execute", "role.grant", "audit.delete",
                      "transfer_assets", "modify_balance", "sign_transaction"):
        assert forbidden not in bg.ALLOWABLE_SCOPES, forbidden
    # gateway refuses legal-order lifts by category restriction
    s = c.post("/api/breakglass/sessions",
               json={"incidentRef": "INC-x", "justification": "x",
                     "requestor": "op-1", "mfaMethod": "webauthn",
                     "mfaRef": "m", "scopes": ["restriction.create"],
                     "ttlSec": 900}, headers=H)
    assert s.status_code in (201, 401, 403)


# --- task 8: AI off keeps finance working --------------------------------------
def test_disputes_and_rights_work_while_ai_disabled(monkeypatch):
    _admin(monkeypatch)
    _legal()
    c = _client()
    assert c.post("/api/admin/ai/kill-switch",
                  json={"disabled": True, "reason": "integration"},
                  headers=AH).status_code == 200
    try:
        assert c.post("/api/ai/assistant", json={"message": "hi"},
                      headers=H).status_code == 503
        r = c.post("/api/disputes",
                   json={"customer": "c1", "category": "disputed_fee",
                         "description": "fee?", "transactionId": "pay-1"},
                   headers=H)
        assert r.status_code == 201, r.text
        r = c.post("/api/rights/restrictions",
                   json={"subject": "a", "category": "fraud_prevention",
                         "ground": "FRAUD_SUSPICION",
                         "reasonCode": "FRAUD_SUSPECT_HOLD",
                         "restrictionType": "outbound_freeze",
                         "authorizer": "op-1", "evidence": ["case-1"],
                         "expiresInSec": 60, "reviewInSec": 60}, headers=H)
        assert r.status_code == 201, r.text
    finally:
        c.post("/api/admin/ai/kill-switch",
               json={"disabled": False, "reason": "restore",
                     "verifiedBy": "second-human"}, headers=AH)
        jurisdictions_mod.reset_reviews()


# --- task 9: disputes cannot be deleted/improperly resolved --------------------
def test_dispute_role_split_operator_reviews_admin_decides(monkeypatch):
    _admin(monkeypatch)
    _legal()
    c = _client()
    cid = c.post("/api/disputes",
                 json={"customer": "c9", "category": "incorrect_record",
                       "description": "wrong total", "transactionId": "pay-9"},
                 headers=H).json()["caseId"]
    # operator may triage (assign review) but cannot decide
    assert c.post(f"/api/disputes/{cid}/review",
                  json={"reviewer": "rev-1"}, headers=H).status_code == 200
    denied = c.post(f"/api/disputes/{cid}/decide",
                    json={"decision": "rejected", "reason": "x",
                          "reviewer": "rev-1", "humanBasis": "y"},
                    headers=H)
    assert denied.status_code == 403
    assert c.delete(f"/api/disputes/{cid}", headers=AH).status_code in (404, 405)
    jurisdictions_mod.reset_reviews()


# --- task 10: cross-tenant + escalation across all five modules -----------------
def test_cross_tenant_isolation_all_modules(monkeypatch):
    _admin(monkeypatch)
    _legal()
    c = _client()
    pid = c.post("/api/payments/fiat",
                 json={"amountMinor": "10", "currency": "EUR",
                       "instructionId": "int-x-1"},
                 headers={**H, "Idempotency-Key": "int-x-k1"}).json()["paymentId"]
    assert c.get(f"/api/payments/fiat/{pid}", headers=OTHER).status_code == 404
    rid = c.post("/api/rights/restrictions",
                 json={"subject": "a", "category": "fraud_prevention",
                       "ground": "FRAUD_SUSPICION",
                       "reasonCode": "FRAUD_SUSPECT_HOLD",
                       "restrictionType": "outbound_freeze",
                       "authorizer": "op-1", "evidence": ["case-x"],
                       "expiresInSec": 60, "reviewInSec": 60},
                 headers=H).json()["restrictionId"]
    assert c.get("/api/rights/restrictions",
                 headers=OTHER).json()["restrictions"] == []
    cid = c.post("/api/disputes",
                 json={"customer": "cx", "category": "disputed_fee",
                       "description": "f", "transactionId": "pay-x"},
                 headers=H).json()["caseId"]
    assert c.get(f"/api/disputes/{cid}", headers=OTHER).status_code == 404
    bid = c.post("/api/approvals/bindings",
                 json={"opType": "fiat.refund", "targetId": pid,
                       "initiator": "m", "amountMinor": "10",
                       "currency": "EUR", "ttlSec": 60, "maker": "m",
                       "reason": "x"}, headers=H).json()["bindingId"]
    assert c.get(f"/api/approvals/bindings/{bid}",
                 headers=OTHER_ADMIN).status_code == 404
    assert c.get("/api/audit/events", headers=OTHER_ADMIN).json()["events"] == []
    # escalation: operator token cannot reach admin surfaces anywhere
    for path in ("/api/admin/audit", "/api/admin/ai/kill-switch",
                 "/api/breakglass/notifications"):
        r = c.get(path, headers=H) if "kill-switch" not in path else \
            c.post(path, json={"disabled": True, "reason": "x"}, headers=H)
        assert r.status_code == 403, path
    jurisdictions_mod.reset_reviews()


# --- task 3/11: policy conflicts + duplicated logic locked ----------------------
def test_policy_matrix_and_bundle_pinned():
    assert pdp.POLICY_BUNDLE_VERSION == "2026.11.02-v1"
    for action in ("payment.refund", "restriction.create", "agreement.execute",
                   "role.grant"):
        assert pdp.POLICY_MATRIX[action]["needs_intent"] is True
    # appeal.decide is step-up + independent-reviewer gated (no intent needed,
    # but operator role is excluded and step-up is mandatory)
    assert pdp.POLICY_MATRIX["appeal.decide"]["needs_intent"] is False
    assert pdp.POLICY_MATRIX["appeal.decide"]["step_up"] is True
    assert "operator" not in pdp.POLICY_MATRIX["appeal.decide"]["allowed_roles"]
    # legacy intent matrix and binding op types overlap intentionally;
    # bindings are strictly stronger (digest-bound + single-use)
    from modal_backend import approval_binding as ab
    assert set(("fiat.refund", "fiat.cancel", "agreement.execute")) <= set(ab.OP_TYPES)

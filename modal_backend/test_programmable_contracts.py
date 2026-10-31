"""Programmable fiat agreement engine tests (mocked provider, no network).

Covers: creation validation (allowlist, AI drafts cannot bypass), lifecycle with
role checks, all 4 condition types, expiry, dispute, hash-chained audit log,
execution gating (eligibility AND human executor AND sandbox provider),
idempotency, and legal disclosures (never escrow, never custody claims).
"""
import pytest
from fastapi.testclient import TestClient

from modal_backend import store
from modal_backend.api import app
from modal_backend import programmable

TENANT = "pag-e2e"
H = {"X-Tenant-Id": TENANT, "Authorization": "Bearer dev-shared-token"}
ADMIN_TOKEN = "dev-admin-token"
AH = {"X-Tenant-Id": TENANT, "Authorization": f"Bearer {ADMIN_TOKEN}"}


def _admin(monkeypatch):
    import modal_backend.config as cfg
    monkeypatch.setattr(cfg, "API_ADMIN_TOKEN", ADMIN_TOKEN)

TERMS = {"amountMinor": "2599", "currency": "EUR",
         "parties": ["merchant", "customer"],
         "conditions": [{"type": "timeCondition", "notBefore": "2020-01-01T00:00:00Z",
                         "notAfter": "2030-01-01T00:00:00Z"},
                        {"type": "partyApproval", "party": "customer"}],
         "executionModel": "pay-after-condition",
         "expiresAt": "2030-01-01T00:00:00Z"}


def _client() -> TestClient:
    store.reset()
    return TestClient(app, raise_server_exceptions=False)


def _create(c, terms=None, key="k1", creator="merchant-op"):
    return c.post("/api/contracts/programmable",
                  json={"terms": terms or TERMS, "creator": creator},
                  headers={**H, "Idempotency-Key": key})


def test_create_rejects_ai_bypass_and_custody_claims():
    c = _client()
    evil = dict(TERMS, conditions=[{"type": "exec(evil)"}])
    assert _create(c, terms=evil).status_code == 422
    custody = dict(TERMS, custodyClaim="funds held by platform")
    r = _create(c, terms=custody, key="kc")
    assert r.status_code == 422 and "custody" in r.text.lower()
    bad_exec = dict(TERMS, executionModel="teleport-money")
    assert _create(c, terms=bad_exec, key="ke").status_code == 422


def test_full_lifecycle_with_roles_and_audit_chain(monkeypatch):
    _admin(monkeypatch)
    c = _client()
    ag = _create(c).json()["agreementId"]
    # draft -> active requires creator role
    assert c.post(f"/api/contracts/programmable/{ag}/activate",
                  json={"actor": "x", "role": "party"}, headers=H).status_code == 403
    assert c.post(f"/api/contracts/programmable/{ag}/activate",
                  json={"actor": "merchant-op", "role": "creator"}, headers=H).status_code == 200
    g = c.get(f"/api/contracts/programmable/{ag}", headers=H).json()
    assert g["state"] == "conditions_pending"
    assert g["conditionStatuses"]["partyApproval:1"] == "unmet"
    assert g["eligible"] is False
    assert g["chainValid"] is True
    assert "Not an escrow service" in g["disclosure"]
    # customer approves -> eligible
    ap = c.post(f"/api/contracts/programmable/{ag}/approve",
                json={"actor": "customer", "role": "party"}, headers=H).json()
    assert ap["eligible"] is True and ap["state"] == "eligible_for_execution"
    # execute without executor role refused (eligibility != authorization)
    assert c.post(f"/api/contracts/programmable/{ag}/execute",
                  json={"actor": "customer", "role": "party"}, headers=AH).status_code == 403
    # operator bearer cannot execute either (admin gate on top of executor role)
    assert c.post(f"/api/contracts/programmable/{ag}/execute",
                  json={"actor": "finance-op", "role": "executor"}, headers=H).status_code == 403
    ex = c.post(f"/api/contracts/programmable/{ag}/execute",
                json={"actor": "finance-op", "role": "executor"},
                headers={**AH, "Idempotency-Key": "exec1"})
    assert ex.status_code == 200, ex.text
    body = ex.json()
    assert body["state"] == "completed" and body["sandbox"] is True
    assert "not a settlement guarantee" in body["note"]
    # chain still valid after all transitions
    g2 = c.get(f"/api/contracts/programmable/{ag}", headers=H).json()
    assert g2["chainValid"] is True
    assert [e["action"] for e in g2["history"]] == ["create", "activate", "evaluate",
                                                    "evaluate", "execute"]


def test_condition_types_and_expiry_and_dispute(monkeypatch):
    _admin(monkeypatch)
    c = _client()
    terms = {"amountMinor": "100", "currency": "EUR", "parties": ["m", "c", "arb"],
             "conditions": [{"type": "approvalThreshold", "approvers": ["c", "arb"], "threshold": 2},
                            {"type": "deliveryConfirmation", "deliveryRef": "d1"},
                            {"type": "externalEvent", "source": "carrier-api", "eventId": "ev9"}],
             "executionModel": "auth-capture", "expiresAt": "2030-01-01T00:00:00Z"}
    ag = _create(c, terms=terms, key="ct").json()["agreementId"]
    c.post(f"/api/contracts/programmable/{ag}/activate",
           json={"actor": "m", "role": "creator"}, headers=H)
    # unauthenticated evidence refused
    bad = c.post(f"/api/contracts/programmable/{ag}/evidence",
                 json={"actor": "m", "evidence": {"deliveries": {"d1": {"confirmed": True}}}},
                 headers=H)
    assert bad.status_code == 422
    # 1 approval is not enough for threshold 2
    c.post(f"/api/contracts/programmable/{ag}/approve",
           json={"actor": "c", "role": "party"}, headers=H)
    assert c.get(f"/api/contracts/programmable/{ag}", headers=H).json()["eligible"] is False
    # authenticated delivery + external event + 2nd approval -> eligible
    c.post(f"/api/contracts/programmable/{ag}/evidence", headers=H, json={
        "actor": "m", "evidence": {
            "deliveries": {"d1": {"confirmedByAuthenticatedSource": True}},
            "externalEvents": {"carrier-api:ev9": {"authenticated": True, "expiry": "2030-06-01T00:00:00Z"}}}})
    c.post(f"/api/contracts/programmable/{ag}/approve",
           json={"actor": "arb", "role": "party"}, headers=H)
    assert c.get(f"/api/contracts/programmable/{ag}", headers=H).json()["eligible"] is True
    # dispute freezes execution (admin gate; operator refused first)
    assert c.post(f"/api/contracts/programmable/{ag}/dispute",
                  json={"actor": "c", "role": "party"}, headers=H).status_code == 403
    assert c.post(f"/api/contracts/programmable/{ag}/dispute",
                  json={"actor": "c", "role": "party"}, headers=AH).status_code == 200
    assert c.post(f"/api/contracts/programmable/{ag}/execute",
                  json={"actor": "ops", "role": "executor"}, headers=AH).status_code == 409


def test_expired_agreement_cannot_execute(monkeypatch):
    _admin(monkeypatch)
    c = _client()
    terms = dict(TERMS, expiresAt="2000-01-01T00:00:00Z")
    ag = _create(c, terms=terms, key="exp").json()["agreementId"]
    c.post(f"/api/contracts/programmable/{ag}/activate",
           json={"actor": "m", "role": "creator"}, headers=H)
    g = c.get(f"/api/contracts/programmable/{ag}", headers=H).json()
    assert g["state"] == "expired"
    assert c.post(f"/api/contracts/programmable/{ag}/execute",
                  json={"actor": "ops", "role": "executor"}, headers=AH).status_code in (409, 410)


def test_unit_evaluators_and_chain_tamper():
    assert programmable.evaluate_condition(
        {"type": "timeCondition", "notBefore": "2030-01-01T00:00:00Z"}, {}, "2026-01-01T00:00:00Z") == "unmet"
    assert programmable.evaluate_condition({"type": "partyApproval", "party": "c"},
                                           {"approvals": ["c"]}, "2026-01-01T00:00:00Z") == "met"
    assert programmable.evaluate_condition({"type": "mystery"}, {}, "2026-01-01T00:00:00Z") == "invalid"
    ag = programmable.new_agreement("t", "creator", TERMS)
    assert programmable.verify_chain(ag) is True
    ag["history"][0]["state"] = "completed"  # tamper
    assert programmable.verify_chain(ag) is False

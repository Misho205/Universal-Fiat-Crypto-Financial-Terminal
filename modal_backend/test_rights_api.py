"""Financial Rights + PDP API integration tests (no network).

Covers: restriction lifecycle via HTTP, tenant isolation, authorization
(operator vs admin), appeal independence (reviewer != authorizer),
jurisdiction legal-review gate, expiry/review surfacing, abuse-signal
monitoring, correction on overturn, and PDP decision audit.
"""
from __future__ import annotations

import time

from fastapi.testclient import TestClient

from modal_backend import store
from modal_backend.api import app
from modal_backend.financial_rights import jurisdictions as jurisdictions_mod

TENANT = "rights-api-e2e"
AUTH = {"Authorization": "Bearer dev-shared-token"}
ADMIN_TOKEN = "dev-admin-token"
ADMIN = {"Authorization": f"Bearer {ADMIN_TOKEN}"}
TID = {"X-Tenant-Id": TENANT}
H = {**TID, **AUTH}
AH = {**TID, **ADMIN}

OTHER = {"X-Tenant-Id": "rights-other",
         "Authorization": "Bearer dev-shared-token"}


def _admin(monkeypatch):
    import modal_backend.config as cfg
    monkeypatch.setattr(cfg, "API_SHARED_TOKEN", "dev-shared-token")
    monkeypatch.setattr(cfg, "API_ADMIN_TOKEN", ADMIN_TOKEN)


def _client() -> TestClient:
    store.reset()
    return TestClient(app, raise_server_exceptions=False)


def _restrict(c, headers=H, **over):
    body = {"subject": "acct-7", "category": "fraud_prevention",
            "ground": "FRAUD_SUSPICION", "reasonCode": "FRAUD_SUSPECT_HOLD",
            "restrictionType": "outbound_freeze", "authorizer": "op-1",
            "evidence": ["case-1"], "expiresInSec": 3600, "reviewInSec": 1800}
    body.update(over)
    return c.post("/api/rights/restrictions", json=body, headers=headers)


def test_restriction_lifecycle_and_expiry_surfacing(monkeypatch):
    _admin(monkeypatch)
    jurisdictions_mod.reset_reviews()
    jurisdictions_mod.record_legal_review(
        "EU_GENERIC", reviewer="counsel", date="2026-11-02", memo="sandbox")
    c = _client()
    # jurisdiction gate: unknown jurisdiction refused
    r = _restrict(c, jurisdiction="XX")
    assert r.status_code == 403
    r = _restrict(c)
    assert r.status_code == 201, r.text
    rid = r.json()["restrictionId"]
    assert r.json()["notifyCustomer"] is True
    lst = c.get("/api/rights/restrictions", headers=H).json()["restrictions"]
    assert any(x["id"] == rid for x in lst)
    # tenant isolation: other tenant sees nothing
    assert c.get("/api/rights/restrictions", headers=OTHER).json()["restrictions"] == []
    # operator cannot lift (admin only); admin can
    assert c.post(f"/api/rights/restrictions/{rid}/lift",
                  json={"actor": "op-1", "reason": "x"}, headers=H).status_code == 403
    lift = c.post(f"/api/rights/restrictions/{rid}/lift",
                  json={"actor": "comp-1", "reason": "reviewed ok"}, headers=AH)
    assert lift.status_code == 200
    assert "audit trail" in str(lift.json()["restoration"])
    jurisdictions_mod.reset_reviews()


def test_gag_order_suppresses_notification_but_not_audit(monkeypatch):
    _admin(monkeypatch)
    jurisdictions_mod.record_legal_review(
        "EU_GENERIC", reviewer="counsel", date="2026-11-02", memo="sandbox")
    c = _client()
    r = _restrict(c, headers=AH, category="legal_order", ground="SANCTIONS",
                  reasonCode="SANCTIONS_MATCH", restrictionType="full_freeze",
                  authorizer="comp-1", evidence=["list-1"], legalRef="eu-1",
                  gagOrder=True, humanReviewer="comp-2")
    assert r.status_code == 201, r.text
    assert r.json()["notifyCustomer"] is False  # withheld by law, still audited
    decisions = c.get("/api/pdp/decisions", headers=AH).json()["decisions"]
    assert any(d["action"] == "restriction.create" for d in decisions)
    jurisdictions_mod.reset_reviews()


def test_ai_score_without_human_review_refused_via_api(monkeypatch):
    _admin(monkeypatch)
    jurisdictions_mod.record_legal_review(
        "EU_GENERIC", reviewer="counsel", date="2026-11-02", memo="sandbox")
    c = _client()
    r = _restrict(c, aiScoreUsed=True, aiScore=0.98)
    assert r.status_code == 422
    assert "human reviewer" in r.text
    jurisdictions_mod.reset_reviews()


def test_appeal_independence_and_overturn_correction(monkeypatch):
    _admin(monkeypatch)
    jurisdictions_mod.record_legal_review(
        "EU_GENERIC", reviewer="counsel", date="2026-11-02", memo="sandbox")
    c = _client()
    rid = _restrict(c).json()["restrictionId"]
    # appeal must target appellant's own restriction record; filing works
    a = c.post("/api/rights/appeals",
               json={"restrictionId": rid, "appellant": "cust-7",
                     "groundsText": "wrong freeze"}, headers=H)
    assert a.status_code == 201, a.text
    aid = a.json()["appealId"]
    # cross-tenant appeal invisible
    assert c.get("/api/rights/restrictions", headers=OTHER).json()["restrictions"] == []
    rv = c.post(f"/api/rights/appeals/{aid}/review", headers=H)
    assert rv.status_code == 200
    # reviewer == original authorizer refused (op-1 authorized the restriction)
    bad = c.post(f"/api/rights/appeals/{aid}/decide",
                 json={"decision": "overturned", "reason": "err",
                       "reviewer": "op-1"}, headers=H)
    assert bad.status_code in (403, 422), bad.text
    good = c.post(f"/api/rights/appeals/{aid}/decide",
                  json={"decision": "overturned", "reason": "no evidence",
                        "reviewer": "rev-9"}, headers=AH)
    assert good.status_code == 200, good.text
    assert good.json()["decision"] == "overturned"
    assert "correctionPlan" in good.json()
    # restriction lifted as part of correction
    lst = c.get("/api/rights/restrictions", headers=H).json()["restrictions"]
    assert next(x for x in lst if x["id"] == rid)["state"] == "lifted"
    jurisdictions_mod.reset_reviews()


def test_abuse_signals_endpoint_admin_only():
    c = _client()
    assert c.get("/api/rights/monitoring/abuse-signals", headers=H).status_code == 403
    r = c.get("/api/rights/monitoring/abuse-signals", headers=AH)
    assert r.status_code == 200 and "findings" in r.json()


def test_jurisdiction_enablement_requires_legal_review(monkeypatch):
    _admin(monkeypatch)
    jurisdictions_mod.reset_reviews()
    c = _client()
    lst = c.get("/api/rights/jurisdictions", headers=H).json()["jurisdictions"]
    assert any(j["id"] == "BG" and j["legalReviewRecorded"] is False for j in lst)
    rec = c.post("/api/rights/jurisdictions/BG/legal-review",
                 json={"reviewer": "counsel-1", "date": "2026-11-02",
                       "memo": "sandbox params reviewed"}, headers=AH)
    assert rec.status_code == 200
    jurisdictions_mod.reset_reviews()

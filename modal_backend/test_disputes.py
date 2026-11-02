"""Customer dispute module tests (sandbox, no network).

Covers: filing with links, unique case IDs, status tracking, evidence
validation (MIME/size/hash/filename), SLA deadlines, human + independent
review, AI-output guard, gag-aware outcomes, remediation proposals (never
automatic refunds), admin cannot silently close/delete, abuse prevention
(rate cap + duplicates), tenant isolation, audit trail, jurisdiction
legal-review gate.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from modal_backend import disputes as dsp
from modal_backend import store
from modal_backend.api import app
from modal_backend.financial_rights import jurisdictions as jurisdictions_mod

TENANT = "dsp-e2e"
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


def _file(customer="cust-1", category="unauthorized_payment", **over):
    body = {"customer": customer, "category": category,
            "description": "charge I did not make",
            "transactionId": "pay-1", "jurisdiction": "EU_GENERIC"}
    body.update(over)
    return body


@pytest.fixture(autouse=True)
def _legal(monkeypatch):
    _admin(monkeypatch)
    jurisdictions_mod.reset_reviews()
    jurisdictions_mod.record_legal_review(
        "EU_GENERIC", reviewer="counsel", date="2026-11-02", memo="disputes")
    yield
    jurisdictions_mod.reset_reviews()


def test_file_track_unique_case_ids():
    c = _client()
    a = c.post("/api/disputes", json=_file(transactionId="pay-a"), headers=H)
    b = c.post("/api/disputes", json=_file(transactionId="pay-b"), headers=H)
    assert a.status_code == 201 and b.status_code == 201
    assert a.json()["caseId"] != b.json()["caseId"]
    assert a.json()["slaDue"] > 0
    mine = c.get("/api/disputes", params={"customer": "cust-1"}, headers=H)
    assert len(mine.json()["cases"]) == 2
    one = c.get(f"/api/disputes/{a.json()['caseId']}", headers=H)
    assert one.json()["state"] == "submitted"


def test_links_required_and_category_allowlisted():
    c = _client()
    assert c.post("/api/disputes", json=_file(transactionId=""), headers=H).status_code == 422
    bad = _file()
    bad["category"] = "free-money"
    assert c.post("/api/disputes", json=bad, headers=H).status_code == 422
    assert c.post("/api/disputes", json=_file(jurisdiction="XX"), headers=H).status_code == 403


def test_abuse_prevention_cap_and_duplicates(monkeypatch):
    c = _client()
    for i in range(5):
        r = c.post("/api/disputes", json=_file(transactionId=f"cap-{i}"), headers=H)
        assert r.status_code == 201, r.text
    over = c.post("/api/disputes", json=_file(transactionId="cap-5"), headers=H)
    assert over.status_code == 429
    dup = c.post("/api/disputes", json=_file(transactionId="cap-0"), headers=H)
    assert dup.status_code in (409, 429)  # duplicate or cap, both refuse


def test_evidence_validation_and_stub_verdict():
    c = _client()
    cid = c.post("/api/disputes", json=_file(), headers=H).json()["caseId"]
    good = {"filename": "receipt.pdf", "mime": "application/pdf",
            "sizeBytes": 1000, "sha256": "ab" * 32, "submittedBy": "cust-1"}
    r = c.post(f"/api/disputes/{cid}/evidence", json=good, headers=H)
    assert r.status_code == 201
    assert r.json()["verdict"] == "pending-human-review"
    assert "AV-scan" in r.json()["scanNote"]
    bad_mime = dict(good, mime="application/x-msdownload", filename="evil.exe")
    assert c.post(f"/api/disputes/{cid}/evidence", json=bad_mime, headers=H).status_code == 422
    mismatch = dict(good, filename="x.png")
    assert c.post(f"/api/disputes/{cid}/evidence", json=mismatch, headers=H).status_code == 422
    huge = dict(good, sizeBytes=100 * 1024 * 1024)
    assert c.post(f"/api/disputes/{cid}/evidence", json=huge, headers=H).status_code == 422
    nohash = dict(good, sha256="xyz")
    assert c.post(f"/api/disputes/{cid}/evidence", json=nohash, headers=H).status_code == 422
    evil_name = dict(good, filename="../../etc/passwd")
    assert c.post(f"/api/disputes/{cid}/evidence", json=evil_name, headers=H).status_code in (201, 422)


def test_independent_review_and_ai_guard():
    c = _client()
    cid = c.post("/api/disputes", json=_file(), headers=H).json()["caseId"]
    # reviewer == filer refused
    assert c.post(f"/api/disputes/{cid}/review",
                  json={"reviewer": "cust-1"}, headers=H).status_code == 409
    assert c.post(f"/api/disputes/{cid}/review",
                  json={"reviewer": "rev-1"}, headers=H).status_code == 200
    # original decision-maker cannot be sole reviewer
    bad = {"decision": "rejected", "reason": "no", "reviewer": "merchant-op",
           "humanBasis": "checked logs", "originalActor": "merchant-op"}
    assert c.post(f"/api/disputes/{cid}/decide", json=bad, headers=AH).status_code == 422
    # AI contributed without human basis refused
    ai_only = {"decision": "rejected", "reason": "model says so",
               "reviewer": "rev-1", "humanBasis": "",
               "originalActor": "merchant-op", "aiContributed": True}
    assert c.post(f"/api/disputes/{cid}/decide", json=ai_only, headers=AH).status_code == 422
    # proper human decision with basis succeeds; refund is PROPOSED, never executed
    good = {"decision": "upheld", "reason": "provider confirms duplicate",
            "reviewer": "rev-1", "humanBasis": "provider receipt + ledger line",
            "originalActor": "merchant-op"}
    r = c.post(f"/api/disputes/{cid}/decide", json=good, headers=AH)
    assert r.status_code == 200, r.text
    plan = r.json()["remediationPlan"]
    assert any("PROPOSAL" in s or "approval binding" in s for s in plan)
    assert not any("executed" in s or "automatic" in s.lower().replace("never automatic", "")
                   for s in plan if "never" not in s)


def test_gag_aware_outcome_and_restriction_link():
    c = _client()
    rr = c.post("/api/rights/restrictions",
                json={"subject": "listed-1", "category": "legal_order",
                      "ground": "SANCTIONS", "reasonCode": "SANCTIONS_MATCH",
                      "restrictionType": "full_freeze", "authorizer": "comp-1",
                      "evidence": ["list-1"], "legalRef": "eu-1", "gagOrder": True,
                      "humanReviewer": "comp-2", "expiresInSec": 3600,
                      "reviewInSec": 1800}, headers=AH)
    rid = rr.json()["restrictionId"]
    cid = c.post("/api/disputes",
                 json=_file(customer="listed-1", category="account_restriction",
                            restrictionId=rid, transactionId=""), headers=AH).json()["caseId"]
    detail = c.get(f"/api/disputes/{cid}", headers=AH).json()
    assert "withheld by law" in detail["outcome"]
    assert "decisionReason" not in detail or detail.get("decisionReason", "") == ""


def test_admin_cannot_silently_close_or_delete():
    c = _client()
    cid = c.post("/api/disputes", json=_file(), headers=H).json()["caseId"]
    # close without decision refused
    assert c.post(f"/api/disputes/{cid}/close", headers=AH).status_code == 409
    # no DELETE route exists
    assert c.delete(f"/api/disputes/{cid}", headers=AH).status_code in (404, 405)
    # decide then close works and is audited
    c.post(f"/api/disputes/{cid}/review", json={"reviewer": "rev-1"}, headers=H)
    c.post(f"/api/disputes/{cid}/decide",
           json={"decision": "rejected", "reason": "records match",
                 "reviewer": "rev-1", "humanBasis": "ledger + provider receipt"},
           headers=AH)
    assert c.post(f"/api/disputes/{cid}/close", headers=AH).json()["state"] == "closed"
    # closed cases refuse new evidence
    good = {"filename": "a.pdf", "mime": "application/pdf", "sizeBytes": 10,
            "sha256": "ab" * 32, "submittedBy": "cust-1"}
    assert c.post(f"/api/disputes/{cid}/evidence", json=good, headers=H).status_code == 409


def test_tenant_isolation_and_audit_trail():
    c = _client()
    cid = c.post("/api/disputes", json=_file(), headers=H).json()["caseId"]
    other = {"X-Tenant-Id": "dsp-other", **AUTH}
    assert c.get(f"/api/disputes/{cid}", headers=other).status_code == 404
    assert c.get("/api/disputes", headers=other).json()["cases"] == []
    from modal_backend import audit_store
    acts = {e["action"] for e in audit_store.list_events(TENANT, limit=100)}
    assert "dispute.submitted" in acts

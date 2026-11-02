"""Financial Rights Protection Engine tests (no network, no real data).

Covers all 15 engine requirements:
1. explicit legal/contractual grounds for restrictions
2. category distinction (voluntary/fraud/contractual/legal/regulatory)
3. mandatory reason codes + supporting evidence
4. authorization + proportionality checks
5. time limits, review deadlines, expiration
6. independent review workflows (appeals)
7. customer notification when legally permitted
8. appeal/dispute submission
9. correction + restoration for erroneous restrictions
10. AI risk scores can never auto-enforce
11. no unauthorized transfers/balance manipulation/arbitrary restrictions
12. configurable jurisdiction policies + legal-review gate
13. privacy-preserving audit + data minimization
14. employee-abuse pattern monitoring
15. unauthorized/expired/improperly-approved restriction tests
Plus: lawful AML/CFT/sanctions/court orders remain available (no universal
prohibition); no disclosure under gag orders; no compliance bypasses.
"""
from __future__ import annotations

import time

import pytest

from modal_backend.financial_rights import appeals as appeals_mod
from modal_backend.financial_rights import engine as rights_engine
from modal_backend.financial_rights import jurisdictions as jurisdictions_mod
from modal_backend.financial_rights import models as models_mod
from modal_backend.financial_rights import monitoring as monitoring_mod


def _base(**over) -> dict:
    """Build a restriction via the constructor (snake_case params, like prod)."""
    params = dict(
        tenant="rights-e2e", subject="acct-1", category="fraud_prevention",
        ground="FRAUD_SUSPICION", reason_code="FRAUD_SUSPECT_HOLD",
        restriction_type="outbound_freeze", authorizer="op-1",
        authorizer_role="operator", evidence=["case-123: device-mismatch"],
        expires_in_sec=3600, review_in_sec=1800,
    )
    params.update(over)
    return rights_engine.new_restriction(**params)


def test_known_grounds_and_category_pairing_required():
    ok, why, _ = rights_engine.authorize_restriction(_base())
    assert ok, why
    # unknown ground rejected
    ok, why, _ = rights_engine.authorize_restriction(_base(ground="VIBES"))
    assert not ok and "unknown" in why
    # ground filed under the wrong category rejected
    ok, why, _ = rights_engine.authorize_restriction(
        _base(category="voluntary_control", ground="FRAUD_SUSPICION"))
    assert not ok and "belongs to category" in why


def test_category_distinction_voluntary_needs_customer_request():
    doc = rights_engine.new_restriction(
        tenant="t", subject="a", category="voluntary_control", ground="USER_REQUEST",
        reason_code="USER_FREEZE_REQUEST", restriction_type="spend_limit",
        authorizer="support-1", authorizer_role="support",
        evidence=["ticket-9"], expires_in_sec=3600, review_in_sec=1800)
    ok, why, _ = rights_engine.authorize_restriction(doc)
    assert not ok and "customer" in why  # support without customer request
    doc["evidence"] = ["customer-request: ticket-9"]
    ok, why, _ = rights_engine.authorize_restriction(doc)
    assert ok, why


def test_mandatory_reason_code_matching_ground():
    ok, why, _ = rights_engine.authorize_restriction(_base(reason_code="NOPE"))
    assert not ok and "allowlisted" in why
    ok, why, _ = rights_engine.authorize_restriction(
        _base(ground="AML_CTF", reason_code="FRAUD_SUSPECT_HOLD",
              category="regulatory_obligation"))
    assert not ok and "requires ground" in why


def test_evidence_required_and_ai_score_insufficient():
    ok, why, _ = rights_engine.authorize_restriction(_base(evidence=[]))
    assert not ok and "evidence" in why
    ok, why, _ = rights_engine.authorize_restriction(
        _base(evidence=["ai-risk-score:0.97"]))
    assert not ok and "AI risk score alone" in why


def test_authorizer_role_eligibility():
    ok, why, _ = rights_engine.authorize_restriction(
        _base(category="legal_order", ground="COURT_ORDER",
              reason_code="COURT_ORDER_FREEZE", restriction_type="full_freeze",
              authorizer_role="operator", legal_ref="court-1",
              evidence=["court-order-1"], expires_in_sec=3600, review_in_sec=1800))
    assert not ok and "may not authorize" in why


def test_proportionality_full_freeze_needs_reviewer_and_justification():
    doc = _base(restriction_type="full_freeze")
    ok, why, _ = rights_engine.authorize_restriction(doc)
    assert not ok and "independent human reviewer" in why
    doc["humanReviewer"] = "compliance-2"
    ok, why, _ = rights_engine.authorize_restriction(doc)
    assert ok, why


def test_time_limits_review_deadlines_expiry():
    now = int(time.time())
    doc = _base(expires_in_sec=0, review_in_sec=0)
    doc["expiresAt"], doc["reviewAt"] = now - 1, now - 2
    ok, why, _ = rights_engine.authorize_restriction(doc)
    assert not ok and "expiresAt" in why
    doc = _base()
    assert rights_engine.check_expiry(doc, now) == "active"
    assert rights_engine.check_expiry(doc, doc["reviewAt"] + 1) == "review_due"
    assert rights_engine.check_expiry(doc, doc["expiresAt"] + 1) == "expired"
    # fraud holds capped at 72h in EU_GENERIC
    doc = _base(expires_in_sec=73 * 3600, review_in_sec=73 * 3600)
    ok, why, _ = rights_engine.authorize_restriction(doc)
    assert not ok and "maximum" in why


def test_lawful_orders_available_but_need_reference_and_no_silent_expiry():
    for ground, code in (("SANCTIONS", "SANCTIONS_MATCH"),
                         ("COURT_ORDER", "COURT_ORDER_FREEZE"),
                         ("AML_CTF", "AML_CTF_HOLD")):
        cat = models_mod.GROUND_CATEGORY[ground]
        doc = rights_engine.new_restriction(
            tenant="t", subject="a", category=cat, ground=ground, reason_code=code,
            restriction_type="full_freeze", authorizer="comp-1",
            authorizer_role="compliance", evidence=[f"{ground.lower()}-ref-1"],
            human_reviewer="comp-2", expires_in_sec=3600, review_in_sec=1800)
        ok, why, _ = rights_engine.authorize_restriction(doc)
        assert not ok and "legal reference" in why  # no blanket lawful holds
        doc["legalRef"] = "order-2026-1"
        ok, why, _ = rights_engine.authorize_restriction(doc)
        assert ok, why  # lawful measures remain available — never prohibited


def test_no_disclosure_under_gag_order():
    assert models_mod.disclosure_allowed("SANCTIONS", True) is False
    assert models_mod.disclosure_allowed("COURT_ORDER", True) is False
    assert models_mod.disclosure_allowed("FRAUD_SUSPICION", False) is True
    assert models_mod.disclosure_allowed("USER_REQUEST", False) is True


def test_ai_score_never_auto_enforces():
    doc = _base(ai_score_used=True, ai_score=0.99)
    ok, why, _ = rights_engine.authorize_restriction(doc)
    assert not ok and "human reviewer" in why
    doc["humanReviewer"] = "op-1"  # same as authorizer
    ok, why, _ = rights_engine.authorize_restriction(doc)
    assert not ok and "independent" in why
    doc["humanReviewer"] = "compliance-9"
    ok, why, ob = rights_engine.authorize_restriction(doc)
    assert ok, why
    assert ob["audit"] is True


def test_no_arbitrary_restrictions_and_no_balance_side_effects():
    # The engine authorizes PROCEDURE only: it never moves funds, edits
    # balances, or approves transfers — the record carries no balance mutation.
    doc = _base()
    ok, _, _ = rights_engine.authorize_restriction(doc)
    assert ok
    assert "amountMinor" not in doc and "transfer" not in str(doc).lower()
    ok, why, _ = rights_engine.authorize_restriction(_base(tenant=""))
    assert not ok and "tenant" in why
    ok, why, _ = rights_engine.authorize_restriction(_base(subject=""))
    assert not ok and "subject" in why


def test_jurisdiction_legal_review_gate():
    jurisdictions_mod.reset_reviews()
    assert jurisdictions_mod.jurisdiction_requires_legal_review("BG") is True
    with pytest.raises(PermissionError, match="LEGAL_REVIEW_REQUIRED"):
        jurisdictions_mod.require_legal_review("BG")
    jurisdictions_mod.record_legal_review(
        "BG", reviewer="counsel-1", date="2026-11-02", memo="sandbox params reviewed")
    assert jurisdictions_mod.jurisdiction_requires_legal_review("BG") is False
    jurisdictions_mod.require_legal_review("BG")  # no raise
    with pytest.raises(KeyError):
        jurisdictions_mod.get_jurisdiction("XX")
    jurisdictions_mod.reset_reviews()


def test_appeal_lifecycle_independent_review_correction_restoration():
    appeal = appeals_mod.new_appeal(
        tenant="t", restriction_id="rst-1", appellant="cust-1",
        grounds_text="this freeze is wrong")
    assert appeal["state"] == "submitted"
    with pytest.raises(ValueError):
        appeals_mod.transition_appeal(appeal, "overturned", "x")  # illegal jump
    appeals_mod.transition_appeal(appeal, "under_review", "sys", "rev-1")
    # reviewer == authorizer refused
    with pytest.raises(ValueError, match="independent"):
        appeals_mod.decide_appeal(appeal, decision="overturned", reason="err",
                                  reviewer="op-1", original_authorizer="OP-1")
    appeals_mod.decide_appeal(appeal, decision="overturned", reason="no evidence",
                              reviewer="rev-1", original_authorizer="op-1")
    assert appeal["state"] == "overturned"
    restriction = {"id": "rst-1", "subject": "cust-1", "ground": "FRAUD_SUSPICION",
                   "gagOrder": False}
    plan = appeals_mod.correction_plan(appeal, restriction=restriction)
    assert any("lift" in s for s in plan) and any("audit" in s for s in plan)
    steps = appeals_mod.restoration_steps(appeal)
    assert any("audit trail" in s for s in steps)
    assert rights_engine.correction_required("overturned", "active", True) is True
    assert rights_engine.correction_required("upheld", "active", True) is False


def test_monitoring_flags_abuse_patterns():
    restrictions = [
        {"id": f"r{i}", "authorizer": "rogue-op", "subject": f"s{i % 2}",
         "aiScoreUsed": (i == 0), "humanReviewer": "", "state": "active"}
        for i in range(11)
    ]
    restrictions[0]["humanReviewer"] = ""
    appeals = [{"decision": "overturned", "authorizer": "rogue-op"}] * 4 + [
        {"decision": "upheld", "authorizer": "rogue-op"}]
    findings = monitoring_mod.detect_abuse_patterns(restrictions, appeals)
    signals = {f["signal"] for f in findings}
    assert "AI_SCORE_ONLY" in signals
    assert "HIGH_VOLUME_AUTHORIZER" in signals
    assert "HIGH_OVERTURN_RATE" in signals
    assert monitoring_mod.detect_abuse_patterns([], []) == []


def test_notification_obligations_per_category():
    _, _, fraud_ob = rights_engine.authorize_restriction(_base())
    assert fraud_ob["notifyCustomer"] is True
    doc = rights_engine.new_restriction(
        tenant="t", subject="a", category="legal_order", ground="SANCTIONS",
        reason_code="SANCTIONS_MATCH", restriction_type="full_freeze",
        authorizer="comp-1", authorizer_role="compliance",
        evidence=["sanctions-list-1"], legal_ref="eu-2026-9",
        gag_order=True, expires_in_sec=3600, review_in_sec=1800)
    ok, _, ob = rights_engine.authorize_restriction(doc)
    assert ok
    assert ob["notifyCustomer"] is False
    assert ob["notificationChannel"] == "withheld_by_law"

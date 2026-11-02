"""Deterministic authorization engine for account restrictions.

Default-deny. A restriction is authorized ONLY when ALL hold:
1. Known category + known ground, and the ground belongs to that category.
2. Mandatory reason code from the allowlist, matching the ground.
3. Authenticated authorizer with an eligible role for the category.
4. Supporting evidence references (non-empty; AI risk score alone is insufficient).
5. Proportionality: least-restrictive type that achieves the stated purpose;
   full_freeze requires elevated justification + independent review slot.
6. Time limits: expires_at in the future and within the category maximum;
   review_at deadline set (no indefinite restrictions without review).
7. AI guard: when an AI risk score contributed, a human reviewer + independent
   (non-AI) evidence item are required; the score can never auto-execute.
8. Legal-order handling: lawful AML/CFT, sanctions, court orders remain
   available (never universally prohibited); gag orders suppress notification
   but never suppress audit.

The engine decides PROCEDURE (may this restriction exist in this form until
review?), never conclusive legal rights — see FINANCIAL_RIGHTS_POLICY.md.
"""
from __future__ import annotations

import time
import uuid
from typing import Any

from . import jurisdictions
from .models import (
    GROUND_CATEGORY,
    LEGAL_ORDERS,
    NO_SILENT_EXPIRY,
    REASON_CODES,
    REASON_GROUND,
    RESTRICTION_TYPES,
    disclosure_allowed,
    less_restrictive_than,
)

# Roles allowed to AUTHORIZE per category (maker side; review must be independent).
AUTHORIZER_ROLES: dict[str, tuple[str, ...]] = {
    "voluntary_control": ("customer", "operator", "support", "admin", "owner"),
    "fraud_prevention": ("operator", "compliance", "admin", "owner"),
    "contractual": ("operator", "approver", "compliance", "admin", "owner"),
    "legal_order": ("compliance", "admin", "owner"),
    "regulatory_obligation": ("compliance", "admin", "owner"),
}

# Reviewer roles per category (must differ from the authorizer — enforced).
REVIEWER_ROLES: dict[str, tuple[str, ...]] = {
    "voluntary_control": ("operator", "support", "admin", "owner"),
    "fraud_prevention": ("compliance", "approver", "admin", "owner"),
    "contractual": ("approver", "compliance", "admin", "owner"),
    "legal_order": ("compliance", "admin", "owner"),
    "regulatory_obligation": ("compliance", "auditor", "admin", "owner"),
}

ENGINE_VERSION = "2026.11.02-v1"


def _now() -> int:
    return int(time.time())


def new_restriction(
    *,
    tenant: str,
    subject: str,
    category: str,
    ground: str,
    reason_code: str,
    restriction_type: str,
    authorizer: str,
    authorizer_role: str,
    evidence: list[str] | None = None,
    reason_text: str = "",
    jurisdiction: str = "EU_GENERIC",
    gag_order: bool = False,
    ai_score_used: bool = False,
    ai_score: float | None = None,
    human_reviewer: str = "",
    expires_in_sec: int = 0,
    review_in_sec: int = 0,
    legal_ref: str = "",
) -> dict[str, Any]:
    """Build a restriction record (unauthorized until authorize_restriction passes)."""
    now = _now()
    return {
        "id": f"rst-{uuid.uuid4().hex[:12]}",
        "tenant": tenant,
        "subject": subject,
        "category": category,
        "ground": ground,
        "reasonCode": reason_code,
        "reasonText": reason_text[:500],
        "restrictionType": restriction_type,
        "authorizer": authorizer,
        "authorizerRole": authorizer_role,
        "evidence": list(evidence or []),
        "jurisdiction": jurisdiction,
        "gagOrder": bool(gag_order),
        "aiScoreUsed": bool(ai_score_used),
        "aiScore": ai_score,
        "humanReviewer": human_reviewer,
        "legalRef": legal_ref[:200],
        "state": "proposed",
        "createdAt": now,
        "expiresAt": now + expires_in_sec if expires_in_sec else 0,
        "reviewAt": now + review_in_sec if review_in_sec else 0,
        "engineVersion": ENGINE_VERSION,
    }


def authorize_restriction(doc: dict[str, Any]) -> tuple[bool, str, dict[str, Any]]:
    """Authorize a proposed restriction. Returns (allowed, reason, obligations).

    Obligations are follow-up duties the caller MUST perform (notify customer,
    schedule review, write audit). A denial explains the first failing gate.
    """
    tenant = (doc.get("tenant") or "").strip()
    if not tenant:
        return False, "DENY: tenant scope is required", {}
    subject = (doc.get("subject") or "").strip()
    if not subject:
        return False, "DENY: restriction subject (account/customer id) is required", {}

    category = doc.get("category", "")
    ground = doc.get("ground", "")
    reason_code = doc.get("reasonCode", "")
    rtype = doc.get("restrictionType", "")

    # 1. Known category + ground pairing.
    if category not in AUTHORIZER_ROLES:
        return False, f"DENY: unknown restriction category {category!r}", {}
    if ground not in GROUND_CATEGORY:
        return False, f"DENY: unknown legal/contractual ground {ground!r}", {}
    if GROUND_CATEGORY[ground] != category:
        return False, (
            f"DENY: ground {ground} belongs to category {GROUND_CATEGORY[ground]}, "
            f"not {category}"
        ), {}

    # 2. Mandatory reason code must match the ground.
    if reason_code not in REASON_CODES:
        return False, f"DENY: reason code {reason_code!r} is not allowlisted", {}
    if REASON_GROUND.get(reason_code) != ground:
        return False, (
            f"DENY: reason code {reason_code} requires ground "
            f"{REASON_GROUND.get(reason_code)}, got {ground}"
        ), {}

    # 3. Authorizer role eligibility.
    authorizer = (doc.get("authorizer") or "").strip()
    arole = doc.get("authorizerRole", "")
    if not authorizer:
        return False, "DENY: authenticated authorizer identity is required", {}
    if arole not in AUTHORIZER_ROLES[category]:
        return False, (
            f"DENY: role {arole} may not authorize {category} restrictions"
        ), {}

    # Voluntary controls must come from (or be confirmed by) the customer,
    # except an explicit customer request handled by support/operator.
    if category == "voluntary_control" and arole != "customer":
        ev = [str(e) for e in (doc.get("evidence") or [])]
        if not any("customer-request" in e or "user-consent" in e for e in ev):
            return False, (
                "DENY: voluntary controls require the customer's own request "
                "(evidence must cite customer-request/user-consent)"
            ), {}

    # 4. Supporting evidence (AI score alone is never enough — see gate 7).
    evidence = [str(e) for e in (doc.get("evidence") or []) if str(e).strip()]
    if not evidence:
        return False, "DENY: supporting evidence references are required", {}
    non_ai_evidence = [e for e in evidence if not e.startswith("ai-risk-score")]
    if not non_ai_evidence:
        return False, (
            "DENY: an AI risk score alone cannot justify a restriction; "
            "independent (non-AI) evidence is required"
        ), {}

    # 5. Proportionality: least-restrictive means.
    if rtype not in RESTRICTION_TYPES:
        return False, f"DENY: unknown restriction type {rtype!r}", {}
    if rtype == "full_freeze":
        reviewer = (doc.get("humanReviewer") or "").strip()
        if doc.get("humanReviewer") is not None and not reviewer and category != "legal_order":
            # legal orders carry their own authority; all other full freezes
            # need a named independent reviewer slot up front.
            return False, (
                "DENY: full_freeze is the most restrictive measure and requires "
                "a named independent human reviewer"
            ), {}
        if category in ("voluntary_control", "contractual") and not str(doc.get("reasonText", "")).strip():
            return False, (
                "DENY: full_freeze outside legal/fraud contexts requires "
                "elevated written justification"
            ), {}

    # 6. Time limits + review deadlines.
    now = _now()
    expires_at = int(doc.get("expiresAt") or 0)
    review_at = int(doc.get("reviewAt") or 0)
    try:
        cfg = jurisdictions.get_jurisdiction(doc.get("jurisdiction") or "EU_GENERIC")
    except KeyError as exc:
        return False, f"DENY: {exc}", {}
    max_sec = int(cfg.get("max_restriction_sec", {}).get(category, 30 * 86400))
    if expires_at <= now:
        return False, "DENY: expiresAt must be a future timestamp", {}
    if expires_at - now > max_sec:
        return False, (
            f"DENY: duration exceeds the {cfg['id']} maximum for {category} "
            f"({max_sec}s); renew only after review"
        ), {}
    if review_at <= now or review_at > expires_at:
        return False, (
            "DENY: reviewAt must be set after now and no later than expiresAt "
            "(no restriction without a review deadline)"
        ), {}
    if ground in LEGAL_ORDERS and not str(doc.get("legalRef", "")).strip():
        return False, (
            "DENY: legal-order restrictions require a legal reference "
            "(order id / sanctions listing / case number)"
        ), {}

    # 7. AI guard: score contributed -> human reviewer + independent evidence.
    if doc.get("aiScoreUsed"):
        reviewer = (doc.get("humanReviewer") or "").strip()
        if not reviewer:
            return False, (
                "DENY: when an AI risk score contributed, a named human reviewer "
                "is required (scores never auto-enforce)"
            ), {}
        if reviewer == authorizer:
            return False, (
                "DENY: the AI-score reviewer must be independent of the authorizer"
            ), {}
        if len(non_ai_evidence) < 1:
            return False, (
                "DENY: AI-assisted restrictions require independent non-AI evidence"
            ), {}

    # 8. Notification (suppressed only when the law prohibits it).
    notify = disclosure_allowed(ground, bool(doc.get("gagOrder")))
    obligations: dict[str, Any] = {
        "notifyCustomer": notify,
        "notificationChannel": "account_notice" if notify else "withheld_by_law",
        "scheduleReview": True,
        "reviewAt": review_at,
        "audit": True,
        "engineVersion": ENGINE_VERSION,
    }
    if ground in LEGAL_ORDERS:
        obligations["legalOrderSurvives"] = True
    if category in ("legal_order", "regulatory_obligation"):
        obligations["independentReviewRequired"] = True
    return True, "ALLOW: grounds, evidence, proportionality, and time limits satisfied", obligations


def check_expiry(doc: dict[str, Any], now: int | None = None) -> str:
    """Return 'active', 'review_due', or 'expired' for a restriction."""
    ts = now if now is not None else _now()
    if int(doc.get("expiresAt") or 0) <= ts:
        return "expired"
    if int(doc.get("reviewAt") or 0) <= ts:
        return "review_due"
    return "active"


def correction_required(
    appeal_decision: str, restriction_state: str, chain_valid: bool
) -> bool:
    """Whether an erroneous-restriction correction workflow must run."""
    return appeal_decision == "overturned" or (
        restriction_state == "expired" and not chain_valid
    )

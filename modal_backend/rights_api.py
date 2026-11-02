"""Financial Rights + PDP HTTP surface (APIRouter, mounted by api.py).

Sandbox only. All routes are tenant-scoped and server-authorized:
- restriction create/lift: operator+ (create), compliance/admin (lift), with
  Financial Rights engine authorization + PDP decision + audit.
- appeal submit/decide: filing is authenticated; decisions need an independent
  reviewer (never the original authorizer) + PDP appeal.decide.
- jurisdiction enablement: requires recorded qualified legal review.
- PDP: decision audit read (auditor+) + dry-run simulation endpoint.

The frontend cannot bypass: every mutation evaluates server-side before any
state change, and the engine (not the client) decides notification, expiry,
and review duties.
"""
from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from . import rights_store
from .auth import caller_role, require_admin, require_auth, require_tenant, role_of
from .financial_rights import appeals as appeals_mod
from .financial_rights import engine as rights_engine
from .financial_rights import jurisdictions as jurisdictions_mod
from .financial_rights import monitoring as monitoring_mod
from .logging_util import get_logger, log_event
from .pdp import enforcement as pel
from .pdp import policy as pdp_policy

logger = get_logger("hybridpay.rights")

router = APIRouter()


# ---------- schemas ----------

class RestrictionCreateIn(BaseModel):
    subject: str = Field(min_length=1, max_length=120)
    category: str = Field(min_length=1, max_length=40)
    ground: str = Field(min_length=1, max_length=40)
    reasonCode: str = Field(min_length=1, max_length=40)
    reasonText: str = Field(default="", max_length=500)
    restrictionType: str = Field(min_length=1, max_length=40)
    authorizer: str = Field(min_length=1, max_length=80)
    evidence: list[str] = Field(default_factory=list, max_length=20)
    jurisdiction: str = Field(default="EU_GENERIC", max_length=20)
    gagOrder: bool = False
    aiScoreUsed: bool = False
    aiScore: float | None = None
    humanReviewer: str = Field(default="", max_length=80)
    expiresInSec: int = Field(default=86400, ge=60, le=366 * 86400)
    reviewInSec: int = Field(default=86400, ge=60, le=366 * 86400)
    legalRef: str = Field(default="", max_length=200)


class RestrictionLiftIn(BaseModel):
    actor: str = Field(min_length=1, max_length=80)
    reason: str = Field(min_length=1, max_length=500)


class AppealCreateIn(BaseModel):
    restrictionId: str = Field(min_length=1, max_length=40)
    appellant: str = Field(min_length=1, max_length=80)
    groundsText: str = Field(min_length=1, max_length=2000)
    contact: str = Field(default="", max_length=200)


class AppealDecideIn(BaseModel):
    decision: str = Field(min_length=1, max_length=20)
    reason: str = Field(min_length=1, max_length=1000)
    reviewer: str = Field(min_length=1, max_length=80)


class JurisdictionReviewIn(BaseModel):
    reviewer: str = Field(min_length=1, max_length=120)
    date: str = Field(min_length=1, max_length=20)
    memo: str = Field(min_length=1, max_length=1000)


class PdpSimulateIn(BaseModel):
    action: str = Field(min_length=1, max_length=60)
    resourceType: str = Field(default="", max_length=40)
    resourceTenant: str = Field(default="", max_length=120)
    context: dict[str, Any] = Field(default_factory=dict)


def _role_of_token(authorization: str | None) -> str:
    role = role_of(authorization)
    if role is None:
        return "anonymous"
    return role


# ---------- restrictions ----------

@router.post("/api/rights/restrictions", status_code=201)
async def restriction_create(
    body: RestrictionCreateIn,
    tenant: str = Depends(require_tenant),
    caller: str = Depends(require_auth),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    role = _role_of_token(authorization)
    if role == "anonymous":
        raise HTTPException(status_code=401, detail="missing bearer token")
    # Jurisdiction enforcement gate: profiles without qualified legal review
    # cannot authorize restrictions.
    try:
        jurisdictions_mod.require_legal_review(body.jurisdiction)
    except (PermissionError, KeyError) as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    doc = rights_engine.new_restriction(
        tenant=tenant, subject=body.subject, category=body.category,
        ground=body.ground, reason_code=body.reasonCode,
        restriction_type=body.restrictionType, authorizer=body.authorizer,
        authorizer_role=role, evidence=body.evidence,
        reason_text=body.reasonText, jurisdiction=body.jurisdiction,
        gag_order=body.gagOrder, ai_score_used=body.aiScoreUsed,
        ai_score=body.aiScore, human_reviewer=body.humanReviewer,
        expires_in_sec=body.expiresInSec, review_in_sec=body.reviewInSec,
        legal_ref=body.legalRef,
    )
    allowed, why, obligations = rights_engine.authorize_restriction(doc)
    decision = pel.evaluate_request(
        action="restriction.create", authorization=authorization, tenant=tenant,
        resource_tenant=tenant, resource_type="restriction",
        context={"intent_approved": True, "intent_scope_ok": True,
                 "intent_fresh": True, "step_up_ok": True},
    )
    if not decision["allow"]:
        raise HTTPException(status_code=403, detail=decision["reason"])
    if not allowed:
        rights_store.pdp_record(tenant, "restriction.create", False, why,
                                pdp_policy.POLICY_BUNDLE_VERSION)
        raise HTTPException(status_code=422, detail=why)
    doc["state"] = "active"
    rights_store.restriction_put(doc)
    rights_store.pdp_record(tenant, "restriction.create", True, why,
                            pdp_policy.POLICY_BUNDLE_VERSION)
    from . import db as _db

    _db.audit_append(tenant, "rights.restriction.created", body.authorizer,
                     f"{doc['id']} {body.category}/{body.ground}/{body.reasonCode}"[:500])
    from . import audit_store as _audit

    _audit.must_audit(tenant=tenant, actor=body.authorizer,
                      action="rights.restriction.created", resource=doc["id"],
                      outcome="active", policy="rights-v1",
                      detail=f"{body.category}/{body.ground}/{body.reasonCode}")
    log_event(logger, "rights.restriction.created", tenant=tenant,
              caller=caller, restrictionId=doc["id"])
    return {"restrictionId": doc["id"], "state": "active",
            "notifyCustomer": obligations.get("notifyCustomer"),
            "reviewAt": doc["reviewAt"], "expiresAt": doc["expiresAt"],
            "sandbox": True}


@router.get("/api/rights/restrictions")
async def restriction_list(
    tenant: str = Depends(require_tenant),
    caller: str = Depends(require_auth),
    authorization: str | None = Header(default=None, alias="Authorization"),
    state: str = "", subject: str = "",
) -> dict[str, Any]:
    decision = pel.evaluate_request(
        action="restriction.read", authorization=authorization, tenant=tenant,
        resource_tenant=tenant, resource_type="restriction", context={},
    )
    if not decision.get("allow"):
        status = decision.get("http", 403)
        raise HTTPException(status_code=status, detail=decision["reason"])
    items = rights_store.restriction_list(tenant, state=state, subject=subject)
    now = int(time.time())
    out = []
    for r in items:
        status = rights_engine.check_expiry(r, now)
        out.append({"id": r.get("id"), "subject": r.get("subject"),
                    "category": r.get("category"), "ground": r.get("ground"),
                    "reasonCode": r.get("reasonCode"),
                    "restrictionType": r.get("restrictionType"),
                    "state": status if status != "active" else r.get("state"),
                    "reviewAt": r.get("reviewAt"), "expiresAt": r.get("expiresAt")})
    return {"restrictions": out, "sandbox": True}


@router.post("/api/rights/restrictions/{restriction_id}/lift")
async def restriction_lift(
    restriction_id: str,
    body: RestrictionLiftIn,
    tenant: str = Depends(require_tenant),
    caller: str = Depends(require_admin),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    rec = rights_store.restriction_get(restriction_id, tenant)
    if not rec:
        raise HTTPException(status_code=404, detail="not found")
    decision = pel.evaluate_request(
        action="restriction.lift", authorization=authorization, tenant=tenant,
        resource_tenant=tenant, resource_type="restriction",
        context={"intent_approved": True, "intent_scope_ok": True,
                 "intent_fresh": True, "step_up_ok": True},
    )
    if not decision["allow"]:
        raise HTTPException(status_code=403, detail=decision["reason"])
    rec["state"] = "lifted"
    rec["liftedBy"] = body.actor
    rec["liftReason"] = body.reason[:500]
    rights_store.restriction_put(rec)
    rights_store.pdp_record(tenant, "restriction.lift", True, "lifted after review",
                            pdp_policy.POLICY_BUNDLE_VERSION)
    from . import db as _db

    _db.audit_append(tenant, "rights.restriction.lifted", body.actor, restriction_id)
    from . import audit_store as _audit

    _audit.must_audit(tenant=tenant, actor=body.actor,
                      action="rights.restriction.lifted", resource=restriction_id,
                      outcome="lifted", policy="rights-v1",
                      detail=body.reason[:200])
    return {"restrictionId": restriction_id, "state": "lifted", "sandbox": True,
            "restoration": ["re-evaluate queued operations",
                            "notify customer when legally permitted",
                            "retain append-only audit trail"]}


# ---------- appeals ----------

@router.post("/api/rights/appeals", status_code=201)
async def appeal_create(
    body: AppealCreateIn,
    tenant: str = Depends(require_tenant),
    caller: str = Depends(require_auth),
) -> dict[str, Any]:
    rec = rights_store.restriction_get(body.restrictionId, tenant)
    if not rec:
        raise HTTPException(status_code=404, detail="restriction not found")
    try:
        appeal = appeals_mod.new_appeal(
            tenant=tenant, restriction_id=body.restrictionId,
            appellant=body.appellant, grounds_text=body.groundsText,
            contact=body.contact,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    rights_store.appeal_put(appeal)
    from . import db as _db

    _db.audit_append(tenant, "rights.appeal.submitted", body.appellant,
                     body.restrictionId)
    return {"appealId": appeal["id"], "state": "submitted", "sandbox": True}


@router.post("/api/rights/appeals/{appeal_id}/review")
async def appeal_review(
    appeal_id: str,
    tenant: str = Depends(require_tenant),
    caller: str = Depends(require_auth),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    appeal = rights_store.appeal_get(appeal_id, tenant)
    if not appeal:
        raise HTTPException(status_code=404, detail="not found")
    reviewer = appeal.get("reviewer") or "independent-reviewer"
    try:
        appeals_mod.transition_appeal(appeal, "under_review", caller, reviewer)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    rights_store.appeal_put(appeal)
    return {"appealId": appeal_id, "state": appeal["state"], "sandbox": True}


@router.post("/api/rights/appeals/{appeal_id}/decide")
async def appeal_decide(
    appeal_id: str,
    body: AppealDecideIn,
    tenant: str = Depends(require_tenant),
    caller: str = Depends(require_auth),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    appeal = rights_store.appeal_get(appeal_id, tenant)
    if not appeal:
        raise HTTPException(status_code=404, detail="not found")
    restriction = rights_store.restriction_get(appeal.get("restrictionId", ""), tenant)
    original_authorizer = (restriction or {}).get("authorizer", "")
    decision = pel.evaluate_request(
        action="appeal.decide", authorization=authorization, tenant=tenant,
        resource_tenant=tenant, resource_type="appeal",
        context={"step_up_ok": True},
    )
    if not decision["allow"]:
        raise HTTPException(status_code=403, detail=decision["reason"])
    try:
        appeals_mod.decide_appeal(
            appeal, decision=body.decision, reason=body.reason,
            reviewer=body.reviewer, original_authorizer=original_authorizer,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    rights_store.appeal_put(appeal)
    result: dict[str, Any] = {"appealId": appeal_id, "state": appeal["state"],
                              "decision": appeal["decision"], "sandbox": True}
    if appeal["decision"] == "overturned" and restriction is not None:
        plan = appeals_mod.correction_plan(appeal, restriction=restriction)
        restriction["state"] = "lifted"
        restriction["liftedBy"] = body.reviewer
        restriction["liftReason"] = f"appeal {appeal_id} overturned"
        rights_store.restriction_put(restriction)
        try:
            appeals_mod.transition_appeal(appeal, "corrected", body.reviewer)
            rights_store.appeal_put(appeal)
            result["state"] = "corrected"
        except ValueError:
            pass
        result["correctionPlan"] = plan
        result["restoration"] = appeals_mod.restoration_steps(appeal)
    from . import db as _db

    _db.audit_append(tenant, f"rights.appeal.{appeal['decision']}", body.reviewer,
                     appeal_id)
    return result


# ---------- jurisdictions ----------

@router.post("/api/rights/jurisdictions/{jurisdiction_id}/legal-review")
async def jurisdiction_review(
    jurisdiction_id: str,
    body: JurisdictionReviewIn,
    tenant: str = Depends(require_tenant),
    caller: str = Depends(require_admin),
) -> dict[str, Any]:
    try:
        rec = jurisdictions_mod.record_legal_review(
            jurisdiction_id, reviewer=body.reviewer, date=body.date, memo=body.memo
        )
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    from . import db as _db

    _db.audit_append(tenant, "rights.jurisdiction.reviewed", body.reviewer,
                     f"{jurisdiction_id}: {body.memo}"[:500])
    return {"jurisdiction": jurisdiction_id, "legalReview": rec, "sandbox": True}


@router.get("/api/rights/jurisdictions")
async def jurisdiction_list(
    tenant: str = Depends(require_tenant),
    caller: str = Depends(require_auth),
) -> dict[str, Any]:
    return {"jurisdictions": [
        {"id": jid, "label": cfg["label"],
         "legalReviewRecorded": not jurisdictions_mod.jurisdiction_requires_legal_review(jid)}
        for jid, cfg in jurisdictions_mod.JURISDICTIONS.items()
    ], "sandbox": True}


# ---------- monitoring ----------

@router.get("/api/rights/monitoring/abuse-signals")
async def abuse_signals(
    tenant: str = Depends(require_tenant),
    caller: str = Depends(require_admin),
) -> dict[str, Any]:
    restrictions = rights_store.restriction_list(tenant, limit=200)
    appeals = rights_store.appeal_list(tenant, limit=200)
    findings = monitoring_mod.detect_abuse_patterns(restrictions, appeals)
    return {"tenant": tenant, "findings": findings, "sandbox": True,
            "note": "Signals are for human review; the monitor never auto-punishes."}


# ---------- PDP: audit + simulation ----------

@router.get("/api/pdp/decisions")
async def pdp_decisions(
    tenant: str = Depends(require_tenant),
    caller: str = Depends(require_admin),
    limit: int = 50,
) -> dict[str, Any]:
    return {"tenant": tenant, "policyVersion": pdp_policy.POLICY_BUNDLE_VERSION,
            "decisions": rights_store.pdp_list(tenant, limit=limit), "sandbox": True}


@router.post("/api/pdp/simulate")
async def pdp_simulate(
    body: PdpSimulateIn,
    tenant: str = Depends(require_tenant),
    caller: str = Depends(require_auth),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    """Dry-run: evaluate a decision without side effects (testing + rollout)."""
    decision = pdp_policy.simulate(
        action=body.action, role=_role_of_token(authorization),
        actor="simulate", tenant=tenant,
        resource_tenant=body.resourceTenant or tenant,
        resource_type=body.resourceType, context=body.context,
    )
    return {**decision, "sandbox": True}


@router.get("/api/pdp/policy-version")
async def pdp_version() -> dict[str, Any]:
    return {"policyVersion": pdp_policy.POLICY_BUNDLE_VERSION,
            "actions": sorted(pdp_policy.POLICY_MATRIX.keys()), "sandbox": True}


@router.get("/api/rights/me")
async def rights_me(
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    return {"role": caller_role(authorization), "sandbox": True,
            "engine": rights_engine.ENGINE_VERSION,
            "policy": pdp_policy.POLICY_BUNDLE_VERSION}

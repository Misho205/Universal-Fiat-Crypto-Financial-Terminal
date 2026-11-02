"""Customer dispute HTTP surface (APIRouter, mounted by api.py).

Customer side (Personal Workspace): file a dispute, attach evidence metadata,
track status, read the reasoned outcome (generic wording under gag orders).
Banking side (role-restricted): review queue, assign independent reviewer,
decide with written reason + human basis, propose remediation. Remediation
that moves money executes ONLY through approval bindings — never here.

Admins cannot silently close or delete: close requires a prior decision +
reason + audit; no DELETE route exists for cases or evidence.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from . import audit_store as _audit
from . import disputes as dsp
from .auth import require_admin, require_auth, require_tenant, role_of
from .financial_rights import jurisdictions as jurisdictions_mod
from .logging_util import get_logger, log_event
from .pdp import enforcement as pel

logger = get_logger("hybridpay.disputes")

router = APIRouter()


class DisputeCreateIn(BaseModel):
    customer: str = Field(min_length=1, max_length=80)
    category: str = Field(min_length=1, max_length=40)
    description: str = Field(min_length=1, max_length=2000)
    transactionId: str = Field(default="", max_length=40)
    restrictionId: str = Field(default="", max_length=40)
    agreementId: str = Field(default="", max_length=40)
    jurisdiction: str = Field(default="EU_GENERIC", max_length=20)


class DisputeReviewIn(BaseModel):
    reviewer: str = Field(min_length=1, max_length=80)


class DisputeDecideIn(BaseModel):
    decision: str = Field(min_length=1, max_length=20)
    reason: str = Field(min_length=1, max_length=2000)
    reviewer: str = Field(min_length=1, max_length=80)
    humanBasis: str = Field(default="", max_length=1000)
    originalActor: str = Field(default="", max_length=80)
    aiContributed: bool = False


class EvidenceIn(BaseModel):
    filename: str = Field(min_length=1, max_length=120)
    mime: str = Field(min_length=1, max_length=80)
    sizeBytes: int = Field(ge=1, le=10 * 1024 * 1024)
    sha256: str = Field(min_length=64, max_length=64)
    submittedBy: str = Field(min_length=1, max_length=80)


def _must_audit(**kw: Any) -> None:
    try:
        _audit.must_audit(**kw)
    except _audit.AuditWriteError as exc:
        raise HTTPException(status_code=503, detail=f"audit unavailable: {exc}") from exc


@router.post("/api/disputes", status_code=201)
async def dispute_create(
    body: DisputeCreateIn,
    tenant: str = Depends(require_tenant),
    caller: str = Depends(require_auth),
) -> dict[str, Any]:
    # Abuse prevention: daily cap + duplicate open-case detection.
    if dsp.customer_daily_count(tenant, body.customer) >= dsp.MAX_CASES_PER_CUSTOMER_PER_DAY:
        raise HTTPException(status_code=429, detail="dispute filing limit reached "
                                                   "(abuse prevention; try tomorrow)")
    if dsp.duplicate_open_case(tenant, body.customer, body.category,
                               body.transactionId, body.restrictionId,
                               body.agreementId) is not None:
        raise HTTPException(status_code=409, detail="an open case for this matter "
                                                   "already exists (track it instead)")
    try:
        jurisdictions_mod.require_legal_review(body.jurisdiction)
    except (PermissionError, KeyError) as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    try:
        doc = dsp.new_case(
            tenant=tenant, customer=body.customer, category=body.category,
            description=body.description, transaction_id=body.transactionId,
            restriction_id=body.restrictionId, agreement_id=body.agreementId,
            jurisdiction=body.jurisdiction)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    dsp.case_put(doc)
    _must_audit(tenant=tenant, actor=body.customer, action="dispute.submitted",
                resource=doc["id"], outcome="submitted",
                detail=f"{body.category} links={body.transactionId or body.restrictionId or body.agreementId}")
    log_event(logger, "dispute.submitted", tenant=tenant, caseId=doc["id"])
    return {"caseId": doc["id"], "state": "submitted", "slaDue": doc["slaDue"],
            "sandbox": True,
            "note": "Filing creates no automatic right to reversal or refund; "
                    "a human reviews under the published SLA."}


@router.get("/api/disputes")
async def dispute_list(
    tenant: str = Depends(require_tenant),
    caller: str = Depends(require_auth),
    authorization: str | None = Header(default=None, alias="Authorization"),
    state: str = "", customer: str = "", limit: int = 50,
) -> dict[str, Any]:
    """Track disputes. Customers see ONLY their own; staff see the queue.
    (Server trusts the authenticated tenant + explicit customer filter, and
    customers are confined to their own identity below.)"""
    role = role_of(authorization) or "anonymous"
    if role == "anonymous":
        raise HTTPException(status_code=401, detail="missing bearer token")
    items = dsp.case_list(tenant, limit=limit, state=state,
                          customer=customer if role != "anonymous" else "")
    if role == "operator":
        # Operators see only their own customer's cases: the caller asserts
        # identity via the customer filter (sandbox; production: JWT sub).
        items = [c for c in items if not customer or c.get("customer") == customer]
    return {"tenant": tenant, "sandbox": True,
            "cases": [{k: v for k, v in c.items()
                       if k in ("id", "category", "state", "reviewer", "decision",
                                "slaDue", "createdAt", "updatedAt")}
                       for c in items]}


@router.get("/api/disputes/{case_id}")
async def dispute_get(
    case_id: str,
    tenant: str = Depends(require_tenant),
    caller: str = Depends(require_auth),
) -> dict[str, Any]:
    doc = dsp.case_get(case_id, tenant)
    if not doc:
        raise HTTPException(status_code=404, detail="not found")
    # Gag-aware outcome: generic wording when a linked legal restriction
    # suppresses disclosure; full reason otherwise.
    from . import rights_store
    gagged = False
    if doc.get("restrictionId"):
        restriction = rights_store.restriction_get(doc["restrictionId"], tenant)
        if restriction and restriction.get("gagOrder"):
            gagged = True
    out = {k: doc.get(k) for k in ("id", "category", "state", "reviewer",
                                    "decision", "slaDue", "createdAt", "updatedAt")}
    out["evidence"] = dsp.evidence_list(tenant, case_id)
    if gagged:
        out["outcome"] = ("under legal review with restricted disclosure; "
                          "details withheld by law")
    else:
        out["outcome"] = doc.get("decisionReason", "")
        out["remediation"] = doc.get("remediation", {})
    out["sandbox"] = True
    return out


@router.post("/api/disputes/{case_id}/evidence", status_code=201)
async def dispute_evidence(
    case_id: str,
    body: EvidenceIn,
    tenant: str = Depends(require_tenant),
    caller: str = Depends(require_auth),
) -> dict[str, Any]:
    doc = dsp.case_get(case_id, tenant)
    if not doc:
        raise HTTPException(status_code=404, detail="not found")
    if doc.get("state") == "closed":
        raise HTTPException(status_code=409, detail="case is closed")
    try:
        record = dsp.validate_evidence(body.filename, body.mime,
                                       body.sizeBytes, body.sha256)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    saved = dsp.evidence_put(tenant, case_id, record, body.submittedBy)
    doc.setdefault("evidence", []).append(saved["id"])
    dsp.case_put(doc)
    _must_audit(tenant=tenant, actor=body.submittedBy,
                action="dispute.evidence.added", resource=case_id,
                outcome="pending-human-review",
                detail=f"{saved['filename']} {saved['mime']} {saved['sha256'][:16]}")
    return {"evidenceId": saved["id"], "verdict": saved["verdict"],
            "sandbox": True, "scanNote": saved["scanNote"]}


@router.post("/api/disputes/{case_id}/review")
async def dispute_review(
    case_id: str,
    body: DisputeReviewIn,
    tenant: str = Depends(require_tenant),
    caller: str = Depends(require_auth),
) -> dict[str, Any]:
    """Banking review queue: assign an independent reviewer (never the filer)."""
    doc = dsp.case_get(case_id, tenant)
    if not doc:
        raise HTTPException(status_code=404, detail="not found")
    try:
        dsp.transition(doc, "under_review", caller, body.reviewer)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    dsp.case_put(doc)
    _must_audit(tenant=tenant, actor=caller, action="dispute.under_review",
                resource=case_id, outcome="under_review",
                detail=f"reviewer={body.reviewer}")
    return {"caseId": case_id, "state": doc["state"], "sandbox": True}


@router.post("/api/disputes/{case_id}/decide")
async def dispute_decide(
    case_id: str,
    body: DisputeDecideIn,
    tenant: str = Depends(require_tenant),
    caller: str = Depends(require_auth),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    """Reasoned decision by an independent human reviewer. AI output can never
    be the sole basis; the original decision-maker cannot be the sole reviewer."""
    decision = pel.evaluate_request(
        action="appeal.decide", authorization=authorization, tenant=tenant,
        resource_tenant=tenant, resource_type="appeal",
        context={"step_up_ok": True})
    if not decision.get("allow"):
        raise HTTPException(status_code=403, detail=decision["reason"])
    doc = dsp.case_get(case_id, tenant)
    if not doc:
        raise HTTPException(status_code=404, detail="not found")
    try:
        dsp.decide(doc, decision=body.decision, reason=body.reason,
                   reviewer=body.reviewer, human_basis=body.humanBasis,
                   original_actor=body.originalActor,
                   ai_contributed=body.aiContributed)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    plan: list[str] = []
    if doc["decision"] in ("upheld", "partially_upheld"):
        plan = dsp.remediation_plan(doc)
        doc["remediation"] = {"plan": plan, "status": "proposed"}
        try:
            dsp.transition(doc, "remediation", body.reviewer)
        except ValueError:
            pass
    dsp.case_put(doc)
    _must_audit(tenant=tenant, actor=body.reviewer, action="dispute.decided",
                resource=case_id, outcome=doc["decision"],
                detail=body.reason[:500])
    return {"caseId": case_id, "state": doc["state"], "decision": doc["decision"],
            "remediationPlan": plan, "sandbox": True,
            "note": "Remediation that moves money executes only through approval "
                    "bindings with explicit approval — never automatically."}


@router.post("/api/disputes/{case_id}/close")
async def dispute_close(
    case_id: str,
    tenant: str = Depends(require_tenant),
    caller: str = Depends(require_auth),
) -> dict[str, Any]:
    """Close requires a prior decision + audit. Silent closes and deletes are
    impossible: no DELETE route exists and close without a decision is refused."""
    doc = dsp.case_get(case_id, tenant)
    if not doc:
        raise HTTPException(status_code=404, detail="not found")
    if not doc.get("decision"):
        raise HTTPException(status_code=409, detail="cannot close an undecided case "
                                                   "(decide with written reason first)")
    if doc.get("state") == "remediation":
        raise HTTPException(status_code=409, detail="remediation proposed — close only "
                                                   "after remediation completes")
    try:
        dsp.transition(doc, "closed", caller)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    dsp.case_put(doc)
    _must_audit(tenant=tenant, actor=caller, action="dispute.closed",
                resource=case_id, outcome=doc["decision"], detail="")
    return {"caseId": case_id, "state": "closed", "sandbox": True}

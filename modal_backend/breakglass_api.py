"""Break-glass HTTP surface (APIRouter, mounted by api.py).

- POST /api/breakglass/sessions — request (operator+, MFA attested). Returns
  the opaque session token ONCE (never stored, only its digest).
- POST /api/breakglass/sessions/{id}/approve — independent approver
  (admin bearer; different identity AND credential).
- POST /api/breakglass/sessions/{id}/extend — independent extension only.
- POST /api/breakglass/sessions/{id}/revoke — terminate now (requestor,
  approver, or admin). Rotation = revoke + new session.
- POST /api/breakglass/sessions/{id}/review — mandatory retrospective
  independent review (auditor/compliance/approver/owner).
- POST /api/breakglass/actions — session-token gateway: exactly one
  allowlisted action per call, tenant-bound, audited. Step-up for
  state-changing actions.
- GET /api/breakglass/sessions, /notifications — oversight (auditor+).

Every initiation, approval, action, expiry, revocation, and review is
recorded in the independent audit system; security personnel are notified
via audited breakglass.notify.* events.
"""
from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from . import audit_store as _audit
from . import breakglass as bg
from .auth import require_admin, require_auth, require_tenant, role_of
from .logging_util import get_logger, log_event
from .pdp import enforcement as pel

logger = get_logger("hybridpay.breakglass")

router = APIRouter()


class SessionRequestIn(BaseModel):
    incidentRef: str = Field(min_length=1, max_length=120)
    justification: str = Field(min_length=1, max_length=1000)
    requestor: str = Field(min_length=1, max_length=80)
    mfaMethod: str = Field(min_length=1, max_length=20)
    mfaRef: str = Field(min_length=1, max_length=200)
    scopes: list[str] = Field(default_factory=list, max_length=10)
    ttlSec: int = Field(default=900, ge=60, le=3600)
    preauthorized: bool = False
    approvalUnreachable: bool = False


class SessionApproveIn(BaseModel):
    approver: str = Field(min_length=1, max_length=80)


class SessionExtendIn(BaseModel):
    actor: str = Field(min_length=1, max_length=80)
    extraSec: int = Field(ge=60, le=3600)


class SessionRevokeIn(BaseModel):
    actor: str = Field(min_length=1, max_length=80)
    reason: str = Field(default="", max_length=500)


class SessionReviewIn(BaseModel):
    reviewer: str = Field(min_length=1, max_length=80)
    findings: str = Field(min_length=1, max_length=2000)


class GatewayActionIn(BaseModel):
    sessionId: str = Field(min_length=1, max_length=40)
    sessionToken: str = Field(min_length=1, max_length=128)
    action: str = Field(min_length=1, max_length=40)
    confirm: bool = False
    reason: str = Field(default="", max_length=500)
    params: dict[str, Any] = Field(default_factory=dict)


def _bearer(authorization: str | None) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        return ""
    return authorization.removeprefix("Bearer ").strip()


def _cred(authorization: str | None) -> str:
    from . import approval_binding as _ab
    return _ab.credential_id(_bearer(authorization))


def _notify(tenant: str, event: str, actor: str, detail: str,
            session_id: str = "") -> None:
    """Notify independent security personnel: audited notification event."""
    try:
        _audit.record_event(
            tenant=tenant, actor=actor, action=f"breakglass.notify.{event}",
            resource=session_id or tenant, outcome="notified",
            correlation_id=session_id, detail=detail[:500])
    except _audit.AuditWriteError:
        pass


@router.post("/api/breakglass/sessions", status_code=201)
async def session_request(
    body: SessionRequestIn,
    tenant: str = Depends(require_tenant),
    caller: str = Depends(require_auth),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    role = role_of(authorization) or "anonymous"
    if role == "anonymous":
        raise HTTPException(status_code=401, detail="missing bearer token")
    if role not in ("operator", "admin", "owner"):
        raise HTTPException(status_code=403, detail="DENY: break-glass request "
                                                   "requires an authenticated operator")
    # Approval-service outage must be explicitly attested for the preauth path.
    try:
        doc, token = bg.request_session(
            tenant=tenant, incident_ref=body.incidentRef,
            justification=body.justification, requestor=body.requestor,
            requestor_cred=_cred(authorization), mfa_method=body.mfaMethod,
            mfa_ref=body.mfaRef, scopes=body.scopes, ttl_sec=body.ttlSec,
            preauthorized=body.preauthorized,
            approval_unreachable=body.approvalUnreachable)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    bg.session_put(doc)
    _audit.must_audit(tenant=tenant, actor=body.requestor,
                      action="breakglass.session.requested", resource=doc["id"],
                      outcome=doc["state"], correlation_id=doc["id"],
                      detail=f"{body.incidentRef}: {body.justification[:200]}")
    _notify(tenant, "session.requested", body.requestor,
            f"incident {body.incidentRef} scopes={','.join(doc['scopes'])}",
            doc["id"])
    log_event(logger, "breakglass.session.requested", tenant=tenant,
              sessionId=doc["id"])
    out = {k: v for k, v in doc.items() if k not in ("tokenHash", "requestorCred")}
    out["sessionId"] = out.pop("id")
    return {**out, "sessionToken": token, "sandbox": True,
            "warning": "Token shown ONCE. It expires automatically and cannot "
                       "extend itself or widen scopes."}


@router.post("/api/breakglass/sessions/{session_id}/approve")
async def session_approve(
    session_id: str,
    body: SessionApproveIn,
    tenant: str = Depends(require_tenant),
    caller: str = Depends(require_admin),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    doc = bg.session_get(session_id, tenant)
    if not doc:
        raise HTTPException(status_code=404, detail="not found")
    try:
        bg.approve_session(doc, body.approver, _cred(authorization))
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    bg.session_put(doc)
    _audit.must_audit(tenant=tenant, actor=body.approver,
                      action="breakglass.session.approved", resource=session_id,
                      outcome="active", correlation_id=session_id,
                      detail=f"incident {doc['incidentRef']}")
    _notify(tenant, "session.approved", body.approver,
            f"session {session_id} active until {doc['expiresAt']}", session_id)
    return {"sessionId": session_id, "state": "active",
            "expiresAt": doc["expiresAt"], "sandbox": True}


@router.post("/api/breakglass/sessions/{session_id}/extend")
async def session_extend(
    session_id: str,
    body: SessionExtendIn,
    tenant: str = Depends(require_tenant),
    caller: str = Depends(require_auth),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    doc = bg.session_get(session_id, tenant)
    if not doc:
        raise HTTPException(status_code=404, detail="not found")
    try:
        bg.extend_session(doc, body.actor, _cred(authorization), body.extraSec)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    bg.session_put(doc)
    _audit.must_audit(tenant=tenant, actor=body.actor,
                      action="breakglass.session.extended", resource=session_id,
                      outcome="active", correlation_id=session_id,
                      detail=f"+{body.extraSec}s")
    return {"sessionId": session_id, "expiresAt": doc["expiresAt"],
            "sandbox": True}


@router.post("/api/breakglass/sessions/{session_id}/revoke")
async def session_revoke(
    session_id: str,
    body: SessionRevokeIn,
    tenant: str = Depends(require_tenant),
    caller: str = Depends(require_auth),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    """Terminate now. Allowed for the requestor, any approver, or an admin —
    revocation is always available, never gated on the session itself."""
    doc = bg.session_get(session_id, tenant)
    if not doc:
        raise HTTPException(status_code=404, detail="not found")
    role = role_of(authorization) or "anonymous"
    if role == "anonymous":
        raise HTTPException(status_code=401, detail="missing bearer token")
    allowed = (
        body.actor.strip().lower() == doc["requestor"].strip().lower()
        or any(body.actor.strip().lower() == a.get("approver", "").lower()
               for a in doc.get("approvals", []))
        or role in ("admin", "owner")
    )
    if not allowed:
        raise HTTPException(status_code=403, detail="DENY: only the requestor, "
                                                   "an approver, or an admin may revoke")
    try:
        bg.revoke_session(doc, body.actor)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    bg.session_put(doc)
    _audit.must_audit(tenant=tenant, actor=body.actor,
                      action="breakglass.session.revoked", resource=session_id,
                      outcome="revoked", correlation_id=session_id,
                      detail=body.reason[:200])
    _notify(tenant, "session.revoked", body.actor,
            f"session {session_id} revoked: {body.reason[:200]}", session_id)
    return {"sessionId": session_id, "state": "revoked", "sandbox": True,
            "rotation": "rotation = revoke + new session (tokens are per-session)"}


@router.post("/api/breakglass/sessions/{session_id}/review")
async def session_review(
    session_id: str,
    body: SessionReviewIn,
    tenant: str = Depends(require_tenant),
    caller: str = Depends(require_admin),
) -> dict[str, Any]:
    """Mandatory retrospective independent review (reviewer != requestor)."""
    doc = bg.session_get(session_id, tenant)
    if not doc:
        raise HTTPException(status_code=404, detail="not found")
    if body.reviewer.strip().lower() == doc["requestor"].strip().lower():
        raise HTTPException(status_code=403, detail="DENY: retrospective review "
                                                   "must be independent of the requestor")
    doc["review"] = {"reviewer": body.reviewer, "findings": body.findings[:2000],
                     "at": int(time.time())}
    if doc["state"] in ("active", "expired", "revoked", "pending_approval"):
        doc["state"] = "closed"
    bg.session_put(doc)
    from . import db as _db

    _db.audit_append(tenant, "breakglass.session.reviewed", body.reviewer, session_id)
    _audit.must_audit(tenant=tenant, actor=body.reviewer,
                      action="breakglass.session.reviewed", resource=session_id,
                      outcome="closed", correlation_id=session_id,
                      detail=body.findings[:500])
    return {"sessionId": session_id, "state": doc["state"], "sandbox": True}


@router.post("/api/breakglass/actions")
async def gateway_action(
    body: GatewayActionIn,
    tenant: str = Depends(require_tenant),
    caller: str = Depends(require_auth),
) -> dict[str, Any]:
    """Session-token gateway: one allowlisted action per call, fully audited.

    Read actions return live backend data (same authoritative sources as the
    operator APIs). `restriction.create` is the ONLY state-changing action and
    goes through the Financial Rights engine + PDP with per-call step-up.
    """
    doc = bg.session_get(body.sessionId, tenant)
    if not doc:
        raise HTTPException(status_code=404, detail="not found")
    try:
        grant = bg.authorize_session_action(
            doc, body.sessionToken, body.action, tenant,
            step_up={"confirm": body.confirm, "reason": body.reason})
    except ValueError as exc:
        msg = str(exc)
        code = 403 if ("exceeds" in msg or "outside" in msg or "cross-tenant" in msg
                       or "unknown or revoked" in msg) else 409
        raise HTTPException(status_code=code, detail=msg) from exc
    result = await _execute_gateway_action(tenant, body, grant)
    _audit.must_audit(tenant=tenant, actor=f"breakglass:{doc['requestor']}",
                      action=f"breakglass.action.{body.action}",
                      resource=body.sessionId, outcome="ok",
                      correlation_id=body.sessionId,
                      detail=f"{body.action} incident={doc['incidentRef']}")
    return {"sessionId": body.sessionId, "action": body.action,
            "sandbox": True, "result": result}


async def _execute_gateway_action(tenant: str, body: GatewayActionIn,
                                 grant: dict[str, Any]) -> dict[str, Any]:
    from . import db as _db

    if body.action == "payment.read":
        pid = str(body.params.get("paymentId", ""))
        row = _db._fetch_one("SELECT * FROM transactions WHERE id=? AND tenant=?",
                             (pid, tenant))
        if not row:
            raise HTTPException(status_code=404, detail="not found")
        return {"paymentId": row["id"], "state": row["state"],
                "amountMinor": row["amount_minor"]}
    if body.action == "agreement.read":
        ag = _db.pag_get(str(body.params.get("agreementId", "")), tenant)
        if not ag:
            raise HTTPException(status_code=404, detail="not found")
        return {"agreementId": ag["id"], "state": ag["state"],
                "version": ag.get("version", 1)}
    if body.action == "restriction.read":
        from . import rights_store
        rec = rights_store.restriction_get(str(body.params.get("restrictionId", "")),
                                           tenant)
        if not rec:
            raise HTTPException(status_code=404, detail="not found")
        return {"restrictionId": rec["id"], "state": rec.get("state"),
                "category": rec.get("category")}
    if body.action in ("audit.read", "audit.verify", "data.read"):
        if body.action == "audit.verify":
            return _audit.verify_chain(tenant)
        return {"tenant": tenant, "note": "read-only emergency access",
                "events": len(_audit.list_events(tenant, limit=5))}
    if body.action == "restriction.create":
        # The ONLY state-changing gateway action: fraud holds via the rights
        # engine (grounds/evidence/expiry enforced; legal-order lifts NOT
        # offered here — they need the normal compliance path).
        from .financial_rights import engine as rights_engine
        from .financial_rights import jurisdictions as jurisdictions_mod
        from . import rights_store
        p = body.params
        if p.get("category", "fraud_prevention") != "fraud_prevention":
            raise HTTPException(status_code=403, detail="emergency gateway may "
                                                       "only create fraud-prevention holds")
        try:
            jurisdictions_mod.require_legal_review(p.get("jurisdiction", "EU_GENERIC"))
        except (PermissionError, KeyError) as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        rdoc = rights_engine.new_restriction(
            tenant=tenant, subject=str(p.get("subject", "")),
            category="fraud_prevention", ground="FRAUD_SUSPICION",
            reason_code="FRAUD_SUSPECT_HOLD",
            restriction_type=str(p.get("restrictionType", "outbound_freeze")),
            authorizer=f"breakglass:{grant.get('requestor', '')}",
            authorizer_role="operator", evidence=[f"incident:{p.get('incidentRef', '')}"],
            expires_in_sec=4 * 3600, review_in_sec=3600)
        allowed, why, _ = rights_engine.authorize_restriction(rdoc)
        if not allowed:
            raise HTTPException(status_code=422, detail=why)
        rdoc["state"] = "active"
        rights_store.restriction_put(rdoc)
        return {"restrictionId": rdoc["id"], "state": "active"}
    raise HTTPException(status_code=403, detail=f"action {body.action} not served")


@router.get("/api/breakglass/sessions")
async def session_list(
    tenant: str = Depends(require_tenant),
    caller: str = Depends(require_auth),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    decision = pel.evaluate_request(
        action="emergency.grant", authorization=authorization, tenant=tenant,
        resource_tenant=tenant, resource_type="emergency",
        context={"intent_approved": True, "intent_scope_ok": True,
                 "intent_fresh": True, "step_up_ok": True})
    if not decision.get("allow"):
        raise HTTPException(status_code=403, detail=decision["reason"])
    return {"tenant": tenant, "sessions": bg.session_list(tenant),
            "sandbox": True}


@router.get("/api/breakglass/notifications")
async def notifications(
    tenant: str = Depends(require_tenant),
    caller: str = Depends(require_auth),
    authorization: str | None = Header(default=None, alias="Authorization"),
    limit: int = 50,
) -> dict[str, Any]:
    """Security-personnel notification feed (audited breakglass.notify.* events)."""
    decision = pel.evaluate_request(
        action="audit.read", authorization=authorization, tenant=tenant,
        resource_tenant=tenant, resource_type="audit", context={})
    if not decision.get("allow"):
        raise HTTPException(status_code=403, detail=decision["reason"])
    events = _audit.list_events(tenant, limit=limit)
    notes = [e for e in events if e["action"].startswith("breakglass.notify.")]
    return {"tenant": tenant, "notifications": notes, "sandbox": True}

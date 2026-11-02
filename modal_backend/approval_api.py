"""Cryptographic approval-binding HTTP surface (APIRouter, mounted by api.py).

- POST /api/approvals/bindings — maker creates a binding from the FULL
  operation parameters. The backend canonicalizes + digests; the digest is
  returned and every later step references it (never raw client claims).
- POST /api/approvals/bindings/{id}/approve — checker approves with step-up
  (confirm + reason + Idempotency-Key), no-self-approval (identity + credential
  binding), quorum from institutional policy.
- GET /api/approvals/bindings/{id} — read binding + quorum status (tenant-scoped).

AI services can never approve: there is no AI input anywhere in this module,
and approval validation is pure backend code. Administrators follow the same
quorum + step-up as everyone else — no bypass path exists.
"""
from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from . import approval_binding as ab
from . import institutional
from .auth import require_admin, require_auth, require_tenant, role_of
from .logging_util import get_logger, log_event

logger = get_logger("hybridpay.approval_binding")

router = APIRouter()


class BindingCreateIn(BaseModel):
    opType: str = Field(min_length=1, max_length=40)
    targetId: str = Field(min_length=1, max_length=120)
    initiator: str = Field(min_length=1, max_length=80)
    counterparty: str = Field(default="", max_length=120)
    amountMinor: str = Field(default="0", max_length=16)
    currency: str = Field(default="", max_length=3)
    contractVersion: int = Field(default=0, ge=0)
    termsHash: str = Field(default="", max_length=128)
    ttlSec: int = Field(default=86400, ge=60, le=30 * 86400)
    maker: str = Field(min_length=1, max_length=80)
    reason: str = Field(min_length=1, max_length=500)


class BindingApproveIn(BaseModel):
    checker: str = Field(min_length=1, max_length=80)
    confirm: bool = False
    reason: str = Field(default="", max_length=500)


def _bearer(authorization: str | None) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        return ""
    return authorization.removeprefix("Bearer ").strip()


@router.post("/api/approvals/bindings", status_code=201)
async def binding_create(
    body: BindingCreateIn,
    tenant: str = Depends(require_tenant),
    caller: str = Depends(require_auth),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    role = role_of(authorization) or "anonymous"
    allowed, why = institutional.policy_decide(
        action=_intent_action(body.opType), role=role, tenant=tenant,
        actor=body.maker, amount_minor=body.amountMinor,
    )
    if not allowed and "unknown sensitive action" in why:
        # op types outside the legacy intent matrix are still bindable —
        # binding is stricter (digest-bound), so allow creation; execution
        # paths decide. Only unknown OP_TYPES are rejected below.
        allowed, why = True, "ALLOW: digest-bound approval (stricter than intent)"
    if not allowed:
        raise HTTPException(status_code=403, detail=why)
    now = int(time.time())
    try:
        canonical = ab.canonical_operation(
            op_id=ab.new_op_id(), tenant=tenant, op_type=body.opType,
            target_id=body.targetId, initiator=body.initiator,
            counterparty=body.counterparty, amount_minor=body.amountMinor,
            currency=body.currency, contract_version=body.contractVersion,
            terms_hash=body.termsHash, expires_at=now + body.ttlSec,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    digest = ab.operation_digest(canonical)
    if ab.binding_get_by_digest(digest, tenant) is not None:
        raise HTTPException(status_code=409, detail="binding already exists "
                                                   "for this exact operation")
    doc = {
        "id": f"bd-{digest[:12]}", "tenant": tenant, "op_digest": digest,
        "op_type": body.opType, "target_id": body.targetId, "maker": body.maker,
        "makerKey": institutional._actor_key(_bearer(authorization), body.maker),
        "credId": ab.credential_id(_bearer(authorization)),
        "reason": body.reason, "state": "pending", "approvals": [],
        "quorum": institutional.required_quorum(body.amountMinor),
        "expiresAt": now + body.ttlSec, "consumedAt": 0, "op": canonical,
        "createdAt": now,
    }
    ab.binding_put(doc)
    from . import db as _db

    _db.audit_append(tenant, "approval.binding.created", body.maker,
                     f"{doc['id']} {body.opType} {body.targetId} digest={digest[:16]}"[:500])
    from . import audit_store as _audit

    # Fail closed: without a durable structured record the binding MUST NOT
    # exist (an unlogged approval is an unauthorized approval).
    _audit.must_audit(tenant=tenant, actor=body.maker, action="approval.binding.created",
                      resource=doc["id"], outcome="pending", policy="ab-v1",
                      approval_ref=doc["id"],
                      detail=f"{body.opType} {body.targetId} digest={digest[:16]}")
    log_event(logger, "approval.binding.created", tenant=tenant, bindingId=doc["id"])
    return {"bindingId": doc["id"], "opDigest": digest, "state": "pending",
            "quorum": doc["quorum"], "expiresAt": doc["expiresAt"],
            "sandbox": True,
            "note": "Approvals bind this exact digest. Any parameter change "
                    "invalidates it — fresh approvals required."}


@router.post("/api/approvals/bindings/{binding_id}/approve")
async def binding_approve(
    binding_id: str,
    body: BindingApproveIn,
    tenant: str = Depends(require_tenant),
    caller: str = Depends(require_admin),
    authorization: str | None = Header(default=None, alias="Authorization"),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict[str, Any]:
    ok, why = institutional.step_up_ok(
        {"confirm": body.confirm, "reason": body.reason},
        {"idempotency-key": idempotency_key or ""},
    )
    if not ok:
        raise HTTPException(status_code=422, detail=why)
    doc = ab.binding_get(binding_id, tenant)
    if not doc:
        raise HTTPException(status_code=404, detail="not found")
    token = _bearer(authorization)
    # Separation of duties: checker must differ from maker by identity AND by
    # credential. credId = sha256(maker bearer token): the same credential
    # under a different label (alt account) is still detected — the raw
    # secret is never stored, only its digest.
    if body.checker.strip().lower() == doc["maker"].strip().lower():
        raise HTTPException(status_code=403, detail="DENY: self-approval "
                                                   "forbidden (same actor)")
    if token and doc.get("credId") and ab.credential_id(token) == doc["credId"]:
        raise HTTPException(status_code=403, detail="DENY: self-approval "
                                                   "forbidden (same credential)")
    try:
        updated = ab.binding_add_approval(
            binding_id, tenant, body.checker,
            institutional._actor_key(token, body.checker), body.reason)
    except (LookupError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    from . import db as _db

    _db.audit_append(tenant, f"approval.binding.{updated['state']}", body.checker,
                     f"{binding_id} quorum={updated['quorum']}")
    from . import audit_store as _audit

    _audit.must_audit(tenant=tenant, actor=body.checker,
                      action=f"approval.binding.{updated['state']}",
                      resource=binding_id, outcome=updated["state"],
                      policy="ab-v1", approval_ref=binding_id,
                      detail=f"quorum={updated['quorum']}")
    log_event(logger, "approval.binding.approved", tenant=tenant,
              bindingId=binding_id)
    return {"bindingId": binding_id, "state": updated["state"],
            "approvals": len(updated["approvals"]), "quorum": updated["quorum"],
            "sandbox": True}


@router.get("/api/approvals/bindings/{binding_id}")
async def binding_get(
    binding_id: str,
    tenant: str = Depends(require_tenant),
    caller: str = Depends(require_auth),
) -> dict[str, Any]:
    doc = ab.binding_get(binding_id, tenant)
    if not doc:
        raise HTTPException(status_code=404, detail="not found")
    return {"bindingId": doc["id"], "opDigest": doc["op_digest"],
            "opType": doc["op_type"], "targetId": doc["targetId"],
            "state": doc["state"], "approvals": doc["approvals"],
            "quorum": doc["quorum"], "expiresAt": doc["expiresAt"],
            "quorumMet": institutional.quorum_met(doc["approvals"], doc["quorum"]),
            "sandbox": True}


def _intent_action(op_type: str) -> str:
    return {
        "fiat.cancel": "fiat.cancel",
        "fiat.refund": "fiat.refund",
        "agreement.execute": "agreement.execute",
        "agreement.cancel": "agreement.cancel",
        "agreement.dispute": "agreement.dispute",
    }.get(op_type, f"binding.{op_type}")

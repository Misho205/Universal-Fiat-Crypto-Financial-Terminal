"""Independent audit HTTP surface (APIRouter, mounted by api.py).

Read-only dashboard for authorized auditors + integrity verification +
retention-protected export. Write path is server-side only (audit_store);
there is deliberately NO update/delete endpoint for audit records.

Access: auditor, compliance, approver, admin, owner (PDP audit.read).
Operator is excluded (least privilege); the legacy /api/admin/audit stays
admin-only for compatibility.
"""
from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException

from . import audit_store
from .auth import require_admin, require_auth, require_tenant, role_of
from .pdp import enforcement as pel

router = APIRouter()

_EXPORT_DIR = os.environ.get("AUDIT_EXPORT_DIR", "./data/audit-exports")


def _auditor_or_deny(authorization: str | None, tenant: str) -> None:
    decision = pel.evaluate_request(
        action="audit.read", authorization=authorization, tenant=tenant,
        resource_tenant=tenant, resource_type="audit", context={},
    )
    if not decision.get("allow"):
        status = decision.get("http", 403)
        raise HTTPException(status_code=status, detail=decision["reason"])


@router.get("/api/audit/events")
async def audit_events(
    tenant: str = Depends(require_tenant),
    caller: str = Depends(require_auth),
    authorization: str | None = Header(default=None, alias="Authorization"),
    limit: int = 100,
    action: str = "",
) -> dict[str, Any]:
    """Read-only audit dashboard feed (no mutation possible here)."""
    _auditor_or_deny(authorization, tenant)
    return {"tenant": tenant, "sandbox": True,
            "events": audit_store.list_events(tenant, limit=limit, action=action)}


@router.get("/api/audit/verify")
async def audit_verify(
    tenant: str = Depends(require_tenant),
    caller: str = Depends(require_auth),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    """Integrity verification + alerts (tamper, gaps, privileged activity)."""
    _auditor_or_deny(authorization, tenant)
    chain = audit_store.verify_chain(tenant)
    return {"tenant": tenant, "sandbox": True, **chain,
            "outboxPending": audit_store.outbox_pending(),
            "privilegedActivity": audit_store.privileged_activity(tenant, limit=50),
            "note": "Hash chaining detects tampering; it does not by itself "
                    "guarantee immutability. Compare against independent "
                    "exports (see AUDIT_ARCHITECTURE.md)."}


@router.post("/api/audit/export")
async def audit_export(
    tenant: str = Depends(require_tenant),
    caller: str = Depends(require_admin),
) -> dict[str, Any]:
    """Export to independently controlled storage (admin, audited)."""
    result = audit_store.export_jsonl(tenant, _EXPORT_DIR)
    try:
        audit_store.record_event(
            tenant=tenant, actor="policy-engine", action="audit.export",
            resource=tenant, outcome="ok" if result.get("exported") else "failed",
            detail=f"exported={result.get('exported', 0)}",
            enqueue_export=False,
        )
    except audit_store.AuditWriteError:
        pass
    if result.get("exported", 0) == 0 and result.get("error"):
        raise HTTPException(status_code=503, detail=f"export unavailable: "
                                                   f"{result['error']} (outbox retains events)")
    return {"tenant": tenant, "sandbox": True, **result}

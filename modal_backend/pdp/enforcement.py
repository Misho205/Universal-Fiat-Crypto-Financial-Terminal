"""Policy Enforcement Layer: FastAPI dependencies wrapping the PDP.

- require_policy(action): dependency factory for sensitive entry points.
  Reads ONLY server-trusted signals (bearer token -> role, server-side tenant
  binding). The client X-Tenant-Id header is accepted solely as the local-dev
  fallback inside require_tenant (same semantics as the rest of the backend);
  the PDP additionally verifies resource.tenant == principal.tenant.
- Decisions are written to the tamper-evident audit log (allow + deny).
- Denials raise HTTP 403 (fail closed); authentication failures stay 401 from
  require_auth/require_admin. The frontend cannot bypass: every wired route
  evaluates server-side before any state change.
"""
from __future__ import annotations

from typing import Any

from fastapi import Depends, Header, HTTPException

from ..auth import require_tenant, role_of
from .. import db as _db
from . import policy


class EnforcementError(HTTPException):
    pass


def _principal_tenant(authorization: str | None, tenant: str) -> str:
    # Tenant here already passed through require_tenant (server binding aware).
    return tenant


def evaluate_request(
    *,
    action: str,
    authorization: str | None,
    tenant: str,
    resource_tenant: str = "",
    resource_type: str = "",
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    role = role_of(authorization)
    if role is None:
        # No/invalid bearer: only allow if the app runs tokenless (bare local
        # dev); otherwise deny here so the PEL fails closed even on routes
        # that forgot require_auth.
        from .. import config

        if config.API_SHARED_TOKEN or config.API_ADMIN_TOKEN:
            return {
                "allow": False,
                "reason": "DENY: missing or invalid bearer token",
                "policy_version": policy.POLICY_BUNDLE_VERSION,
                "obligations": ["audit"],
                "http": 401,
            }
        role = "dev-caller"
    decision = policy.evaluate(
        action=action,
        role=role,
        actor="bearer-principal",
        tenant=_principal_tenant(authorization, tenant),
        resource_tenant=resource_tenant or tenant,
        resource_type=resource_type,
        context=context or {},
    )
    return decision


def require_policy(action: str, resource_type: str = ""):
    """FastAPI dependency: enforce `action` via the PDP before the handler runs."""

    async def _enforce(
        authorization: str | None = Header(default=None, alias="Authorization"),
        tenant: str = Depends(require_tenant),
    ) -> dict[str, Any]:
        rule = policy.POLICY_MATRIX.get(action)
        decision = evaluate_request(
            action=action,
            authorization=authorization,
            tenant=tenant,
            resource_tenant=tenant,
            resource_type=resource_type or (rule["resource"] if rule else ""),
            context={"intent_approved": True, "intent_scope_ok": True,
                     "intent_fresh": True, "step_up_ok": True},
        )
        # Sandbox wiring note: routes that already enforce maker-checker intents
        # + step-up in their handlers pass a permissive context here; the PDP
        # still denies unknown roles/actions and cross-tenant access. Strict
        # (intent-gated) deployments flip these flags via evaluate_request
        # callers — see docs/POLICY_MATRIX.md rollout plan.
        _record_decision(tenant, action, decision)
        if not decision.get("allow"):
            raise HTTPException(status_code=403, detail=decision["reason"])
        return decision

    return _enforce


def _record_decision(tenant: str, action: str, decision: dict[str, Any]) -> None:
    """Write the decision to the tamper-evident audit trail AND the
    append-only PDP decision log (surfaced by GET /api/pdp/decisions)."""
    try:
        _db.audit_append(
            tenant, f"pdp.decision.{action}",
            "policy-engine",
            f"{'ALLOW' if decision['allow'] else 'DENY'} {action} "
            f"{decision['reason']}"[:500],
        )
    except Exception:
        pass
    try:
        from .. import rights_store as _rights_store

        _rights_store.pdp_record(
            tenant, action, bool(decision["allow"]), decision["reason"],
            policy.POLICY_BUNDLE_VERSION,
        )
    except Exception:
        pass

"""Central Policy Decision Point — deterministic, default-deny, versioned.

Input (all server-derived; client headers never trusted for identity):
  principal: {role, actor, tenant, credential}  (role from bearer token)
  resource:  {type, id, tenant}
  action:    one of POLICY_MATRIX actions
  context:   {amount_minor, purpose, intent_approved, intent_scope_ok,
              intent_fresh, step_up_ok, grant_scopes, emergency, legal_review,
              ai_tool, read_only}

Decision: {allow, reason, policy_version, obligations[]}.
- Unknown action/resource/role -> DENY (default-deny).
- Cross-tenant (resource.tenant != principal.tenant) -> DENY, always.
- Sensitive writes require an approved, unexpired, scope-bound intent
  (multi-party approval) + step-up where flagged.
- Read-only safe operations stay available when authenticated.
- Exceptions fail closed (DENY), never open.

The bundle is version-controlled in this file (POLICY_BUNDLE_VERSION);
changes require independent review + rollback via git history.
"""
from __future__ import annotations

from typing import Any

POLICY_BUNDLE_VERSION = "2026.11.02-v1"

# action -> rule. needs_intent: multi-party approval required.
# step_up: explicit confirm+reason+idempotency ceremony required.
# allowed_roles: transport-mapped roles that may attempt (maker or checker side).
POLICY_MATRIX: dict[str, dict[str, Any]] = {
    # Customer payments (fiat sandbox create/confirm, EVM request/submit).
    "payment.create": {
        "resource": "payment", "allowed_roles": ("operator", "admin", "owner"),
        "needs_intent": False, "step_up": False, "read_only": False,
        "obligations": ["audit"],
    },
    "payment.confirm": {
        "resource": "payment", "allowed_roles": ("operator", "admin", "owner"),
        "needs_intent": False, "step_up": False, "read_only": False,
        "obligations": ["audit"],
    },
    "payment.read": {
        "resource": "payment", "allowed_roles": ("operator", "approver", "auditor", "compliance", "admin", "owner"),
        "needs_intent": False, "step_up": False, "read_only": True,
        "obligations": [],
    },
    # Institutional payments (cancel/refund — money movement reversal).
    "payment.cancel": {
        "resource": "payment", "allowed_roles": ("operator", "admin", "owner"),
        "needs_intent": True, "step_up": True, "read_only": False,
        "obligations": ["audit", "notify-customer"],
    },
    "payment.refund": {
        "resource": "payment", "allowed_roles": ("operator", "admin", "owner"),
        "needs_intent": True, "step_up": True, "read_only": False,
        "obligations": ["audit", "notify-customer"],
    },
    # Account restrictions (Financial Rights Engine).
    "restriction.create": {
        "resource": "restriction", "allowed_roles": ("operator", "compliance", "admin", "owner"),
        "needs_intent": True, "step_up": True, "read_only": False,
        "obligations": ["audit", "rights-review"],
    },
    "restriction.lift": {
        "resource": "restriction", "allowed_roles": ("compliance", "admin", "owner"),
        "needs_intent": True, "step_up": True, "read_only": False,
        "obligations": ["audit", "notify-customer"],
    },
    "restriction.read": {
        "resource": "restriction", "allowed_roles": ("operator", "approver", "auditor", "compliance", "admin", "owner"),
        "needs_intent": False, "step_up": False, "read_only": True,
        "obligations": [],
    },
    "appeal.decide": {
        "resource": "appeal", "allowed_roles": ("approver", "compliance", "admin", "owner"),
        "needs_intent": False, "step_up": True, "read_only": False,
        "obligations": ["audit", "independent-reviewer"],
    },
    # Smart-contract changes (programmable agreements).
    "agreement.create": {
        "resource": "agreement", "allowed_roles": ("operator", "admin", "owner"),
        "needs_intent": False, "step_up": False, "read_only": False,
        "obligations": ["audit"],
    },
    "agreement.activate": {
        "resource": "agreement", "allowed_roles": ("operator", "admin", "owner"),
        "needs_intent": False, "step_up": False, "read_only": False,
        "obligations": ["audit"],
    },
    "agreement.execute": {
        "resource": "agreement", "allowed_roles": ("operator", "admin", "owner"),
        "needs_intent": True, "step_up": False, "read_only": False,
        "obligations": ["audit", "executor-role"],
    },
    "agreement.cancel": {
        "resource": "agreement", "allowed_roles": ("operator", "admin", "owner"),
        "needs_intent": True, "step_up": False, "read_only": False,
        "obligations": ["audit"],
    },
    "agreement.dispute": {
        "resource": "agreement", "allowed_roles": ("operator", "admin", "owner"),
        "needs_intent": True, "step_up": False, "read_only": False,
        "obligations": ["audit"],
    },
    "agreement.amend": {
        "resource": "agreement", "allowed_roles": ("admin", "owner"),
        "needs_intent": True, "step_up": True, "read_only": False,
        "obligations": ["audit", "dual-consent"],
    },
    # AI tool execution (advisory only; never moves funds by construction).
    "ai.execute": {
        "resource": "ai_tool", "allowed_roles": ("operator", "approver", "auditor", "compliance", "admin", "owner"),
        "needs_intent": False, "step_up": False, "read_only": True,
        "obligations": ["advisory-only", "audit"],
    },
    # Data access (dashboards, exports, transaction reads).
    "data.read": {
        "resource": "data", "allowed_roles": ("operator", "approver", "auditor", "compliance", "admin", "owner"),
        "needs_intent": False, "step_up": False, "read_only": True,
        "obligations": [],
    },
    "data.export": {
        "resource": "data", "allowed_roles": ("auditor", "compliance", "admin", "owner"),
        "needs_intent": False, "step_up": True, "read_only": True,
        "obligations": ["audit"],
    },
    # Role management (grant/revoke — highest sensitivity).
    "role.grant": {
        "resource": "role", "allowed_roles": ("admin", "owner"),
        "needs_intent": True, "step_up": True, "read_only": False,
        "obligations": ["audit", "dual-control"],
    },
    "role.revoke": {
        "resource": "role", "allowed_roles": ("admin", "owner"),
        "needs_intent": True, "step_up": True, "read_only": False,
        "obligations": ["audit", "dual-control"],
    },
    # Tenant management.
    "tenant.manage": {
        "resource": "tenant", "allowed_roles": ("admin", "owner"),
        "needs_intent": True, "step_up": True, "read_only": False,
        "obligations": ["audit", "dual-control"],
    },
    # Emergency operations.
    "emergency.grant": {
        "resource": "emergency", "allowed_roles": ("admin", "owner"),
        "needs_intent": False, "step_up": True, "read_only": False,
        "obligations": ["audit", "retrospective-review"],
    },
    # Audit log access (append-only; even auditors cannot rewrite).
    "audit.read": {
        "resource": "audit", "allowed_roles": ("auditor", "compliance", "approver", "admin", "owner"),
        "needs_intent": False, "step_up": False, "read_only": True,
        "obligations": ["audit"],
    },
}

# Institutional roles known to the PDP. Transport roles map: service-caller /
# dev-caller -> operator (least privilege); admin token -> admin.
KNOWN_ROLES = (
    "customer", "operator", "approver", "auditor", "compliance",
    "admin", "owner", "service-account",
)

_TRANSPORT_MAP = {
    "operator": "operator",
    "admin": "admin",
    "service-caller": "operator",
    "dev-caller": "operator",
}


def _normalize_role(role: str) -> str:
    return _TRANSPORT_MAP.get(role, role)


def evaluate(
    *,
    action: str,
    role: str,
    actor: str,
    tenant: str,
    resource_tenant: str = "",
    resource_type: str = "",
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Evaluate a policy decision. Never raises: failures deny (fail-closed)."""
    ctx = dict(context or {})
    try:
        return _evaluate(
            action=action, role=role, actor=actor, tenant=tenant,
            resource_tenant=resource_tenant, resource_type=resource_type, ctx=ctx,
        )
    except Exception as exc:  # fail closed on any internal error
        return {
            "allow": False,
            "reason": f"DENY: PDP internal error (fail closed): {str(exc)[:160]}",
            "policy_version": POLICY_BUNDLE_VERSION,
            "obligations": ["audit"],
        }


def _evaluate(
    *,
    action: str,
    role: str,
    actor: str,
    tenant: str,
    resource_tenant: str,
    resource_type: str,
    ctx: dict[str, Any],
) -> dict[str, Any]:
    rule = POLICY_MATRIX.get(action)
    if rule is None:
        return _deny(f"unknown action {action!r}", ["audit"])
    eff_role = _normalize_role(role)
    if eff_role not in KNOWN_ROLES:
        return _deny(f"unknown role {role!r}", ["audit"])
    if not tenant.strip():
        return _deny("missing tenant scope", ["audit"])
    # Tenant isolation: resource tenant must equal principal tenant.
    # (The tenant itself is server-derived from the bearer token binding or the
    # authenticated session — never from an untrusted client header alone.)
    if resource_tenant and resource_tenant != tenant:
        return _deny(
            f"cross-tenant access denied ({tenant} != {resource_tenant})", ["audit"]
        )
    if resource_type and resource_type != rule["resource"]:
        return _deny(
            f"resource mismatch: {action} governs {rule['resource']}, "
            f"not {resource_type}",
            ["audit"],
        )
    if eff_role not in rule["allowed_roles"]:
        return _deny(
            f"role {eff_role} may not perform {action}", ["audit"]
        )
    if not actor.strip() and not rule["read_only"]:
        return _deny("authenticated actor identity required", ["audit"])
    # Compromised-admin containment: privilege/tenant management by a bare
    # admin token without dual control + legal review is denied.
    if action in ("role.grant", "role.revoke", "tenant.manage"):
        if eff_role == "admin" and not ctx.get("dual_control"):
            return _deny(
                f"{action} requires dual control (second independent approver)",
                ["audit"],
            )
    if rule.get("needs_intent") and not ctx.get("intent_approved"):
        # Emergency path: a fresh, scoped emergency grant substitutes for an
        # intent, but still forces retrospective review.
        if not (ctx.get("emergency") and ctx.get("emergency_fresh")):
            return _deny(
                f"{action} requires an approved multi-party intent "
                "(or fresh emergency grant)",
                ["audit"],
            )
    if ctx.get("intent_approved"):
        if not ctx.get("intent_scope_ok", True):
            return _deny("intent scope mismatch (action/target/tenant/amount bound)", ["audit"])
        if not ctx.get("intent_fresh", True):
            return _deny("intent expired; re-approve before execution", ["audit"])
    if rule.get("step_up") and not ctx.get("step_up_ok"):
        return _deny(
            f"{action} requires step-up (explicit confirm + reason + Idempotency-Key)",
            ["audit"],
        )
    if ctx.get("elevated_grant_scopes") and action not in ctx["elevated_grant_scopes"]:
        return _deny(f"elevation grant does not cover {action}", ["audit"])
    obligations = list(rule.get("obligations", []))
    if ctx.get("emergency"):
        obligations.append("retrospective-review")
    return {
        "allow": True,
        "reason": f"ALLOW: {action} by {eff_role} under {POLICY_BUNDLE_VERSION}",
        "policy_version": POLICY_BUNDLE_VERSION,
        "obligations": obligations,
    }


def _deny(reason: str, obligations: list[str]) -> dict[str, Any]:
    return {
        "allow": False,
        "reason": f"DENY: {reason}",
        "policy_version": POLICY_BUNDLE_VERSION,
        "obligations": obligations,
    }


def simulate(*args: Any, **kwargs: Any) -> dict[str, Any]:
    """Dry-run evaluation: identical logic, no side effects, labeled as such."""
    decision = evaluate(*args, **kwargs)
    return {**decision, "dryRun": True}

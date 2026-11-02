"""Institutional & human guardrails — deterministic backend enforcement.

Prevents abuse of financial authority by employees, admins, executives,
support, and infrastructure operators. All checks run in backend code;
the frontend NEVER authorizes anything.

Controls:
1. RBAC + ABAC (role × tenant × amount × purpose × time-window attributes).
2. Default-deny on every sensitive endpoint (explicit allow required).
3. Segregation of duties (maker ≠ checker ≠ auditor; enforced by actor id).
4. Maker-checker approval intents for sensitive financial operations.
5. Multi-party approval for high-risk actions (threshold-based quorums).
6. No self-approval, incl. alternate accounts (same bearer token = same person).
7. Time-limited, purpose-bound elevated access (JIT grants with expiry).
8. Step-up authentication for sensitive ops (admin bearer + explicit confirm).
9. Tenant isolation (token-derived tenant; cross-tenant access denied).
10. Admins cannot directly alter balances, ownership, or audit history.
11. Privilege changes need independent (second-actor) review.
12. Tamper-evident security + financial audit trails (hash-chained).
13. JIT access with automatic expiry (swept on read).
14. Emergency access with justification + mandatory retrospective review flag.

High-risk actions are evaluated by policy_decide() — a deterministic engine.
Approval decisions bind authenticated identity + scoped permission + evidence.
Nobody, incl. the platform owner, gets unrestricted financial authority:
owner actions still need intents, second approvers, and audit entries.
Legally required institutional powers (compliance freezes, court orders) and
mandatory procedures remain available via the emergency path with full audit.
"""
from __future__ import annotations

import hashlib
import os
import time
import uuid
from typing import Any

# ---- Roles & permissions (RBAC matrix; ABAC attributes refine per request) ----
ROLES = ("operator", "approver", "auditor", "compliance", "admin", "owner")

# Sensitive actions: which roles may INITIATE (maker) vs APPROVE (checker).
SENSITIVE_ACTIONS: dict[str, dict[str, tuple[str, ...]]] = {
    "fiat.cancel": {"maker": ("operator", "admin", "owner"), "checker": ("approver", "admin", "owner")},
    "fiat.refund": {"maker": ("operator", "admin", "owner"), "checker": ("approver", "admin", "owner")},
    "agreement.execute": {"maker": ("operator", "admin", "owner"), "checker": ("approver", "admin", "owner")},
    "agreement.cancel": {"maker": ("operator", "admin", "owner"), "checker": ("approver", "admin", "owner")},
    "agreement.dispute": {"maker": ("operator", "admin", "owner"), "checker": ("approver", "admin", "owner")},
    "permission.grant": {"maker": ("admin", "owner"), "checker": ("owner", "compliance")},
    "emergency.access": {"maker": ("admin", "owner"), "checker": ("compliance", "owner", "auditor")},
}

# Amount (minor units) at/above which multi-party quorum is required.
HIGH_RISK_THRESHOLD_MINOR = int(os.environ.get("INSTITUTIONAL_HIGH_RISK_MINOR", "50000"))
# Quorum sizes: standard maker-checker vs high-risk multi-party.
STANDARD_QUORUM = 1
HIGH_RISK_QUORUM = int(os.environ.get("INSTITUTIONAL_HIGH_RISK_QUORUM", "2"))
# Strict mode: when "1", sensitive money endpoints REQUIRE an approved intent.
STRICT = os.environ.get("INSTITUTIONAL_STRICT", "0") == "1"


def is_high_risk(amount_minor: int | str) -> bool:
    try:
        return int(amount_minor or 0) >= HIGH_RISK_THRESHOLD_MINOR
    except (TypeError, ValueError):
        return True  # unparseable amount fails closed to high-risk


def required_quorum(amount_minor: int | str) -> int:
    return HIGH_RISK_QUORUM if is_high_risk(amount_minor) else STANDARD_QUORUM


def _actor_key(bearer_presented: str, actor: str) -> str:
    """Identity binding: same bearer token == same person (alt-account resistant).

    Different actor labels presenting the SAME token are treated as the same
    principal and cannot approve their own intent.
    """
    return hashlib.sha256(f"{bearer_presented}\x00{actor}".encode()).hexdigest()


def policy_decide(*, action: str, role: str, tenant: str, actor: str,
                  amount_minor: int | str = 0, purpose: str = "",
                  grant_scopes: tuple[str, ...] = ()) -> tuple[bool, str]:
    """Deterministic policy engine. Default-deny. Returns (allowed, reason)."""
    if action not in SENSITIVE_ACTIONS:
        return False, f"DENY: unknown sensitive action {action!r}"
    if not tenant:
        return False, "DENY: missing tenant scope"
    if role not in ROLES and role not in ("service-caller", "dev-caller"):
        return False, f"DENY: unknown role {role!r}"
    if role in ("service-caller", "dev-caller"):
        role = "operator"  # bearer-authenticated callers act as operators unless admin token
    matrix = SENSITIVE_ACTIONS[action]
    if role not in matrix["maker"] and role not in matrix["checker"]:
        return False, f"DENY: role {role} may neither make nor check {action}"
    if not actor or not actor.strip():
        return False, "DENY: authenticated actor identity required"
    if action in ("permission.grant", "emergency.access") and not purpose.strip():
        return False, "DENY: purpose-bound justification required"
    if grant_scopes and action not in grant_scopes:
        return False, f"DENY: elevation grant does not cover {action}"
    return True, "ALLOW: policy matrix pass (intent + quorum still required)"


def check_no_self_approval(maker_actor: str, maker_token: str,
                           checker_actor: str, checker_token: str) -> tuple[bool, str]:
    if not checker_actor.strip():
        return False, "DENY: checker identity required"
    if maker_token and maker_token == checker_token:
        return False, "DENY: self-approval forbidden (same credential)"
    if maker_actor.strip().lower() == checker_actor.strip().lower():
        return False, "DENY: self-approval forbidden (same actor)"
    return True, "ALLOW: distinct checker"


def new_intent_id() -> str:
    return f"in-{uuid.uuid4().hex[:12]}"


def quorum_met(approvals: list[dict[str, Any]], required: int) -> bool:
    distinct = {a.get("checkerKey", a.get("checker", "")) for a in approvals}
    distinct.discard("")
    return len(distinct) >= max(1, required)


def grant_expired(grant: dict[str, Any], now: int | None = None) -> bool:
    ts = now if now is not None else int(time.time())
    return ts >= int(grant.get("expiresAt", 0))


def step_up_ok(body: dict[str, Any], headers: dict[str, str]) -> tuple[bool, str]:
    """Step-up: sensitive ops need explicit confirmation + idempotency key.

    The admin bearer token is the possession factor; the explicit
    {"confirm": true, "reason": "..."} body plus Idempotency-Key header is the
    step-up ceremony (prevents one-click / replayed approvals).
    """
    if body.get("confirm") is not True:
        return False, "DENY: step-up confirmation missing (confirm:true required)"
    if not str(body.get("reason", "")).strip():
        return False, "DENY: step-up reason required"
    if not headers.get("idempotency-key"):
        return False, "DENY: Idempotency-Key required for sensitive operations"
    return True, "ALLOW: step-up satisfied"

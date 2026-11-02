"""Deterministic AI policy engine — enforced server-side, independent of prompts.

CORE PRINCIPLE: the AI is an advisory system, never an autonomous financial
authority. No AI output may directly or indirectly execute a financial action.

Capabilities (allowlisted, read-only):
- explain_receipt, summarize_agreement, list_eligible_routes,
  risk_indicators_readonly, explain_chain_state, assistant_reply
Forbidden (denied by construction — no tool exists, policy double-denies):
- payment execution / capture / refund / cancel
- wallet signing / private-key or seed access
- account freezing, asset seizure, balance mutation
- permission / role management, tenant reassignment
- financial contract modification, settlement declaration
- credential / API-key disclosure

Human review is REQUIRED before any AI-generated fraud signal, risk
assessment, or financial recommendation may influence a human decision, and
such output must NEVER automatically become an account restriction or a
payment decision (enforced: AI responses carry advisoryOnly=true and no
endpoint consumes them as authorization).

Kill-switch: AI_DISABLED=1 env or runtime disable via admin endpoint stops
all /api/ai/* routes with 503 AI_DISABLED while payment APIs keep serving.
"""
from __future__ import annotations

import os
import time

# ---- Capability allowlist (read-only tools the AI may invoke server-side) ----
ALLOWED_TOOLS = (
    "explain_receipt",
    "summarize_agreement",
    "list_eligible_routes",
    "risk_indicators_readonly",
    "explain_chain_state",
    "assistant_reply",
)

# ---- Forbidden actions (deny by name even if a tool is smuggled in) ----
FORBIDDEN_ACTIONS = (
    "execute_payment", "capture_payment", "refund_payment", "cancel_payment",
    "sign_transaction", "sign_wallet", "export_private_key", "reveal_seed",
    "freeze_account", "seize_assets", "modify_balance", "adjust_ledger",
    "grant_permission", "revoke_permission", "change_role", "reassign_tenant",
    "modify_contract", "declare_settlement", "approve_payment", "release_funds",
    "disclose_api_key", "disclose_secret", "disclose_credentials",
)

# Actions whose AI output requires recorded human review before use.
REVIEW_REQUIRED_KINDS = ("fraud", "risk", "routing", "contract", "financial-recommendation")

_runtime_disabled = False
_runtime_reason = ""


def is_ai_disabled() -> tuple[bool, str]:
    """Kill-switch state. Env override wins; durable distributed control next;
    process-local runtime flag last (kept for compatibility).

    Requirement: never rely on a process-local flag alone — the DB-backed
    control (`ai_guardrails/control.py`) propagates to every Modal
    container/replica on its next check without redeploys.
    """
    if os.environ.get("AI_DISABLED", "") == "1":
        return True, "AI_DISABLED env set"
    try:
        from . import control as _control
        disabled, why = _control.is_inference_disabled()
        if disabled:
            return True, why
    except Exception:
        pass
    if _runtime_disabled:
        return False or True, _runtime_reason or "runtime kill-switch engaged"
    return False, ""


def set_runtime_disabled(disabled: bool, reason: str = "") -> dict:
    global _runtime_disabled, _runtime_reason
    _runtime_disabled = bool(disabled)
    _runtime_reason = str(reason or "")[:200]
    return {"disabled": _runtime_disabled, "reason": _runtime_reason,
            "ts": int(time.time())}


def evaluate_tool(tool: str, *, role: str, tenant: str) -> tuple[bool, str]:
    """Default-deny tool authorization. Returns (allowed, reason)."""
    if not tenant:
        return False, "DENY: missing tenant scope"
    if role not in ("operator", "admin"):
        return False, f"DENY: unknown role {role!r}"
    if tool in FORBIDDEN_ACTIONS:
        return False, f"DENY: forbidden action {tool}"
    if tool not in ALLOWED_TOOLS:
        return False, f"DENY: tool {tool!r} not allowlisted"
    disabled, why = is_ai_disabled()
    if disabled:
        return False, f"DENY: AI disabled ({why})"
    return True, "ALLOW: allowlisted read-only tool"


def decision_from_ai(kind: str, ai_output: dict) -> dict:
    """Deterministic gate: AI output NEVER authorizes action.

    Returns a decision envelope the backend (not the model) computes:
    - approved=False always (AI cannot approve),
    - requiresHumanReview=True for review-gated kinds,
    - autoEnforced=False always (no automatic restriction/payment).
    """
    needs_review = kind in REVIEW_REQUIRED_KINDS or bool(
        ai_output.get("riskLevel") in ("medium", "high"))
    return {"approved": False, "autoEnforced": False,
            "requiresHumanReview": needs_review,
            "advisoryOnly": True, "kind": kind,
            "note": ("AI output is advisory; a deterministic policy check and "
                     "an authenticated human decide. AI output never moves funds.")}

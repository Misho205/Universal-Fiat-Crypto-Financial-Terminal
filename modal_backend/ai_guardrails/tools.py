"""Allowlisted, least-privilege, read-only tools for the AI.

The model never touches payments, wallets, permissions, or contracts.
Each tool is a pure read function over already-authorized data passed in by
the backend route (which already enforced bearer auth + tenant scope).
Server-side permission is re-checked here via policy.evaluate_tool —
a smuggled tool name fails closed even if prompt text asks for it.
"""
from __future__ import annotations

from typing import Any

from . import policy
from .audit import log_security_event


def _ok(tool: str, data: dict[str, Any]) -> dict[str, Any]:
    return {"tool": tool, "data": data, "advisoryOnly": True, "authoritative": False}


def explain_receipt(receipt: dict[str, Any], *, role: str, tenant: str) -> dict[str, Any]:
    allowed, reason = policy.evaluate_tool("explain_receipt", role=role, tenant=tenant)
    if not allowed:
        log_security_event("ai.tool.denied", tool="explain_receipt", reason=reason, tenant=tenant)
        raise PermissionError(reason)
    amt = str(receipt.get("amountMinor", "?"))
    return _ok("explain_receipt", {"summary": f"Sandbox receipt: {amt} minor units (test funds only).",
                                   "state": str(receipt.get("state", "unknown"))})


def summarize_agreement(agreement: dict[str, Any], *, role: str, tenant: str) -> dict[str, Any]:
    allowed, reason = policy.evaluate_tool("summarize_agreement", role=role, tenant=tenant)
    if not allowed:
        log_security_event("ai.tool.denied", tool="summarize_agreement", reason=reason, tenant=tenant)
        raise PermissionError(reason)
    return _ok("summarize_agreement", {"state": str(agreement.get("state", "unknown")),
                                       "note": "Eligibility and execution are separate; human executor required."})


def list_eligible_routes(context: dict[str, Any], *, role: str, tenant: str) -> dict[str, Any]:
    allowed, reason = policy.evaluate_tool("list_eligible_routes", role=role, tenant=tenant)
    if not allowed:
        log_security_event("ai.tool.denied", tool="list_eligible_routes", reason=reason, tenant=tenant)
        raise PermissionError(reason)
    void = context  # context scopes the answer; never authorizes anything
    assert void is not None
    return _ok("list_eligible_routes",
               {"routes": ["sandbox-fiat", "sepolia-evm", "REVIEW_REQUIRED"],
                "note": "Deterministic eligibility decides; AI only phrases."})


def risk_indicators_readonly(tx: dict[str, Any], *, role: str, tenant: str) -> dict[str, Any]:
    allowed, reason = policy.evaluate_tool("risk_indicators_readonly", role=role, tenant=tenant)
    if not allowed:
        log_security_event("ai.tool.denied", tool="risk_indicators_readonly", reason=reason, tenant=tenant)
        raise PermissionError(reason)
    void = tx
    assert void is not None
    return _ok("risk_indicators_readonly",
               {"indicators": [], "riskLevel": "high",
                "notice": "Heuristic only, NOT certified fraud detection; human review required."})


def explain_chain_state(snapshot: dict[str, Any], *, role: str, tenant: str) -> dict[str, Any]:
    allowed, reason = policy.evaluate_tool("explain_chain_state", role=role, tenant=tenant)
    if not allowed:
        log_security_event("ai.tool.denied", tool="explain_chain_state", reason=reason, tenant=tenant)
        raise PermissionError(reason)
    return _ok("explain_chain_state", {"state": str(snapshot.get("state", "unknown")),
                                       "note": "Confirmed != settled; settlement is a separate business step."})


def assistant_reply(topic: str, *, role: str, tenant: str) -> dict[str, Any]:
    allowed, reason = policy.evaluate_tool("assistant_reply", role=role, tenant=tenant)
    if not allowed:
        log_security_event("ai.tool.denied", tool="assistant_reply", reason=reason, tenant=tenant)
        raise PermissionError(reason)
    return _ok("assistant_reply", {"topic": topic, "actions": ["read-docs", "open-simulator"]})


TOOLS = {"explain_receipt": explain_receipt, "summarize_agreement": summarize_agreement,
         "list_eligible_routes": list_eligible_routes,
         "risk_indicators_readonly": risk_indicators_readonly,
         "explain_chain_state": explain_chain_state, "assistant_reply": assistant_reply}


def invoke_tool(name: str, args: dict[str, Any], *, role: str, tenant: str) -> dict[str, Any]:
    """Single server-side entry point for any AI tool call. Default-deny.

    Authorization is enforced AGAIN here at execution time (not just at the
    HTTP route): role/tenant allowlist, kill-switch, tool-execution switch,
    and the control-plane generation. A disable/permission-revocation that
    lands between request admission and execution invalidates the call —
    closing the TOCTOU race for queued or concurrent tool actions.
    """
    from . import control as _control
    from . import policy as _policy
    allowed, reason = _policy.evaluate_tool(name, role=role, tenant=tenant)
    if not allowed:
        log_security_event("ai.tool.denied", tool=str(name)[:80],
                           reason=reason, tenant=tenant)
        raise PermissionError(f"DENY: {reason}")
    tools_ok, tools_why = _control.are_tools_enabled()
    if not tools_ok:
        log_security_event("ai.tool.denied", tool=str(name)[:80],
                           reason=tools_why, tenant=tenant)
        raise PermissionError(f"DENY: {tools_why} (generation {_control.generation()})")
    fn = TOOLS.get(name)
    if fn is None:
        log_security_event("ai.tool.denied", tool=str(name)[:80],
                           reason="DENY: unknown tool", tenant=tenant)
        raise PermissionError(f"DENY: tool {name!r} not allowlisted")
    return fn(args, role=role, tenant=tenant)

"""Deterministic programmable fiat payment agreement engine (sandbox only).

LEGAL BOUNDARIES (enforced in responses, never just docs):
- An agreement is a conditional *instruction set*, NOT a regulated escrow service.
- The engine never claims funds are reserved, held, or guaranteed. Only the
  payment provider's own confirmed capability counts, and it is quoted verbatim.
- Settlement is never simulated as a real transfer: execution calls the fiat
  sandbox provider (mock or Stripe TEST) and reports the provider's answer.
- No custody, no money transmission: the backend moves no funds; it authorizes
  provider calls only when the agreement is eligible AND a human authorized.
- AI output can never become an executable condition: every condition passes the
  allowlist validator + explicit human acceptance (see validate_creation).

States: draft -> active -> conditions_pending -> eligible_for_execution ->
completed | canceled | expired | disputed.
"""
from __future__ import annotations

import hashlib
import json
import time
import uuid
from typing import Any, Literal

from . import config

STATES = ("draft", "active", "conditions_pending", "eligible_for_execution",
          "completed", "canceled", "expired", "disputed")

ALLOWED_CONDITIONS = {"timeCondition", "deliveryConfirmation", "partyApproval",
                      "approvalThreshold", "externalEvent"}
ALLOWED_EXECUTION = {"pay-after-condition", "auth-capture"}
ALLOWED_ACTIONS = {"create", "activate", "approve", "submit-evidence", "execute", "cancel", "dispute"}

ConditionStatus = Literal["met", "unmet", "invalid"]

DISCLOSURE = ("Not an escrow service: no funds are reserved, held, or guaranteed by this engine. "
              "Execution only calls the configured sandbox payment provider; the provider's own "
              "response is authoritative. Sandbox only — no real transfer.")


def validate_creation(terms: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    amount = terms.get("amountMinor", "")
    if not (isinstance(amount, str) and amount.isdigit()):
        errors.append("amount must be integer minor units string")
    currency = terms.get("currency", "EUR")
    if not (isinstance(currency, str) and len(currency) == 3 and currency.isupper()):
        errors.append("currency must be ISO 4217 code")
    parties = terms.get("parties", [])
    if not (isinstance(parties, list) and 2 <= len(parties) <= 8 and all(isinstance(p, str) and p for p in parties)):
        errors.append("parties must list 2..8 named parties")
    for cond in terms.get("conditions", []) or []:
        ctype = cond.get("type")
        if ctype not in ALLOWED_CONDITIONS:
            errors.append(f"disallowed condition: {ctype} (AI drafts must pass this validator)")
        if ctype == "approvalThreshold":
            approvers, th = cond.get("approvers", []), cond.get("threshold", 0)
            if not (isinstance(approvers, list) and 1 <= th <= len(approvers)):
                errors.append("approvalThreshold: threshold out of range")
        if ctype == "timeCondition":
            nb, na = cond.get("notBefore"), cond.get("notAfter")
            if nb and na and nb >= na:
                errors.append("timeCondition window invalid")
        if ctype == "externalEvent":
            if not cond.get("source") or not cond.get("eventId"):
                errors.append("externalEvent requires authenticated source + eventId")
    if terms.get("executionModel") not in ALLOWED_EXECUTION:
        errors.append(f"executionModel must be one of {sorted(ALLOWED_EXECUTION)}")
    exp = terms.get("expiresAt", "")
    if not exp:
        errors.append("expiresAt is required (ISO-8601)")
    if terms.get("custodyClaim"):
        errors.append("custody claims forbidden: engine holds no funds")
    return errors


def evaluate_condition(cond: dict[str, Any], evidence: dict[str, Any], now_iso: str) -> ConditionStatus:
    """Pure deterministic evaluator. Evidence from authenticated sources only —
    callers must authenticate the source before passing evidence in."""
    ctype = cond.get("type")
    if ctype == "timeCondition":
        nb, na = cond.get("notBefore", ""), cond.get("notAfter", "")
        if nb and now_iso < nb:
            return "unmet"
        if na and now_iso >= na:
            return "unmet"
        return "met"
    if ctype == "deliveryConfirmation":
        ref = cond.get("deliveryRef", "")
        confirmed = (evidence.get("deliveries", {}) or {}).get(ref, {})
        return "met" if confirmed.get("confirmedByAuthenticatedSource") is True else "unmet"
    if ctype == "partyApproval":
        party = cond.get("party", "")
        return "met" if party in (evidence.get("approvals", []) or []) else "unmet"
    if ctype == "approvalThreshold":
        approvers = set(cond.get("approvers", []))
        given = set(evidence.get("approvals", []) or [])
        return "met" if len(approvers & given) >= int(cond.get("threshold", 999)) else "unmet"
    if ctype == "externalEvent":
        key = f"{cond.get('source')}:{cond.get('eventId')}"
        seen = (evidence.get("externalEvents", {}) or {}).get(key, {})
        if not seen.get("authenticated"):
            return "unmet"
        exp = seen.get("expiry", "")
        if exp and now_iso >= exp:
            return "invalid"
        return "met"
    return "invalid"


def evaluate_all(terms: dict[str, Any], evidence: dict[str, Any], now_iso: str) -> dict[str, ConditionStatus]:
    return {f"{c.get('type')}:{i}": evaluate_condition(c, evidence, now_iso)
            for i, c in enumerate(terms.get("conditions", []) or [])}


def all_met(statuses: dict[str, ConditionStatus]) -> bool:
    return bool(statuses) and all(v == "met" for v in statuses.values())


# ---------- state machine with authorization ----------

_TRANSITIONS: dict[str, set[str]] = {
    "draft": {"active", "canceled"},
    "active": {"conditions_pending", "canceled", "expired", "disputed"},
    "conditions_pending": {"eligible_for_execution", "conditions_pending", "canceled", "expired", "disputed"},
    "eligible_for_execution": {"completed", "canceled", "expired", "disputed"},
    "completed": set(),
    "canceled": set(),
    "expired": set(),
    "disputed": {"canceled", "eligible_for_execution"},
}

# which roles may trigger which target state
_ROLE_ALLOW: dict[str, set[str]] = {
    "active": {"creator"},
    "conditions_pending": {"system", "creator", "executor"},
    "eligible_for_execution": {"system"},
    "completed": {"executor"},
    "canceled": {"creator", "approver"},
    "expired": {"system"},
    "disputed": {"creator", "approver", "executor", "party"},
}


def can_transition(frm: str, to: str, actor_role: str) -> tuple[bool, str]:
    if to not in _TRANSITIONS.get(frm, set()):
        return False, f"illegal transition {frm}->{to}"
    if actor_role not in _ROLE_ALLOW.get(to, set()):
        return False, f"role {actor_role} may not move to {to}"
    return True, ""


def new_agreement(tenant: str, creator: str, terms: dict[str, Any]) -> dict[str, Any]:
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    ag_id = f"pag-{uuid.uuid4().hex[:12]}"
    genesis = {"seq": 0, "at": now, "actor": creator, "action": "create",
               "state": "draft", "prevHash": "GENESIS"}
    genesis["hash"] = _event_hash(ag_id, genesis)
    return {"id": ag_id, "tenant": tenant, "version": 1, "state": "draft",
            "terms": terms, "evidence": {"approvals": [], "deliveries": {}, "externalEvents": {}},
            "createdBy": creator, "createdAt": now, "updatedAt": now, "history": [genesis],
            "disclosure": DISCLOSURE}


def _event_hash(ag_id: str, event: dict[str, Any]) -> str:
    payload = json.dumps({"ag": ag_id, "seq": event["seq"], "at": event["at"],
                          "actor": event["actor"], "action": event["action"],
                          "state": event["state"], "prev": event["prevHash"]}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


def append_event(ag: dict[str, Any], actor: str, action: str, to_state: str) -> dict[str, Any]:
    if action not in ALLOWED_ACTIONS and action != "evaluate":
        raise ValueError(f"unknown action {action}")
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    prev = ag["history"][-1]["hash"] if ag["history"] else "GENESIS"
    ev = {"seq": len(ag["history"]), "at": now, "actor": actor, "action": action,
          "state": to_state, "prevHash": prev}
    ev["hash"] = _event_hash(ag["id"], ev)
    ag["history"].append(ev)
    ag["state"] = to_state
    ag["updatedAt"] = now
    return ev


def verify_chain(ag: dict[str, Any]) -> bool:
    prev = "GENESIS"
    for ev in ag.get("history", []):
        if ev.get("prevHash") != prev:
            return False
        if ev.get("hash") != _event_hash(ag["id"], ev):
            return False
        prev = ev["hash"]
    return True


def check_expiry(ag: dict[str, Any], now_iso: str) -> bool:
    exp = (ag.get("terms", {}) or {}).get("expiresAt", "")
    return bool(exp) and now_iso >= exp


def assert_sandbox_execution() -> None:
    config.assert_sandbox()

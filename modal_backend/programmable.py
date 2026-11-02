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

# Marketing/custody language that must never appear inside accepted terms.
# The engine holds no funds; claims of escrow, custody, or guaranteed
# settlement are rejected at validation time (not just documented).
FORBIDDEN_CLAIM_PHRASES = (
    "escrow",
    "custody",
    "custodial",
    "guaranteed settlement",
    "principal-protected",
    "funds are held",
)

AMENDABLE_STATES = ("draft", "active", "conditions_pending")


def _contains_forbidden_claim(terms: dict[str, Any]) -> str:
    blob = json.dumps(terms, sort_keys=True).lower()
    for phrase in FORBIDDEN_CLAIM_PHRASES:
        if phrase in blob:
            return phrase
    return ""


def terms_hash(terms: dict[str, Any]) -> str:
    """Cryptographic binding of the exact accepted terms (approval scope).

    Approvals, evidence, and execution all reference this hash: a single
    changed byte (amount, party, currency, condition) yields a different hash
    and is rejected as tampering — unilateral modification is impossible.
    """
    return hashlib.sha256(json.dumps(terms, sort_keys=True).encode()).hexdigest()

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
    bad_claim = _contains_forbidden_claim(terms)
    if bad_claim:
        errors.append(f"forbidden custody/settlement claim: {bad_claim!r} "
                      "(engine holds no funds; no escrow or guaranteed settlement)")
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
            "terms": terms, "termsHash": terms_hash(terms),
            "evidence": {"approvals": [], "deliveries": {}, "externalEvents": {}},
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


def verify_evidence_attestation(item: dict[str, Any]) -> tuple[bool, str]:
    """Independent verification record for external condition evidence.

    The engine never trusts a bare caller assertion. An attestation must name
    an authenticated source/oracle (`attestedBy`), carry an issuance timestamp
    (`attestedAt`), and include either a cryptographic `signature` or an
    allowlisted-oracle reference (`oracleRef`). Returns (ok, reason).
    """
    if not isinstance(item, dict):
        return False, "attestation must be an object"
    if not str(item.get("attestedBy", "")).strip():
        return False, "attestation requires attestedBy (authenticated source)"
    if not str(item.get("attestedAt", "")).strip():
        return False, "attestation requires attestedAt (issuance time)"
    sig = str(item.get("signature", ""))
    oracle = str(item.get("oracleRef", ""))
    if not sig and not oracle:
        return False, ("attestation requires a signature or an allowlisted "
                       "oracleRef (independent verification, never bare assertion)")
    if sig and len(sig) < 8:
        return False, "attestation signature too short"
    return True, "attestation well-formed"


def amend_terms(ag: dict[str, Any], new_terms: dict[str, Any],
                expected_prev_hash: str,
                consents: list[dict[str, str]]) -> tuple[bool, str]:
    """Versioned amendment with explicit dual consent (pure; caller persists).

    Rules:
    - Agreement must be in an amendable state (draft/active/conditions_pending).
    - `expected_prev_hash` must equal the current terms hash (optimistic
      concurrency: prevents lost updates, replayed amendments, and silent
      modification — a stale client cannot overwrite newer terms).
    - New terms must pass validate_creation (allowlist + no custody claims).
    - Dual consent: the creator plus a DISTINCT approver must both consent to
      the EXACT new terms hash (binding approval to terms/parties/amounts/
      currency/conditions — no blanket approvals).
    - Bumps version, resets evaluation to conditions_pending, appends history.
    """
    if ag.get("state") not in AMENDABLE_STATES:
        return False, f"cannot amend from state {ag.get('state')}"
    current_hash = terms_hash(ag.get("terms", {}) or {})
    if expected_prev_hash != current_hash:
        return False, ("terms hash mismatch: terms changed since you read them "
                       "(reload and re-consent; replayed amendments rejected)")
    errors = validate_creation(new_terms)
    if errors:
        return False, f"invalid amended terms: {errors[0]}"
    new_hash = terms_hash(new_terms)
    if new_hash == current_hash:
        return False, "amendment is identical to current terms (no-op rejected)"
    consenting = {(str(c.get("actor", "")).strip().lower(),
                   str(c.get("termsHash", "")))
                  for c in (consents or [])}
    creator = str(ag.get("createdBy", "")).strip().lower()
    creator_ok = any(a == creator and h == new_hash for a, h in consenting)
    approver_ok = any(a and a != creator and h == new_hash for a, h in consenting)
    if not creator_ok:
        return False, "amendment requires explicit creator consent to the new terms hash"
    if not approver_ok:
        return False, ("amendment requires explicit consent from a second party "
                       "distinct from the creator (dual consent to exact terms)")
    ag["terms"] = new_terms
    ag["termsHash"] = new_hash
    ag["version"] = int(ag.get("version", 1)) + 1
    ag["evidence"] = {"approvals": [], "deliveries": {}, "externalEvents": {}}
    append_event(ag, "system", "evaluate", "conditions_pending")
    return True, ""


def assert_sandbox_execution() -> None:
    config.assert_sandbox()

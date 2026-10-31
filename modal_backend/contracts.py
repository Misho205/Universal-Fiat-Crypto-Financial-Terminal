"""Conditional-payment agreement validation (Python port of packages/agreements).

Typed allowlist DSL only: timeCondition, externalEvent, partyApproval,
approvalThreshold, milestone, disputeWindow. No eval. AI output is NEVER
authoritative — it must pass this validator plus explicit human acceptance.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Literal

ConditionType = Literal["timeCondition", "externalEvent", "partyApproval", "approvalThreshold", "milestone", "disputeWindow"]
ALLOWED_CONDITIONS = {"timeCondition", "externalEvent", "partyApproval", "approvalThreshold", "milestone", "disputeWindow"}
ALLOWED_EXECUTION = {"pay-after-condition", "auth-capture"}


def validate_terms(terms: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    amount = terms.get("amountMinor", "")
    if not (isinstance(amount, str) and amount.isdigit()):
        errors.append("amount must be integer minor units string")
    beneficiaries = terms.get("beneficiaries", [])
    if sum(b.get("shareBps", 0) for b in beneficiaries) != 10000:
        errors.append("beneficiary shares must sum to 10000 bps")
    for cond in terms.get("conditions", []):
        ctype = cond.get("type")
        if ctype not in ALLOWED_CONDITIONS:
            errors.append(f"disallowed condition: {ctype}")
        if ctype == "approvalThreshold":
            approvers = cond.get("approvers", [])
            threshold = cond.get("threshold", 0)
            if not (1 <= threshold <= len(approvers)):
                errors.append("threshold out of range")
        if ctype == "timeCondition":
            nb, na = cond.get("notBefore"), cond.get("notAfter")
            if nb and na and nb >= na:
                errors.append("timeCondition window invalid")
    if terms.get("executionModel") == "approved-payout-product":
        errors.append("REVIEW: approved-payout-product needs licensed escrow product (unavailable)")
    if terms.get("executionModel") not in ALLOWED_EXECUTION and terms.get("executionModel") != "approved-payout-product":
        errors.append("unknown executionModel")
    return errors


def version_hash(terms: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(terms, sort_keys=True).encode()).hexdigest()


def indexed_amount(base_minor: int, base_index: float, eligible_index: float) -> int:
    """raw = base * eligible / base on comparable positive index LEVELS."""
    if not (base_index > 0 and eligible_index > 0):
        raise ValueError("INVALID_INDEX_LEVEL")
    # Integer-leaning: scale levels by 1e6 to avoid float money.
    scaled = (base_minor * round(eligible_index * 1_000_000)) // round(base_index * 1_000_000)
    return int(scaled)

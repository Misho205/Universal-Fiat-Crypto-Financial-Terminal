"""Financial Rights models: categories, grounds, reason codes, restriction types.

Every sensitive account restriction MUST carry:
- category: which family of interference (voluntary / fraud / contractual /
  legal-order / regulatory).
- ground: the explicit legal or contractual basis.
- reason_code: machine-readable code from the allowlist below.
- evidence: references supporting the action (never the AI score alone).
- scope: least-restrictive scope (account / instrument / amount-limited).
- expires_at + review_at: time limits and review deadlines.
"""
from __future__ import annotations

# Restriction families. The engine treats each differently for notification,
# review urgency, and expiry defaults.
CATEGORIES = (
    "voluntary_control",      # user asked for it (self-freeze, limits)
    "fraud_prevention",       # temporary protective hold, evidence-based
    "contractual",            # agreement terms explicitly allow it
    "legal_order",            # court order, sanctions listing, binding authority act
    "regulatory_obligation",  # AML/CFT or regulator-mandated measure
)

# Explicit legal/contractual grounds. Unknown grounds are rejected (default-deny).
GROUNDS = (
    "USER_REQUEST",
    "FRAUD_SUSPICION",
    "CONTRACT_TERMS",
    "AML_CTF",
    "SANCTIONS",
    "COURT_ORDER",
    "REGULATOR_ORDER",
    "RISK_LIMIT",
)

# Ground -> allowed categories (a ground cannot be filed under a wrong family).
GROUND_CATEGORY: dict[str, str] = {
    "USER_REQUEST": "voluntary_control",
    "FRAUD_SUSPICION": "fraud_prevention",
    "CONTRACT_TERMS": "contractual",
    "AML_CTF": "regulatory_obligation",
    "SANCTIONS": "legal_order",
    "COURT_ORDER": "legal_order",
    "REGULATOR_ORDER": "regulatory_obligation",
    "RISK_LIMIT": "contractual",
}

# Mandatory reason codes (allowlist). Free-text reasons are stored alongside
# for humans but NEVER substitute for a code.
REASON_CODES = (
    "USER_FREEZE_REQUEST",
    "USER_LIMIT_REQUEST",
    "FRAUD_SUSPECT_HOLD",
    "ACCOUNT_TAKEOVER_HOLD",
    "CONTRACT_CONDITION_UNMET",
    "CONTRACT_RISK_LIMIT",
    "AML_CTF_HOLD",
    "AML_CTF_REVIEW",
    "SANCTIONS_MATCH",
    "COURT_ORDER_FREEZE",
    "REGULATOR_ORDER_HOLD",
    "ACCOUNT_SECURITY_HOLD",
)

# Reason code -> ground (each code is valid for exactly one ground).
REASON_GROUND: dict[str, str] = {
    "USER_FREEZE_REQUEST": "USER_REQUEST",
    "USER_LIMIT_REQUEST": "USER_REQUEST",
    "FRAUD_SUSPECT_HOLD": "FRAUD_SUSPICION",
    "ACCOUNT_TAKEOVER_HOLD": "FRAUD_SUSPICION",
    "CONTRACT_CONDITION_UNMET": "CONTRACT_TERMS",
    "CONTRACT_RISK_LIMIT": "RISK_LIMIT",
    "AML_CTF_HOLD": "AML_CTF",
    "AML_CTF_REVIEW": "AML_CTF",
    "SANCTIONS_MATCH": "SANCTIONS",
    "COURT_ORDER_FREEZE": "COURT_ORDER",
    "REGULATOR_ORDER_HOLD": "REGULATOR_ORDER",
    "ACCOUNT_SECURITY_HOLD": "FRAUD_SUSPICION",
}

# Restriction types, ordered least-restrictive first (proportionality ladder).
RESTRICTION_TYPES = (
    "spend_limit",       # cap amounts, account otherwise usable
    "instrument_hold",   # block one instrument/rail, rest usable
    "outbound_freeze",   # block outgoing only, inbound allowed
    "full_freeze",       # block all movement (most restrictive)
)

# Grounds that are per se legal orders (court/sanctions/AML-grade authority).
LEGAL_ORDERS = ("SANCTIONS", "COURT_ORDER", "AML_CTF", "REGULATOR_ORDER")

# Grounds where disclosure to the customer may be prohibited by law
# (tipping-off / gag). Disclosure is decided per-case by disclosure_allowed().
NON_DISCLOSABLE_GROUNDS = ("SANCTIONS", "AML_CTF", "COURT_ORDER")

# Grounds for which the engine must NEVER auto-expire silently without review.
NO_SILENT_EXPIRY = ("SANCTIONS", "COURT_ORDER", "AML_CTF", "REGULATOR_ORDER")


def disclosure_allowed(ground: str, gag_order: bool) -> bool:
    """Whether the customer may be notified of the restriction.

    Legal-order grounds with an active gag order MUST NOT be disclosed.
    Voluntary controls and contractual restrictions are always disclosable.
    Fraud-prevention holds are disclosable in generic terms (no tactics).
    """
    if gag_order:
        return False
    if ground in NON_DISCLOSABLE_GROUNDS:
        return False
    return True


def less_restrictive_than(a: str, b: str) -> bool:
    """True when restriction type `a` is less restrictive than `b`."""
    order = {name: i for i, name in enumerate(RESTRICTION_TYPES)}
    return order.get(a, 99) < order.get(b, 99)

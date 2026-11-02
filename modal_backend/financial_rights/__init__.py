"""Financial Rights Protection Engine (sandbox only).

Protects users and institutions against arbitrary, unauthorized, discriminatory,
or disproportionate interference with lawful financial activity.

What this package does:
- Requires explicit legal/contractual grounds + mandatory reason codes + evidence
  for every sensitive account restriction.
- Distinguishes voluntary user controls, fraud prevention, contractual
  restrictions, legal orders, and regulatory obligations.
- Enforces proportionality (least-restrictive means), time limits, review
  deadlines, and expiration.
- Blocks AI-generated risk scores from becoming automatic punitive actions.
- Provides independent review, customer notification (when legally permitted),
  appeals, correction, and restoration workflows.
- Detects employee-abuse patterns (repeated/unjustified restrictions).

What this package does NOT do (by design):
- No universal prohibition of lawful AML/CFT measures, sanctions, court orders,
  or legally mandated restrictions — those remain available with full audit.
- No automatic disclosure when disclosure is prohibited by law (gag orders).
- No bypass of legally required compliance checks.
- No claim to determine legal rights conclusively (AI or otherwise): the engine
  enforces *procedure* (grounds, evidence, review, expiry), never a final legal
  verdict. Qualified human legal review is required before enabling
  jurisdiction-specific enforcement policies.

Sandbox only. No real money movement. See FINANCIAL_RIGHTS_POLICY.md.
"""
from __future__ import annotations

from .appeals import (
    APPEAL_STATES,
    correction_plan,
    decide_appeal,
    new_appeal,
    restoration_steps,
    transition_appeal,
)
from .engine import (
    authorize_restriction,
    check_expiry,
    correction_required,
    new_restriction,
)
from .jurisdictions import (
    JURISDICTIONS,
    get_jurisdiction,
    jurisdiction_requires_legal_review,
)
from .models import (
    CATEGORIES,
    GROUNDS,
    LEGAL_ORDERS,
    REASON_CODES,
    RESTRICTION_TYPES,
    disclosure_allowed,
)
from .monitoring import detect_abuse_patterns

__all__ = [
    "APPEAL_STATES",
    "CATEGORIES",
    "GROUNDS",
    "JURISDICTIONS",
    "LEGAL_ORDERS",
    "REASON_CODES",
    "RESTRICTION_TYPES",
    "authorize_restriction",
    "check_expiry",
    "correction_plan",
    "correction_required",
    "decide_appeal",
    "detect_abuse_patterns",
    "disclosure_allowed",
    "get_jurisdiction",
    "jurisdiction_requires_legal_review",
    "new_appeal",
    "new_restriction",
    "restoration_steps",
    "transition_appeal",
]

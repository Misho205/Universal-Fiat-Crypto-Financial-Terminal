"""Configurable jurisdiction-specific compliance policies.

A jurisdiction profile sets maximum restriction durations, review cadence, and
notification defaults. ENABLING a jurisdiction for enforcement requires a
qualified legal review record (reviewer, date, memo) — the engine refuses to
activate a profile without it. This prevents engineers from switching on
half-understood local enforcement by flipping a string.

Sandbox note: profiles encode *procedural* parameters (durations, review
roles), never conclusive legal interpretation. The system must not claim to
determine legal rights conclusively; see FINANCIAL_RIGHTS_POLICY.md.
"""
from __future__ import annotations

from typing import Any

# Default procedural parameters per jurisdiction profile.
JURISDICTIONS: dict[str, dict[str, Any]] = {
    "EU_GENERIC": {
        "id": "EU_GENERIC",
        "label": "EU generic (PSD2/GDPR baseline, sandbox defaults)",
        "max_restriction_sec": {
            "voluntary_control": 365 * 86400,
            "fraud_prevention": 72 * 3600,
            "contractual": 90 * 86400,
            "legal_order": 365 * 86400,
            "regulatory_obligation": 180 * 86400,
        },
        "default_review_sec": 30 * 86400,
        "notes": (
            "Fraud holds are short-lived by default and must be reviewed or "
            "released; legal/regulatory measures follow the issuing authority."
        ),
    },
    "BG": {
        "id": "BG",
        "label": "Bulgaria (EU member; BNB supervision; sandbox parameters)",
        "max_restriction_sec": {
            "voluntary_control": 365 * 86400,
            "fraud_prevention": 72 * 3600,
            "contractual": 90 * 86400,
            "legal_order": 365 * 86400,
            "regulatory_obligation": 180 * 86400,
        },
        "default_review_sec": 14 * 86400,
        "notes": (
            "Sandbox parameters only. Production use requires qualified Bulgarian "
            "legal review (consumer protection, BNB ordinances, GDPR, fiscal rules)."
        ),
    },
}

# In-memory legal-review registry: jurisdiction -> review record.
# (Durable deployments persist this alongside policy bundles with dual control;
# the sandbox keeps it in process memory + audit log.)
_legal_reviews: dict[str, dict[str, str]] = {}


def get_jurisdiction(jurisdiction_id: str) -> dict[str, Any]:
    cfg = JURISDICTIONS.get(jurisdiction_id)
    if cfg is None:
        raise KeyError(
            f"unknown jurisdiction {jurisdiction_id!r}; "
            f"available: {sorted(JURISDICTIONS)}"
        )
    return cfg


def record_legal_review(
    jurisdiction_id: str, *, reviewer: str, date: str, memo: str
) -> dict[str, str]:
    """Record qualified legal review enabling a jurisdiction profile."""
    _ = get_jurisdiction(jurisdiction_id)  # raises on unknown id
    if not reviewer.strip() or not memo.strip() or not date.strip():
        raise ValueError("legal review requires reviewer, date, and memo")
    rec = {"reviewer": reviewer.strip(), "date": date.strip(), "memo": memo.strip()[:1000]}
    _legal_reviews[jurisdiction_id] = rec
    return rec


def jurisdiction_requires_legal_review(jurisdiction_id: str) -> bool:
    """True when the jurisdiction still lacks a recorded qualified legal review."""
    _ = get_jurisdiction(jurisdiction_id)
    return jurisdiction_id not in _legal_reviews


def require_legal_review(jurisdiction_id: str) -> None:
    """Fail closed when enabling enforcement without qualified legal review."""
    if jurisdiction_requires_legal_review(jurisdiction_id):
        raise PermissionError(
            f"LEGAL_REVIEW_REQUIRED: jurisdiction {jurisdiction_id} has no recorded "
            "qualified legal review (reviewer + date + memo). Enforcement stays disabled."
        )


def reset_reviews() -> None:
    """Test helper: clear the in-memory legal-review registry."""
    _legal_reviews.clear()

"""Centralized Policy Decision Point (PDP) + Policy Enforcement Layer (PEL).

Embedded deterministic PDP for the Modal FastAPI backend: default-deny,
versioned policy bundle, explainable decisions, fail-closed, with simulation /
dry-run support. See docs/PDP_EVALUATION.md for the OPA-vs-Cerbos analysis
(embedded PDP selected for serverless Modal) and docs/POLICY_MATRIX.md for
the full authorization matrix.
"""
from __future__ import annotations

from .enforcement import EnforcementError, require_policy
from .policy import (
    POLICY_BUNDLE_VERSION,
    POLICY_MATRIX,
    evaluate,
    simulate,
)

__all__ = [
    "POLICY_BUNDLE_VERSION",
    "POLICY_MATRIX",
    "EnforcementError",
    "evaluate",
    "require_policy",
    "simulate",
]

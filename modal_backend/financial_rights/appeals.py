"""Customer appeal + dispute + correction/restoration workflows.

Lifecycle:
  submitted -> under_review -> decided(upheld|overturned) -> corrected/restored
  under_review may also move to escalated, then back to under_review/decided.

Rules (deterministic, sandbox):
- Anyone may file an appeal against a restriction on their own account.
- The reviewer must be INDEPENDENT of the original authorizer (different
  identity; enforced by string inequality + credential binding at the API layer).
- Overturned restrictions trigger a correction plan + restoration steps
  (lift restriction, re-evaluate pending operations, notify customer when
  legally permitted, audit everything).
- Escalation is available after a decision or when review_at is breached.
- Correction of erroneous restrictions never rewrites history: the audit trail
  is append-only; corrections are new entries.
"""
from __future__ import annotations

import time
import uuid
from typing import Any

APPEAL_STATES = (
    "submitted",
    "under_review",
    "escalated",
    "upheld",
    "overturned",
    "corrected",
    "restored",
    "closed",
)

_TRANSITIONS: dict[str, set[str]] = {
    "submitted": {"under_review"},
    "under_review": {"upheld", "overturned", "escalated"},
    "escalated": {"under_review", "upheld", "overturned"},
    "overturned": {"corrected"},
    "corrected": {"restored"},
    "restored": {"closed"},
    "upheld": {"closed", "escalated"},
    "closed": set(),
}


def new_appeal(
    *,
    tenant: str,
    restriction_id: str,
    appellant: str,
    grounds_text: str,
    contact: str = "",
) -> dict[str, Any]:
    if not tenant.strip():
        raise ValueError("tenant is required")
    if not restriction_id.strip():
        raise ValueError("restriction_id is required")
    if not appellant.strip():
        raise ValueError("appellant identity is required")
    if not grounds_text.strip():
        raise ValueError("appeal grounds text is required")
    now = int(time.time())
    return {
        "id": f"apl-{uuid.uuid4().hex[:12]}",
        "tenant": tenant,
        "restrictionId": restriction_id,
        "appellant": appellant,
        "groundsText": grounds_text[:2000],
        "contact": contact[:200],
        "state": "submitted",
        "reviewer": "",
        "decision": "",
        "decisionReason": "",
        "history": [{"at": now, "actor": appellant, "to": "submitted"}],
        "createdAt": now,
        "updatedAt": now,
    }


def transition_appeal(
    appeal: dict[str, Any], to_state: str, actor: str, reviewer: str = ""
) -> dict[str, Any]:
    frm = appeal.get("state", "")
    if to_state not in _TRANSITIONS.get(frm, set()):
        raise ValueError(f"illegal appeal transition {frm}->{to_state}")
    if to_state in ("under_review",) and not (reviewer or "").strip():
        raise ValueError("review requires a named independent reviewer")
    if reviewer and reviewer.strip() == (appeal.get("appellant") or ""):
        raise ValueError("reviewer must be independent of the appellant")
    appeal["state"] = to_state
    if reviewer:
        appeal["reviewer"] = reviewer
    now = int(time.time())
    appeal["history"].append({"at": now, "actor": actor, "to": to_state})
    appeal["updatedAt"] = now
    return appeal


def decide_appeal(
    appeal: dict[str, Any],
    *,
    decision: str,
    reason: str,
    reviewer: str,
    original_authorizer: str,
) -> dict[str, Any]:
    """Record an appeal decision. Reviewer must be independent of the authorizer."""
    if decision not in ("upheld", "overturned"):
        raise ValueError("decision must be upheld or overturned")
    if not reason.strip():
        raise ValueError("a written decision reason is required")
    if not reviewer.strip():
        raise ValueError("reviewer identity is required")
    if reviewer.strip().lower() == (original_authorizer or "").strip().lower():
        raise ValueError("appeal reviewer must be independent of the original authorizer")
    appeal["decision"] = decision
    appeal["decisionReason"] = reason[:1000]
    appeal["reviewer"] = reviewer
    target = "overturned" if decision == "overturned" else "upheld"
    return transition_appeal(appeal, target, reviewer, reviewer)


def correction_plan(
    appeal: dict[str, Any], *, restriction: dict[str, Any]
) -> list[str]:
    """Correction steps for an overturned (erroneous) restriction."""
    if appeal.get("decision") != "overturned":
        raise ValueError("correction plans apply to overturned restrictions only")
    steps = [
        f"lift restriction {restriction.get('id')} (append-only audit entry)",
        "re-evaluate queued operations blocked by the restriction",
        "verify no balance was altered by the restriction itself",
    ]
    from .models import disclosure_allowed as _allowed

    if _allowed(restriction.get("ground", ""), bool(restriction.get("gagOrder"))):
        steps.append(f"notify customer {restriction.get('subject')} of the correction")
    else:
        steps.append("notification withheld by law; record legal basis in audit")
    steps.append("schedule post-correction review of the authorizer's pattern")
    return steps


def restoration_steps(appeal: dict[str, Any]) -> list[str]:
    """Full restoration sequence after correction."""
    return [
        "confirm restriction state = lifted in the store",
        "confirm pending lawful operations resume normally",
        "close appeal with written outcome to the appellant (when permitted)",
        "retain tamper-evident audit trail (no history rewrite)",
    ]

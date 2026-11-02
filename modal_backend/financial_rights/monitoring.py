"""Monitoring for employee abuse and repeated unjustified restrictions.

Pure functions over audit/restriction records. Flags patterns for human review —
the monitor never auto-punishes (that would repeat the AI-auto-enforcement
mistake at a meta level). All thresholds are parameters with sandbox defaults.
"""
from __future__ import annotations

from typing import Any


def detect_abuse_patterns(
    restrictions: list[dict[str, Any]],
    appeals: list[dict[str, Any]] | None = None,
    *,
    max_per_authorizer_per_day: int = 10,
    overturn_rate_threshold: float = 0.3,
    min_sample: int = 5,
    ai_only_flag: bool = True,
) -> list[dict[str, Any]]:
    """Scan restriction records and return human-review findings.

    Each finding: {signal, authorizer?, detail, severity}. Empty list = clean.
    Signals:
    - HIGH_VOLUME_AUTHORIZER: one authorizer exceeds the daily volume cap.
    - HIGH_OVERTURN_RATE: authorizer's restrictions are overturned too often.
    - AI_SCORE_ONLY: restriction relied solely on an AI score (engine would
      have denied it; presence in the store means a bypass attempt).
    - REPEATED_SUBJECT_TARGETING: same subject restricted 3+ times in window.
    - MISSING_REVIEW: restriction past reviewAt without a review record.
    """
    findings: list[dict[str, Any]] = []
    appeals = appeals or []
    by_authorizer: dict[str, list[dict[str, Any]]] = {}
    by_subject: dict[str, int] = {}
    for r in restrictions:
        by_authorizer.setdefault(r.get("authorizer", "?"), []).append(r)
        by_subject[r.get("subject", "?")] = by_subject.get(r.get("subject", "?"), 0) + 1
        if ai_only_flag and r.get("aiScoreUsed") and not r.get("humanReviewer"):
            findings.append({
                "signal": "AI_SCORE_ONLY",
                "authorizer": r.get("authorizer"),
                "detail": f"restriction {r.get('id')} used an AI score without human review",
                "severity": "high",
            })
        if r.get("state") == "review_overdue":
            findings.append({
                "signal": "MISSING_REVIEW",
                "authorizer": r.get("authorizer"),
                "detail": f"restriction {r.get('id')} past review deadline",
                "severity": "medium",
            })
    for authorizer, items in by_authorizer.items():
        if len(items) >= max_per_authorizer_per_day:
            findings.append({
                "signal": "HIGH_VOLUME_AUTHORIZER",
                "authorizer": authorizer,
                "detail": f"{len(items)} restrictions by one authorizer in window",
                "severity": "medium",
            })
    decided = [a for a in appeals if a.get("decision") in ("upheld", "overturned")]
    by_auth_decisions: dict[str, list[str]] = {}
    for a in decided:
        by_auth_decisions.setdefault(a.get("authorizer", "?"), []).append(a["decision"])
    for authorizer, decisions in by_auth_decisions.items():
        if len(decisions) >= min_sample:
            rate = sum(1 for d in decisions if d == "overturned") / len(decisions)
            if rate >= overturn_rate_threshold:
                findings.append({
                    "signal": "HIGH_OVERTURN_RATE",
                    "authorizer": authorizer,
                    "detail": f"overturn rate {rate:.0%} over {len(decisions)} decided appeals",
                    "severity": "high",
                })
    for subject, count in by_subject.items():
        if count >= 3:
            findings.append({
                "signal": "REPEATED_SUBJECT_TARGETING",
                "authorizer": "",
                "detail": f"subject {subject} restricted {count} times in window",
                "severity": "medium",
            })
    return findings

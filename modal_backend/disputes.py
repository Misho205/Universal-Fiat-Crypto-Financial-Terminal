"""Customer dispute + financial-rights remediation module (sandbox).

Customers (Personal Workspace) file disputes about unauthorized payments,
incorrect records, disputed fees, account restrictions, or contractual
disagreements. Authorized banking personnel review them with independent
oversight. Remediation (correction / restoration / refund proposal) never
happens automatically: every remediation executes through the normal
authorization paths (approval bindings for money movement), never as a side
effect of filing.

Rules (deterministic):
- Unique case ID per dispute; links to transaction / restriction / agreement.
- Duplicate open case (same customer + category + links) rejected (409).
- Abuse prevention: per-customer daily cap (default 5) + payload limits.
- Evidence is METADATA ONLY in the sandbox (filename, mime, size, sha256,
  verdict). Validation: allowlisted MIME/extension, 10 MB cap, sanitized
  filename. Malware verdict is a stub ("pending-human-review"); production
  MUST scan with ClamAV/AV engine before any reviewer opens the file.
- Status tracking; reasoned decisions when legally permitted (gag-aware via
  the linked restriction: generic wording + notification withheld by law).
- Human review + escalation; the original decision-maker can never be the
  sole reviewer of their own contested action.
- AI scores/recommendations can never become final adverse decisions: a
  decision requires a named human reviewer + non-AI basis note.
- Jurisdiction deadlines/notifications/rights are configurable policies that
  require qualified legal review before enforcement (reuse jurisdictions).
- Tamper-evident audit events for submit/evidence/decision/remediation/close.
- Tenant isolation + data minimization (references, redacted text).
- Admins cannot silently close/delete: close requires a decision + reason +
  audit; no DELETE endpoint exists.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
import uuid
from typing import Any

from . import db as _db

CASE_VERSION = "dsp-v1"

CATEGORIES = (
    "unauthorized_payment",
    "incorrect_record",
    "disputed_fee",
    "account_restriction",
    "contractual",
)

STATES = ("submitted", "under_review", "escalated", "decided", "remediation",
          "closed")

_TRANSITIONS: dict[str, set[str]] = {
    "submitted": {"under_review"},
    "under_review": {"decided", "escalated"},
    "escalated": {"under_review", "decided"},
    "decided": {"remediation", "closed"},
    "remediation": {"closed"},
    "closed": set(),
}

DECISIONS = ("upheld", "partially_upheld", "rejected")

# Per-category SLA (days) + notification duty. Configurable; enforcement of a
# jurisdiction profile requires qualified legal review (see jurisdictions).
CATEGORY_SLA_DAYS: dict[str, int] = {
    "unauthorized_payment": 15,
    "incorrect_record": 30,
    "disputed_fee": 30,
    "account_restriction": 7,
    "contractual": 30,
}

MAX_CASES_PER_CUSTOMER_PER_DAY = int(os.environ.get("DISPUTE_DAILY_CAP", "5"))
MAX_EVIDENCE_BYTES = 10 * 1024 * 1024

ALLOWED_MIME = {
    "application/pdf": (".pdf",),
    "image/png": (".png",),
    "image/jpeg": (".jpg", ".jpeg"),
    "text/plain": (".txt",),
    "text/csv": (".csv",),
}


def _now() -> int:
    return int(time.time())


def new_case(
    *,
    tenant: str,
    customer: str,
    category: str,
    description: str,
    transaction_id: str = "",
    restriction_id: str = "",
    agreement_id: str = "",
    jurisdiction: str = "EU_GENERIC",
) -> dict[str, Any]:
    if not tenant.strip():
        raise ValueError("tenant is required")
    if not customer.strip():
        raise ValueError("customer identity is required")
    if category not in CATEGORIES:
        raise ValueError(f"unknown dispute category {category!r}")
    if not description.strip():
        raise ValueError("dispute description is required")
    if not (transaction_id or restriction_id or agreement_id):
        raise ValueError("a dispute must link a transaction, restriction, or agreement")
    try:
        from .financial_rights import jurisdictions as _jurisdictions
        sla_days = CATEGORY_SLA_DAYS[category]
        _jurisdictions.get_jurisdiction(jurisdiction)
    except KeyError as exc:
        raise ValueError(str(exc)) from exc
    now = _now()
    return {
        "id": f"dsp-{uuid.uuid4().hex[:12]}", "tenant": tenant,
        "customer": customer, "category": category,
        "description": description[:2000], "transactionId": transaction_id,
        "restrictionId": restriction_id, "agreementId": agreement_id,
        "jurisdiction": jurisdiction, "state": "submitted", "reviewer": "",
        "originalActor": "", "decision": "", "decisionReason": "",
        "humanBasis": "", "remediation": {}, "slaDue": now + sla_days * 86400,
        "evidence": [], "history": [{"at": now, "actor": customer, "to": "submitted"}],
        "createdAt": now, "updatedAt": now, "version": CASE_VERSION,
    }


def case_put(doc: dict[str, Any]) -> None:
    if not doc.get("id") or not doc.get("tenant"):
        raise ValueError("case_put: id and tenant are required")
    now = _now()
    _db._exec_write(
        """INSERT INTO dispute_cases(id,tenant,customer,category,state,transaction_id,
             restriction_id,agreement_id,reviewer,original_actor,decision,
             sla_due,jurisdiction,document_json,created_at,updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(id) DO UPDATE SET state=excluded.state,
             reviewer=excluded.reviewer, decision=excluded.decision,
             document_json=excluded.document_json, updated_at=excluded.updated_at""",
        (doc["id"], doc["tenant"], doc.get("customer", ""), doc.get("category", ""),
         doc.get("state", "submitted"), doc.get("transactionId", ""),
         doc.get("restrictionId", ""), doc.get("agreementId", ""),
         doc.get("reviewer", ""), doc.get("originalActor", ""),
         doc.get("decision", ""), int(doc.get("slaDue", 0)),
         doc.get("jurisdiction", "EU_GENERIC"), json.dumps(doc),
         int(doc.get("createdAt", now)), now),
    )


def _row_to_doc(row: dict[str, Any]) -> dict[str, Any]:
    return json.loads(row["document_json"])


def case_get(case_id: str, tenant: str) -> dict[str, Any] | None:
    row = _db._fetch_one(
        "SELECT document_json FROM dispute_cases WHERE id=? AND tenant=?",
        (case_id, tenant),
    )
    return _row_to_doc(row) if row else None


def case_list(tenant: str, limit: int = 50, state: str = "",
              customer: str = "") -> list[dict[str, Any]]:
    lim = max(1, min(limit, 200))
    if state:
        rows = _db._fetch_all(
            "SELECT document_json FROM dispute_cases WHERE tenant=? AND state=? "
            "ORDER BY created_at DESC LIMIT ?", (tenant, state, lim))
    elif customer:
        rows = _db._fetch_all(
            "SELECT document_json FROM dispute_cases WHERE tenant=? AND customer=? "
            "ORDER BY created_at DESC LIMIT ?", (tenant, customer, lim))
    else:
        rows = _db._fetch_all(
            "SELECT document_json FROM dispute_cases WHERE tenant=? "
            "ORDER BY created_at DESC LIMIT ?", (tenant, lim))
    return [_row_to_doc(r) for r in rows]


def customer_daily_count(tenant: str, customer: str, now: int | None = None) -> int:
    ts = now if now is not None else _now()
    day_start = ts - 86400
    rows = _db._fetch_all(
        "SELECT COUNT(*) AS n FROM dispute_cases WHERE tenant=? AND customer=? "
        "AND created_at>=?", (tenant, customer, day_start))
    return int(rows[0]["n"]) if rows else 0


def duplicate_open_case(tenant: str, customer: str, category: str,
                        transaction_id: str, restriction_id: str,
                        agreement_id: str) -> dict[str, Any] | None:
    for doc in case_list(tenant, limit=200, customer=customer):
        if doc.get("state") in ("closed",):
            continue
        if (doc.get("category") == category
                and doc.get("transactionId", "") == transaction_id
                and doc.get("restrictionId", "") == restriction_id
                and doc.get("agreementId", "") == agreement_id):
            return doc
    return None


def transition(doc: dict[str, Any], to_state: str, actor: str,
               reviewer: str = "") -> dict[str, Any]:
    frm = doc.get("state", "")
    if to_state not in _TRANSITIONS.get(frm, set()):
        raise ValueError(f"illegal dispute transition {frm}->{to_state}")
    if to_state == "under_review" and not reviewer.strip():
        raise ValueError("review requires a named independent reviewer")
    if reviewer and reviewer.strip().lower() == doc.get("customer", "").strip().lower():
        raise ValueError("reviewer must be independent of the customer filing")
    doc["state"] = to_state
    if reviewer:
        doc["reviewer"] = reviewer
    now = _now()
    doc["history"].append({"at": now, "actor": actor, "to": to_state})
    doc["updatedAt"] = now
    return doc


def decide(doc: dict[str, Any], *, decision: str, reason: str, reviewer: str,
           human_basis: str, original_actor: str = "",
           ai_contributed: bool = False) -> dict[str, Any]:
    """Record a reasoned decision. The reviewer must be independent of the
    original decision-maker; AI output can never be the sole basis."""
    if decision not in DECISIONS:
        raise ValueError("decision must be upheld, partially_upheld, or rejected")
    if not reason.strip():
        raise ValueError("a written decision reason is required")
    if not reviewer.strip():
        raise ValueError("reviewer identity is required")
    if original_actor and reviewer.strip().lower() == original_actor.strip().lower():
        raise ValueError("the original decision-maker cannot be the sole reviewer "
                         "of their own contested action")
    if ai_contributed and not human_basis.strip():
        raise ValueError("AI-assisted assessment requires an explicit non-AI human "
                         "basis note; AI output can never be the final adverse decision")
    doc["decision"] = decision
    doc["decisionReason"] = reason[:2000]
    doc["reviewer"] = reviewer
    doc["humanBasis"] = human_basis[:1000]
    doc["originalActor"] = original_actor
    return transition(doc, "decided", reviewer)


def remediation_plan(doc: dict[str, Any]) -> list[str]:
    """Remediation steps — proposals only. Money movement executes exclusively
    through the normal authorization paths (approval bindings); filing a dispute
    never creates an automatic right to reversal or an automatic refund."""
    if doc.get("decision") not in ("upheld", "partially_upheld"):
        raise ValueError("remediation applies to upheld disputes only")
    steps = [
        "apply the decided correction (record/fee/restriction scope)",
        "verify no unrelated customer data was touched (data minimization)",
    ]
    if doc.get("category") in ("unauthorized_payment", "disputed_fee"):
        steps.append("prepare a refund PROPOSAL via cryptographic approval binding "
                     "(maker-checker + quorum + step-up; explicit approval required, "
                     "never automatic)")
    if doc.get("category") == "account_restriction":
        steps.append("lift or narrow the restriction via the rights workflow "
                     "(compliance review when legal orders apply)")
    steps.append("notify the customer with a reasoned outcome (generic wording "
                 "when disclosure is restricted by law)")
    steps.append("retain tamper-evident audit trail (submit/evidence/decision/remediation)")
    return steps


# ---------- evidence metadata (no file bytes server-side) ----------

def sanitize_filename(name: str) -> str:
    base = re.sub(r"[^A-Za-z0-9._-]", "_", (name or "").strip().split("/")[-1])
    if not base or base in (".", ".."):
        raise ValueError("invalid filename")
    return base[:120]


def validate_evidence(filename: str, mime: str, size_bytes: int,
                       sha256: str) -> dict[str, Any]:
    """Validate upload metadata. Returns the stored evidence record with a
    stub scan verdict. Production MUST scan bytes with ClamAV/AV engine
    before any reviewer opens the file — the stub never clears content."""
    clean = sanitize_filename(filename)
    exts = ALLOWED_MIME.get(mime, ())
    if not exts:
        raise ValueError(f"file type {mime!r} not allowed "
                         f"(allowlist: {sorted(ALLOWED_MIME)})")
    if not any(clean.lower().endswith(e) for e in exts):
        raise ValueError("filename extension does not match declared MIME type")
    if size_bytes <= 0 or size_bytes > MAX_EVIDENCE_BYTES:
        raise ValueError(f"file size must be 1..{MAX_EVIDENCE_BYTES} bytes")
    if not re.fullmatch(r"[0-9a-f]{64}", sha256 or ""):
        raise ValueError("sha256 digest (64 hex) of the file bytes is required")
    return {"id": f"ev-{uuid.uuid4().hex[:12]}", "filename": clean,
            "mime": mime, "sizeBytes": size_bytes, "sha256": sha256,
            "verdict": "pending-human-review",
            "scanNote": "sandbox stub: production MUST AV-scan bytes pre-review"}


def evidence_put(tenant: str, case_id: str, record: dict[str, Any],
                 submitted_by: str) -> dict[str, Any]:
    rec = {**record, "caseId": case_id, "submittedBy": submitted_by,
           "createdAt": _now()}
    _db._exec_write(
        "INSERT INTO dispute_evidence(id,tenant,case_id,filename,mime,size_bytes,"
        "sha256,verdict,submitted_by,created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (rec["id"], tenant, case_id, rec["filename"], rec["mime"],
         rec["sizeBytes"], rec["sha256"], rec["verdict"], submitted_by,
         rec["createdAt"]),
    )
    return rec


def evidence_list(tenant: str, case_id: str) -> list[dict[str, Any]]:
    rows = _db._fetch_all(
        "SELECT * FROM dispute_evidence WHERE tenant=? AND case_id=? "
        "ORDER BY created_at ASC LIMIT 100", (tenant, case_id))
    return [dict(r) for r in rows]

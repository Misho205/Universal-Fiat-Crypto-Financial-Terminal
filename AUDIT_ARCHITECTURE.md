# Independent Audit Storage Architecture

Implementation: `modal_backend/audit_store.py`, `modal_backend/audit_api.py`,
migration `006_approval_audit.sql` (`audit_events`, `audit_outbox`). Tests:
`test_audit_integrity.py` (9). Report: `AUDIT_INTEGRITY_TEST_REPORT.md`.

## 1. Separation

Security audit events live in `audit_events` — a different table, schema,
and code path from application logs (`logging_util`) and the legacy
`security_audit` trail (kept for compatibility). No shared writers.

## 2. Structured schema

`event_id, ts, actor (server-derived), tenant (server-derived), action,
resource, outcome, policy decision, correlation_id, approval_ref, detail
(redacted)`, plus `prev_hash/hash` chain links. Actors/tenants are NEVER
taken from client input: routes pass `require_tenant` + `role_of` values.

## 3. Append-only ingestion

`record_event()` is the sole writer; the module exposes no update/delete.
`must_audit()` raises on storage failure; sensitive operations call it BEFORE
mutating state (binding create/approve/consume, restriction create/lift,
fiat cancel/refund start, agreement execute start) and refuse with 503 when
recording is impossible (fail-closed list, §7).

## 4. Integrity: hash chaining (and what it does NOT give)

Each record: `digest = SHA-256(v|event_id|tenant|ts|actor|action|resource|
outcome|policy|correlation|approval_ref|detail|prev_hash)` (seq ordered,
no truncation pre-hash — fixes legacy gaps). Optional HMAC-SHA256 when
`AUDIT_HMAC_KEY` is set.

**Do NOT claim hash chaining alone guarantees immutability**: anyone with DB
write access can recompute a chain. Detection works only against an
independent copy — hence exports (§5) and the verify endpoint (§8).

## 5. Independent storage + WORM evaluation

`export_jsonl()` writes per-tenant JSONL (fsync) and drains the outbox ONLY
after the destination acknowledges. The sandbox destination
(`AUDIT_EXPORT_DIR`, default `./data/audit-exports`) stands in for
independently controlled, retention-protected storage. Evaluated options
(assumption: ordinary object storage is NOT immutable):

| Option | Immutability mechanism | Fit |
|---|---|---|
| AWS S3 Object Lock (Compliance mode) + versioning | Retention lock, no delete incl. root | Best fit for export target |
| GCS retention policy / retention lock | Bucket/table retention, holds | Good fit |
| Azure Immutable Blob (time-based/legal hold) | WORM policies | Good fit |
| On-prem append-only volume + separate admin | OS-level append-only, split duties | Acceptable with dual control |
| Plain bucket/dir without locks | None — NOT sufficient | Rejected as sole store |

Production: export target MUST be WORM-locked, owned by a separate audit
administrator (see §6), with retention measured in years per jurisdiction.

## 6. Administration separation

Audit readers: auditor, compliance, approver, admin, owner
(`GET /api/audit/events`, `/verify`). Audit export: admin only, itself
audited. Application admins cannot modify records (no API, verified by source
scan + tests). Remaining gap: the same backend process hosts both planes —
production must split the audit administrator role and credentials from
application administration (R-05).

## 7. Fail-closed operations (audit mandatory)

Binding create/approve/consume; restriction create/lift; fiat cancel/refund;
agreement execute; audit export. When `must_audit` raises → 503, no state
change. Ordinary reads/dashboards stay available (safe read-only).

## 8. Buffering / retry / alerts

Export failures keep events in `audit_outbox` and return the pending count
(no silent loss). `GET /api/audit/verify` reports: INTEGRITY_FAILURE (broken
link/digest), SEQ_GAP (missing events), MONOTONICITY (clock regression),
EMPTY, plus `outboxPending` and a privileged-activity scan. Deletion attempts
surface as integrity/gap alerts on the next verify against an export.

## 9. Privacy & retention

Redaction at ingestion (bearer tokens, `sk_*`, PEM blocks, 13–19 digit PAN
runs); references over payloads; tenant-scoped reads; no passwords/keys/card
data. Lawful deletion: purge by tenant via dual-controlled, audited
procedure against BOTH live tables and WORM-expired exports (retention floor
first) — procedure to be defined with counsel per jurisdiction before
production (BG/EU: GDPR + sectoral retention).

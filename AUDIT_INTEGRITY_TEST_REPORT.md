# Audit Integrity Test Report

Date: 2026-11-02. File: `modal_backend/test_audit_integrity.py` — 9/9 pass.
Full suite: 182 passed / 4 skipped. Sandbox only; TestClient + sqlite.

## Results per required test

| # | Test | Result | What it proves |
|---|---|---|---|
| 1 | Unauthorized audit modification | PASS | No `UPDATE/DELETE audit_*` in any API/DB source; only `/export` writes besides reads (405 on PUT/PATCH/DELETE) |
| 2 | Audit deletion attempts | PASS | Raw DELETE leaves the outbox copy behind (pending ≥ 1); verify quantifies surviving events |
| 3 | Hash chain manipulation | PASS | Forged `detail` → `valid:false` + INTEGRITY_FAILURE alert |
| 4 | Missing audit events | PASS | Deleted middle row → SEQ_GAP alert (seq from live rows, hermetic counters) |
| 5 | Duplicate events | PASS | Same payload twice → distinct event_ids + hashes; chain valid |
| 6 | Storage unavailability | PASS | Export failure buffers (no loss); `must_audit` raises (fail-closed) |
| 7 | Cross-tenant audit access | PASS | Other tenant: empty list + zero verify; operator denied (403) |
| 8 | Compromised administrator | PASS | Admin reads/exports only; history intact; privileged actions visible in scan |
| 9 | Integrity verification report | PASS | Valid chain verifies with event count, zero alerts, HMAC flag; secrets redacted at ingestion |

## What verification proves — and does not prove

Proves: the rows present form an unbroken, untampered sequence; gaps and
forgeries are detected; writes are fail-closed; reads are tenant-scoped and
role-gated; no PII/secrets persist in `detail`.

Does NOT prove: that no rows were deleted without a trace (deletion of the
tail is invisible without an independent export — hence outbox + exports);
immutability (needs WORM, §AUDIT_ARCHITECTURE.md §5); wall-clock accuracy
(monotonicity enforced, no trusted timestamping); protection against an
attacker holding both DB and export credentials (separate admins required).

# Remediation Plan — findings from the 2026-11-02 security audit

Status legend: DONE (implemented + tested) / PLANNED (accepted, scheduled) /
ACCEPTED (sandbox risk acceptance, must clear before real funds).

## DONE

| ID | Action | Evidence |
|---|---|---|
| F-01 | STRICT gate now checks `expiresAt` + `amountMinor` | `api.py::_strict_intent_required`; S11 test |
| F-02 | Cryptographic approval bindings (canonical op + digest + single-use consume) | `approval_binding.py`, migration 006, 11 tests, `APPROVAL_BINDING_SECURITY.md` |
| F-03 | Atomic consume-before-provider on binding paths; revalidation pre-execution | `_binding_enforce` in fiat cancel/refund + agreement execute; concurrency test (1 winner / 8 threads) |
| F-05 | Structured `audit_events` chain (seq in digest, no truncation) + `must_audit` fail-closed on: binding create/approve/consume, restriction create/lift, fiat cancel/refund start, agreement execute start | `audit_store.py`, `AUDIT_ARCHITECTURE.md`, 9 integrity tests |
| F-06 | Auditor-readable endpoints (`/api/audit/events`, `/api/audit/verify`) for auditor/compliance/approver/admin/owner | `audit_api.py`, S7/S6 tests |

## PLANNED (do before any real-money or production-PII use)

| ID | Action | Priority |
|---|---|---|
| R-03 | Migrate ALL execution paths to bindings (retire legacy intent-only unlock); add provider-side idempotency keys for refund/cancel where the PSP supports them | High |
| R-04 | Enforce `credId` self-approval checks on legacy intent approve OR remove legacy approve path | High |
| R-05 | Backfill/export legacy `security_audit` into WORM; deploy Object-Lock/GCS-retention export target + dual-control audit admin (separate from app admin) | High |
| R-08 | Flip PDP `require_policy` to real intent/step-up context (STRICT rollout) once all callers carry intents; remove permissive wiring | High |
| R-07 | Wire `ai_guardrails/tools.invoke_tool` behind `ai.execute` PDP with the tool allowlist, or delete the module | Medium |
| R-09 | Trusted timestamps (RFC 3161) for audit events; HMAC key in Modal Secret + rotation runbook | Medium |
| R-10 | Independent pentest + code review; load/chaos test of consume race across Modal replicas (Postgres `SELECT FOR UPDATE` path) | High (pre-prod gate) |

## ACCEPTED (sandbox only)

A-01 Residual risks R1–R5 (THREAT_MODEL.md §6) are accepted for isolated
sandbox testing with fake tenants. They MUST be cleared (or formally
risk-accepted by the accountable owner with legal review) before staging
with real data, and all of them before production. No auto-deploy is
configured; deploys remain explicit operator steps.

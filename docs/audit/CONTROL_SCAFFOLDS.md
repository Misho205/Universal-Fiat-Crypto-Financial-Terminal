# Enterprise Control Scaffolds — DRAFT, NOT OPERATIONAL

> Scaffolds for future implementation. None of these are operating controls;
> each needs counsel/owner approval, implementation, and testing before it
> counts as evidence. Status: **NOT IMPLEMENTED** (scaffold only).

## 1. Least-privilege RBAC + tenant isolation (partially present)
- Present (verified): operator/admin bearer split, `require_admin` on
  money-moving endpoints, PDP default-deny 23-action matrix, token-derived
  tenant binding, maker-checker with credential-hash self-approval detection.
- Scaffold remaining: periodic access review procedure, break-glass session
  quarterly drill log, `TENANT_FOR_*_TOKEN` mandatory in staging (deploy gate).

## 2. Structured audit events + correlation IDs (present, extend)
- Present: hash-chained per-tenant audit (`audit_store.py`), `must_audit_or_503`
  fail-closed writes, JSONL export + outbox.
- Scaffold remaining: end-to-end correlation ID (`X-Request-Id` passthrough
  SDK → backend → logs) — small code change, queued for next audit branch.

## 3. Secure payment state machine + idempotency (present)
- Present: `STATES` lifecycle, provider-authoritative status, `UNKNOWN` +
  reconcile (no unsafe failover), per-route idempotency with 409 on conflict,
  single-use approval bindings. Covered by 225 backend tests.

## 4. Privacy-aware retention (DRAFT proposal, not enforced)
- Proposal only: `RETENTION_DAYS_TRANSACTIONS` / `_AUDIT` / `_DISPUTES`
  (defaults TBD by counsel; audit/dispute records typically outlive
  operational data for limitation periods — LEGAL_REVIEW_REQUIRED), purge job
  design (tenant-scoped hard delete + audit tombstone), no code written.

## 5. Data-subject request workflow (DRAFT procedure, not implemented)
- Proposed SLA: acknowledge ≤5 days, fulfil ≤30 days (GDPR Art. 12(3));
  identity verification via existing session + tenant binding; export format:
  JSON of tenant-scoped records; erasure with legal-hold exceptions
  (audit/financial-records retention — counsel to define); request log.
- No code written; disputes module is NOT a DSR channel (explicit).

## 6. Secure configuration validation (partially present)
- Present: `assert_sandbox()` fail-closed live gate, `sk_test_`-only provider
  factory, mainnet refusal, tokenless-mode startup warning (M-06), `/ready`
  migration+store checks, `CORS_ORIGINS`/token-binding deploy gates documented.
- Scaffold remaining: startup refusal (not warning) when `NODE_ENV=production`
  without token bindings — queued with operator approval.

## 7. Dependency scanning in CI (scaffold)
- Present (this audit): `pip-audit` + `pnpm audit` baselines recorded in
  `TEST_EVIDENCE.md`; `pnpm.overrides` for postcss/multer.
- Scaffold: CI job (`.github/workflows/security.yml` — NOT created; no CI
  exists) running both audits + `pytest` + `vitest`, failing on new
  critical/high. Snippet queued in roadmap.

## 8. Incident response + recovery (references, not a new plan)
- Existing: `BREAK_GLASS_POLICY.md`, `AI_EMERGENCY_RESPONSE.md`,
  `DISPUTE_HANDLING_POLICY.md`, `/ready` probe, JSONL audit export.
- Scaffold remaining: single incident-runbook index mapping DORA Art. 17–19
  classification onto existing playbooks + 72 h GDPR breach clock — drafting
  queued pending counsel (G-06/G-10).

## 9. Human approval for high-impact AI recommendations (present)
- Present and tested: AI advisory-only (no payment/contract/freeze path imports
  AI), `requiresHumanReview` flags, maker-checker intents for execution,
  dual-control AI kill-switch re-enable, `AI-scores-never-auto-enforce`.
- No scaffold needed; keep under regression (`test_s1/s2`, PDP tests).

## 10. Security integration tests (present, extended this audit)
- Added: `test_remediation_audit_fixes.py` (H-02/M-05/M-06), NestJS CORS
  preflight test. Full counts in `TEST_EVIDENCE.md`.

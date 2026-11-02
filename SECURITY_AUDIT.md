# Security Audit — AI, Employee, Administrator & Financial-Rights Guardrails

Auditor role: independent adversarial assessment. Scope: sandbox/backend only
(`modal_backend/`), isolated TestClient scenarios — **no real customer
accounts, no production financial systems were touched.**
Date: 2026-11-02. Executed: `pytest modal_backend/test_security_audit.py`
(15/15 pass), `test_approval_binding.py` (11/11),
`test_audit_integrity.py` (9/9). Full suite: 182 passed / 4 skipped.

> Passing tests are evidence of tested behavior, NOT security guarantees.
> See GUARDRAIL_TEST_REPORT.md §7 and THREAT_MODEL.md §6 (residual risks).

## 1. Scenario results (expected vs actual)

| # | Scenario | Expected secure behavior | Actual result | Verdict |
|---|---|---|---|---|
| S1 | AI executes payment | AI output never moves funds | No AI imports on any payment path; `decision_from_ai` always approved:false/autoEnforced:false | PASS |
| S2 | AI freezes account | AI cannot create restrictions | 401 without credential; 422 AI-score-only even with stolen operator credential | PASS |
| S3 | Prompt injection | Screened, logged, no side effects | Blocked/validated; advisoryOnly; zero payments created | PASS |
| S4 | Employee self-approves high-risk op | maker != checker (identity + credential) | Same-label 403; same-credential alt-account 403 on binding path; high amounts force quorum=2 | PASS (binding path). Legacy gap → F-04 |
| S5 | Admin modifies balances | No such endpoint | Source scan clean; mutation paths 404; writes only via provider upserts | PASS |
| S6 | Operator erases audit | No delete path; tamper detected | PUT/PATCH/DELETE on /api/audit/* → 405; forged row → INTEGRITY_FAILURE | PASS |
| S7 | Cross-tenant access | 404/empty everywhere | Payments, agreements, bindings, audit all tenant-scoped | PASS |
| S8 | Replay payment requests | 409s everywhere | Idempotency conflict, consumed binding, tx-hash reuse all refused | PASS |
| S9 | Bypass contract conditions | Ineligible never executes | 409 without approval; 403 wrong role | PASS |
| S10 | Privilege escalation via API | 403/422, PDP denies | Operator→admin 403; unknown scope 422; role.grant without dual control denied | PASS |
| S11 | Expired approval reused | Expired never unlocks | Approved-then-expired → STRICT 403 (fix verified); pending-expiry → 410 | PASS (fixed, was F-01) |
| S12 | Unjustified restriction of legit customer | Denied at creation; appealable | 422 without evidence; overturn → lifted + correctionPlan | PASS |
| S13 | Lawful restriction bypassed | LegalRef required; admin-only lift; gag respected | Operator file/lift 403-422; authorizer-as-reviewer 403/422 | PASS |
| S14 | Compromised AI service | Kill-switch contains AI; payments unaffected | AI 503, fiat 201, forbidden tools denied + audited | PASS |
| S15 | Policy update removes approvals | Bundle code-pinned; simulate dry-run only | Matrix still needs intent; no policy-write endpoint (404s) | PASS |

## 2. Findings

| ID | Severity | Finding | Status |
|---|---|---|---|
| F-01 | **High** | `_strict_intent_required` ignored `expiresAt` + `amountMinor`: expired/foreign-amount intents unlocked execution in STRICT mode | **FIXED** (`api.py`: expiry + amount compared; S11 test) |
| F-02 | **High** | Approvals bound to `(action, target)` strings only — no operation digest; parameter changes after approval undetected | **FIXED** (cryptographic approval bindings, migration 006; see APPROVAL_BINDING_SECURITY.md) |
| F-03 | **High** | Duplicate/concurrent execution: legacy intents never consumed; `idem_lookup` per-key only; provider called before any consume | **FIXED** on binding paths (atomic single-use consume BEFORE provider call); legacy paths unchanged → R-03 |
| F-04 | Medium | Legacy intent self-approval check misses same-credential/different-label for quorum counting (`checkerKey` includes the label) | **Mitigated**: bindings enforce `credId` (sha256 of credential); legacy path kept for compat → R-04 |
| F-05 | Medium | `security_audit` chain: seq excluded from digest, fields truncated pre-hash, verify capped at 2000 rows, no WORM, audit errors swallowed on some paths | **Mitigated**: new `audit_events` chain (seq in digest, no truncation) + `must_audit` fail-closed on sensitive paths → R-05 |
| F-06 | Medium | `audit.read` allowed auditor/compliance/approver in PDP matrix, but `GET /api/admin/audit` required admin (auditors locked out) | **FIXED** (`GET /api/audit/events` + `/verify` for auditor/compliance/approver/admin/owner) |
| F-07 | Low | `ai_guardrails/tools.invoke_tool` is dead code (no HTTP route calls it); `PDP[ai.execute]` is read-only by convention only | Documented → R-07 (wire with allowlist or remove) |
| F-08 | Low | PDP `require_policy` sandbox wiring passes permissive intent/step-up context; real `needs_intent` evaluation deferred to handlers/STRICT | Known limitation, rollout plan in `docs/PDP_EVALUATION.md` → R-08 |

## 3. Fixes applied in this audit

1. `_strict_intent_required`: expiry + amount binding (F-01).
2. New cryptographic approval-binding subsystem + execution enforcement (F-02, F-03).
3. New structured audit chain + fail-closed writes + auditor endpoints (F-05, F-06).
4. Migration `006_approval_audit.sql`; `sqlite_sequence` reset for hermetic tests.
5. 35 new tests (15 scenario + 11 binding + 9 integrity); 2 pre-existing tests
   updated for intentional tightening (migration list; EVM tx-reuse 409).

## 4. What was NOT tested / NOT claimed

Live provider networks, real KYC/issuer flows, Modal production deployment,
container/secret infrastructure, frontend auth storage on user devices,
DDoS/availability, and human social-engineering. No pentest of bank networks.

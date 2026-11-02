# Security Integration Audit — five modules, one backend

Independent principal-engineer audit. Scope: sandbox/backend + Next.js
workspaces. Method: code inspection + 10 cross-module integration tests
(`test_security_integration.py`) + full regression (217 passed / 4 skipped).
No production systems, no real customer data touched.
Date: 2026-11-02.

Verdict vocabulary: PASS (implemented + tested) / FAIL (tested, does not meet
the requirement) / NOT IMPLEMENTED / NOT TESTED.

## 1. Module status

| Module | Implementation | Integration | Verdict |
|---|---|---|---|
| 1. Cryptographic Approval Binding | `approval_binding.py`, `approval_api.py`, migration 006; enforced on fiat cancel/refund + agreement execute/amend/cancel/dispute | Mounted; consumed atomically pre-provider | PASS |
| 2. Independent Audit Storage | `audit_store.py`, `audit_api.py`, `audit_events` + `audit_outbox` | Fail-closed `must_audit_or_503` unified (was 500/503 mixed) on all sensitive paths | PASS |
| 3. Break-Glass Emergency Access | `breakglass.py`, `breakglass_api.py`, migration 007 | Session-token gateway; no bearer powers outside scopes | PASS |
| 4. AI Emergency Kill Switch | `ai_guardrails/control.py` (DB-backed), feature flags, circuit breaker | All `/api/ai/*` guarded incl. previously open `/analyze`; dual-control re-enable | PASS (2 gaps fixed during this audit) |
| 5. Customer Dispute + Financial Rights | `disputes.py`, `dispute_api.py`, rights engine, Personal/Banking UI, SDK | Mounted; decision gated by PDP + independent reviewer | PASS |

## 2. Task-by-task findings (tasks 1–15)

| # | Task | Result | Evidence |
|---|---|---|---|
| 1 | Inspect implementation status | PASS | Table §1; 85 OpenAPI paths live |
| 2 | Verify backend/frontend/auth/tenant/policy integration | PASS | 17-endpoint auth-chain table (audit workpapers); tenant-scoped queries; PDP matrix pinned |
| 3 | Missing deps / auth gaps / conflicting policies / duplicated logic | PASS with notes | Gaps G-01…G-05 below; duplicates documented, not silently diverging |
| 4 | High-risk actions server-side authorized | PASS | cancel/refund/execute/amend/cancel/dispute/lift/bindings-approve/kill-switch: admin bearer + PDP + (intent or binding) + audit; 401/403 regression tests |
| 5 | Approvals not reusable after modification | PASS | e2e: amount tamper → 409 APPROVAL_BINDING; intact retry unaffected; bindings enforced even with STRICT=0 |
| 6 | Audit not silently alterable via app privileges | PASS | Source scan: no UPDATE/DELETE audit paths; outage → 503 with zero state change (tested) |
| 7 | Emergency cannot bypass ownership | PASS | Allowlist excludes lift/move/sign/role/audit; gateway legal-order lifts refused by category |
| 8 | AI disable keeps finance working | PASS | AI 503 while fiat create/confirm, dashboard, disputes, rights all 200 |
| 9 | Disputes protected from improper resolution | PASS | Operator triages but cannot decide (403); no DELETE route; close requires decision |
| 10 | Cross-tenant + escalation | PASS | 404/empty across payments, rights, disputes, bindings, audit; operator→admin surfaces 403 |
| 11 | Suites + missing regression tests | PASS | 10 new `test_security_integration.py`; full suite green |
| 12 | Frontend build + backend startup | PASS | `next build` green (/, /banking, /personal, /simulator, /design-system); uvicorn boot + `/health` liveMode OFF + 85 paths |
| 13 | Skipped vs verified | PASS | 4 skips enumerated (all opt-in live); §4 |
| 14 | Deployment readiness | See DEPLOYMENT_READINESS.md | Sandbox READY; production NOT READY (R-gaps) |
| 15 | Remaining risks | See REMAINING_RISKS.md | |

## 3. Gaps found and disposition

- **G-01 (FIXED):** `POST /api/ai/analyze` lacked `require_ai_enabled`, `require_tenant`, and feature flag. → Guard + tenant + `explainers` flag added; test updated.
- **G-02 (FIXED):** `agreement.amend/cancel/dispute` had no `_binding_enforce` and no fail-closed audit (log-only). → Both added.
- **G-03 (FIXED):** Inconsistent fail-closed codes: bindings/breakglass/disputes raised 500 on audit outage, api.py raised 503. → Single `audit_store.must_audit_or_503` used everywhere.
- **G-04 (FIXED):** `rights appeal.decide` wrote only the legacy chain. → Structured fail-closed record added.
- **G-05 (ACCEPTED, documented):** Duplicated systems remain by design for compatibility — legacy intents vs bindings; legacy `security_audit` vs `audit_events` (+ AI ring + pdp_decisions); 3 kill-switch flags OR-ed; PDP sandbox wiring passes permissive intent context. Migration tracked as R-03/R-04/R-05/R-08. No silent divergence: dual writes + pinned bundle version + tests lock behavior.

## 4. Skipped tests — verified vs untested

Skipped (4, all require explicit opt-in + live credentials/network — none
available in sandbox, none executed):
1. `test_ai_complete.py` — live Meta model call.
2. `test_meta_ai.py` — live Meta model call (token-consuming).
3. `test_evm_payments.py` — live Sepolia RPC receipt check.
4. `test_live_integration.py` — against a real deployment.

NOT TESTED (no automated coverage; must not be mistaken for verified):
Postgres backend paths (tests run sqlite), Modal multi-replica concurrency
(thread-level only), real MFA/WebAuthn verification, production AV scanning,
WORM export targets, secret-management rotation, browser key custody,
network/OS layers, human/social processes, real-money rails.

# IMPLEMENTATION_STATUS.md — Universal Hybrid Payment Terminal

Generated: 2026-10-31 (UTC); updated 2026-11-02 (UTC, working tree below).
Scope: user-facing app + persistent data layer (dashboard, auth/RBAC, Postgres/Volume durability, migrations)
+ Financial Rights Protection Engine + centralized PDP/PEL + agreement/crypto guardrails.
Policy: no invented results — every claim below cites an executed command or a file.

Deployed (approved 2026-10-31, commit 9b5971b): backend
`https://michail-tsvetanov--hybridpay-sandbox-fastapi-app.us-east.modal.run` and frontend
`https://michail-tsvetanov--hybridpay-terminal-serve.us-east.modal.run` (verified 200/201 above).
NOT deployed (local only, pending explicit approval): everything after 9b5971b —
tenant binding, SDK validation + modal-schema, polling lib, probe_live 46 checks,
pagination (backend + UI), English-only UI, idempotent cancel/refund, reconcile runs,
server CSV export, webhook test-trigger, per-tenant AI usage, admin overview,
a11y contract tests, load probe, AI + institutional guardrails (see CHANGELOG +
`git log --oneline`).

## 1. Modal startup failure — reproduction & fix
- **Reproduce**: `modal serve modal_backend/app.py` — image builds (fastapi/httpx/pydantic/stripe/uvicorn),
  functions `fastapi_app` + `reconcile_tick` created, `Serving... Watching ./modal_backend` — **no traceback;
  startup succeeds** in this environment (modal 1.6.3, secret `hybridpay-test` present).
- **Root-cause analysis (no failure to fix, hardened instead)**:
  - Working directory: repo root `/workspaces/Universal-Fiat-Crypto-Financial-Terminal`; Modal uploads
    `modal_backend/app.py` as a package (`modal_backend/__init__.py` present) so relative import
    `from .api import app` resolves under both `modal serve` and `python -c "import modal_backend.app"`.
  - Deps: `requirements.txt` pins == image pins in `app.py` (fastapi 0.115.6, uvicorn 0.34.0,
    pydantic 2.10.4, httpx 0.28.1, stripe 11.3.0); local interpreter is 3.14.2 vs image 3.11 —
    local-only skew, image is authoritative and builds clean.
  - Config: `app = modal.App("hybridpay-sandbox")`, CPU-only (`cpu 0.5/0.25`, `memory 512/256`),
    no GPU args, `min_containers=0`, no `schedule=` (removed for cost control), secrets via
    `modal.Secret.from_name("hybridpay-test")` — verified present (`modal secret list`).
  - Import check: `python -c "import modal_backend.app; import modal_backend.api"` → OK, 13 routes.
- **Verify**: `API_SHARED_TOKEN=dev-shared-token uvicorn modal_backend.api:app --port 8123` →
  `GET /health` → `{"ok":true,"liveMode":"OFF","sandbox":true}`; `pytest modal_backend/` → **101 passed, 4 skipped** (Dec 2026: +35 AI/institutional guardrail tests).
  Dev serve not left running (operator step; needs `modal token` on their machine).

## 2. Requirement audit (fiat / crypto / contracts / AI / frontend / db / auth / deploy)
| Area | Status | Evidence |
|---|---|---|
| Fiat sandbox E2E | ✅ implemented + tested | `payments.py` (ABC + Mock + Stripe TEST), `db.py` (SQLite), 7 fiat endpoints, `test_fiat_payments.py` 7/7, `docs/fiat-sandbox.md` |
| Stripe test mode | ✅ implemented, mocked-tested; live-network run documented, not executed here | `StripeTestProvider` (`sk_test_*` enforced), factory fallback to mock, `docs/fiat-sandbox.md` integration steps |
| Crypto testnet | ✅ implemented, partially tested | `crypto/simulate` + regtest validation, `test_modal_backend.py`; full regtest stack needs docker profile (not run) |
| Programmable contracts | ✅ implemented + tested | `contracts.py` allowlist validator + `validate_terms` tests; on-chain contracts out of scope (see `docs/real-money-roadmap.md`) |
| AI integration | ✅ implemented + tested | explain fiat/crypto, contract analysis, fraud (NOT certified), routing, state explainer, assistant (read-only, safe actions) + usage endpoint; mocked tests + opt-in live; `docs/ai-integration.md` |
| Frontend | ✅ implemented + tested | Banking (6 modules: overview/ops/contracts/risk/admin/analytics, maker-checker) + Personal (7 screens: dash/send/receive/program/assistant/history/settings) + design system; mocked tests; builds green |
| Database | ✅ implemented + tested | `db.py` SQLite durable (+ evm_payments, contract_agreements) + persist tests; Postgres remains system of record for Nest API |
| Auth | ✅ implemented + tested | bearer + tenant guards, 401/400 paths tested, CORS allowlist tested |
| Deploy | 🟡 code-ready, NOT deployed | `modal serve` verified locally; `modal deploy` is an operator step (no approval given) — see `docs/modal-deploy-checklist.md` |

## 3. Implemented and verified (executed in this session)
- `modal serve modal_backend/app.py` → Serving, no error.
- `pnpm build` → 9/9 green. `pnpm test` → 11/11 suites green (sdk 6, terminal 5 incl. evm + programmable E2E).
- `pytest modal_backend/` → all green incl. `test_evm_payments.py` (6 passed, 1 skipped opt-in live RPC)
  and `test_programmable_contracts.py` (5 passed).
- `node --test tests/property tests/integration` (explicit files) → 4/4.
- `POST /api/payments/fiat/simulate` live local → 201 `AUTHORIZED`; `/health` → `liveMode OFF`.

## 3b. Financial rights + PDP + guardrails (2026-11-02, executed, sandbox only)- `pytest modal_backend/` → **147 passed, 4 skipped** (was 101/4; +15
  `test_financial_rights.py`, +12 `test_pdp.py`, +6 `test_rights_api.py`, +13
  `test_agreement_guardrails.py`). New code:
  `modal_backend/financial_rights/` (engine, jurisdictions, appeals, monitoring),
  `modal_backend/pdp/` (embedded PDP `POLICY_BUNDLE_VERSION=2026.11.02-v1` +
  FastAPI enforcement), `modal_backend/rights_api.py` (9 rights/PDP routes),
  migration `005_rights_pdp.sql`, hardening in `programmable.py`/`evm.py`/`api.py`
  (terms-hash binding, versioned amend, chain-bound EVM ids, tx-hash replay
  refusal, `require_policy()` on 5 sensitive endpoints).
- Two pre-existing tests updated for intentional behavior tightening (not
  regressions): `test_migrations.py` (new migration file in expected list),
  `test_evm_payments.py` (same tx hash on two payments is now 409 REPLAY).
- Verified live-local: restriction create → 201 (notifyCustomer true),
  gag-order legal restriction → notifyCustomer false + audited, AI-score-only
  → 422, appeal overturn → restriction lifted + correctionPlan, PDP simulate
  cross-tenant → deny, `GET /api/pdp/policy-version` pinned.
- No auto-deploy performed (`modal deploy` NOT run — explicit operator step).

## 3c. Security audit + approval binding + independent audit (2026-11-02, sandbox only)
- `pytest modal_backend/` → **182 passed, 4 skipped** (+35: 15 `test_security_audit.py`
  scenarios S1–S15, 11 `test_approval_binding.py`, 9 `test_audit_integrity.py`).
- New: `approval_binding.py` + `approval_api.py` (canonical `ab-v1` digests, credId
  alt-account resistance, atomic single-use consume wired into fiat cancel/refund +
  agreement execute), `audit_store.py` + `audit_api.py` (structured chain, HMAC option,
  fail-closed writes, JSONL export + outbox, auditor dashboard), migration
  `006_approval_audit.sql`.
- Fixed: STRICT expiry+amount (F-01); legacy digest-less approvals (F-02, bindings);
  unconsumed intents (F-03, consume-before-provider on binding paths); audit gaps
  (F-05); auditor lockout (F-06). Residual R-03/R-04/R-05/R-07/R-08/R-10 planned.
- Docs: `SECURITY_AUDIT.md`, `GUARDRAIL_TEST_REPORT.md`, `THREAT_MODEL.md`,
  `REMEDIATION_PLAN.md`, `APPROVAL_BINDING_SECURITY.md`, `AUDIT_ARCHITECTURE.md`,
  `AUDIT_INTEGRITY_TEST_REPORT.md`. No auto-deploy; no production capabilities added.

## 3d. Break-glass + AI isolation + disputes (2026-11-02, sandbox only)
- `pytest modal_backend/` → **207 passed, 4 skipped** (+25: 9 `test_breakglass.py`,
  8 `test_ai_control.py`, 8 `test_disputes.py`); terminal vitest 25/25 (incl. new
  `disputes.test.ts`); `next build` green with Personal Disputes tab + Banking
  review queue.
- New: `breakglass.py` + `breakglass_api.py` (session gateway, no money/signing/
  audit powers by construction), `ai_guardrails/control.py` (distributed kill
  switch, per-feature flags, circuit breaker, dual-control re-enable),
  `disputes.py` + `dispute_api.py` (metadata-only evidence, independent review,
  no automatic refunds), migration `007_breakglass_ai_disputes.sql`.
- Fixed during testing: unguarded `/ai/analyze`; `invoke_tool` skipped
  authorization; session response `id` vs `sessionId`; evidence placeholder
  count; StatusBadge API usage; comment-semicolon migration syntax.
- Docs: `BREAK_GLASS_POLICY.md`, `BREAK_GLASS_TEST_REPORT.md`,
  `AI_EMERGENCY_RESPONSE.md`, `AI_KILL_SWITCH_TEST_REPORT.md`,
  `DISPUTE_HANDLING_POLICY.md`, `CUSTOMER_RIGHTS_WORKFLOW.md`.
  No auto-deploy; sandbox/testnet only.

## 3e. Security integration audit (2026-11-02, sandbox only)
- `pytest modal_backend/` → **217 passed, 4 skipped** (+10
  `test_security_integration.py`: high-risk auth, approval-reuse e2e,
  fail-closed outage, cross-module tenant isolation, role-split disputes).
- Fixed: `ai/analyze` tenant scope + feature flag; binding + fail-closed audit
  on amend/cancel/dispute; unified `must_audit_or_503` (was 500/503 mixed);
  structured audit for restriction appeals. Full-suite + frontend green;
  backend boot + 85 OpenAPI paths verified; `next build` green.
- Docs: `SECURITY_INTEGRATION_AUDIT.md` (PASS/FAIL/NOT IMPLEMENTED/NOT TESTED),
  `SECURITY_CONTROL_MATRIX.md`, `REMAINING_RISKS.md` (R-11/R-12, O-01…O-04,
  L-01…L-04), `DEPLOYMENT_READINESS.md` (sandbox READY; staging/production
  NOT READY; 4 live skips enumerated, untested areas listed).
  No auto-deploy; no real customer data.

## 4. Implemented but NOT live-tested (needs operator key/infra)
- Stripe TEST network calls (`StripeTestProvider.create/confirm/retrieve`) — mocked path tested; real
  `sk_test_*` exchange documented in `docs/fiat-sandbox.md`, not executed (no key provided).
- Sepolia live RPC receipt check — mocked JSON-RPC tested; read-only live run documented in
  `docs/evm-sepolia.md`, not executed (no RPC URL / known tx provided).
- BTCPay regtest stack (docker profile bitcoind + btcpay) — code ready, `SANDBOX_BLOCKED` without creds.
- Meta model live call — skipped by design (`RUN_META_INTEGRATION` unset).
- `modal deploy` — not run (explicitly withheld without approval).

## 5. Missing / out of scope for this session
- On-chain smart contracts (Solidity/Vyper + audit) — roadmap only (`docs/real-money-roadmap.md`).
- Fiscal (NRA H-18) integration, KYC/KYB vendor wiring, mainnet/CASP — roadmap only.
- Postgres-backed Modal writes (SQLite file is the durable store for the sandbox backend; Postgres stays
  behind `apps/api`).

## 6. Blocking issues
- None for sandbox/demo. Live money is blocked by design (no approval file, no live creds — fail-closed).

## 7. Exact next steps
1. Operator: `modal serve modal_backend/app.py`, run `docs/modal-deploy-checklist.md` §§3+6 (health + UI + simulator 5/5).
2. Optional Stripe TEST: follow `docs/fiat-sandbox.md` integration steps with `sk_test_*`, record paymentId/state/webhook count.
3. Optional regtest: `docker compose --profile btc up`, set `BTCPAY_*_TEST`, rerun crypto tests.
4. For production: work through `docs/real-money-roadmap.md` in order (license/partner → fiscal/KYC → mainnet → CASP → audited contracts).

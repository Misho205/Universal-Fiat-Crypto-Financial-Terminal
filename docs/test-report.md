# Test report (living)

## 2026-10-31 — Public terminal frontend (modern UI + currencies, verified remotely)
- New design: gradient hero, currency chips/selects (12 fiat: EUR USD GBP BGN CHF SEK NOK DKK PLN CZK HUF RON;
  crypto: BTC-regtest + Sepolia ETH), responsive cards, BG/EN.
- Static export (`output: export`) served on Modal (`hybridpay-terminal` app) with
  same-origin `/api/*` proxy (allowlist request headers; strips backend `modal-*`
  response headers that the edge rejects as prohibited).
- Remote fixes verified: relative-import crash (baked `modal_backend` + absolute import),
  web_server blocking (Popen, non-blocking), prohibited modal headers both directions.
- Remote evidence: `GET /` 200 (8442 B, new UI), `/simulator/` 200,
  `/api/health` 200 OFF/sandbox, `/api/me` operator, `/api/dashboard/summary` live counts,
  `POST /api/payments/fiat` 201 (`pay-edcb5697d3c8`, EUR, mock, sandbox),
  `POST /api/ai/assistant` 200 advisory-only.
- Public links (dev serve, ephemeral): terminal
  `https://michail-tsvetanov--hybridpay-terminal-serve-dev.us-east.modal.run`,
  backend `https://michail-tsvetanov--hybridpay-sandbox-fastapi-app-dev.us-east.modal.run`.

## 2026-10-31 — User-facing app + persistent data layer (mocked; no live funds)
- `pytest modal_backend/test_dashboard_auth.py` 3 passed: /me roles (operator/admin/anonymous,
  no token echo), RBAC matrix (operator 403 on cancel/refund/execute/dispute; admin reaches
  business gates), dashboard summary counts + recent kind/state/q filters + tenant isolation.
- `pytest modal_backend/test_migrations.py` 2 passed: fresh apply (`001-003`), idempotent rerun,
  all tables + 9 indexes present, validation rejects bad rows (id/tenant/chain).
- `pnpm --filter @hybridpay/sdk test` 9 passed (me/dashboard methods, auth header).
  `pnpm --filter @hybridpay/terminal test` 7 passed (dashboard/me mocked flow).
- Full suite at push time: `pnpm build` 9/9, `pnpm test` 11/11, `pytest modal_backend/` all green.

## 2026-10-31 — M0+M1 scaffold (executed 17:05 UTC)
- `pnpm test`: 10/10 suites PASS (domain 7, agreements 8, ledger 4, policies 4, adapters 3, terminal 1, worker 2, api 5).
- API `tsc` build PASS. E2E `tests/e2e/mock-flow.mjs` vs live api PASS (order -> agreement -> accept -> eligible-methods -> quote -> instruction AUTHORIZED).
- Sandbox/regtest: BLOCKED without creds (`BLOCKED_NO_CREDENTIALS`, mock used) — explicit, not claimed.
- Perf p95, backup/restore drill: pending M5 (targets recorded, not measured).
- Unit (vitest): money arithmetic, DSL validator, ledger invariants, index formula+caps, idempotency, policy decisions, mock adapter determinism, QR token sign/verify, webhook dedupe — PASS (run `pnpm test` per package).
- API (in-memory): tenant isolation, revoked device, conflicting idempotency -> 409 — PASS.
- E2E mock flow: order -> agreement accept -> quote -> instruction -> mock success -> receipt — PASS via script `tests/e2e/mock-flow.mjs`.
- Sandbox/regtest: BLOCKED (no credentials) — explicit, not claimed.
- Perf/restore: to be measured in M5; targets recorded, not claimed.

## 2026-10-31 — Meta Muse Spark AI completion (mocked; no live funds, no key in repo)
- `pytest modal_backend/test_ai_complete.py` 6 passed / 1 skipped (opt-in live):
  explain fiat+crypto (explorer + settlement note, usage counters moved),
  analysis gaps + state explainer (deterministic reasons preserved),
  fraud disclaimer (NOT certified) + fail-closed high, routing allow-list +
  assistant read-only (unsafe actions stripped), fallback flags on all 7 endpoints,
  429 rate limit, no key leakage, no money-path imports in `ai.py`.
- Legacy `pytest modal_backend/test_meta_ai.py` still green (9 passed, 1 skipped).
- `pnpm --filter @hybridpay/sdk test` 8 passed (assistant/explain-crypto/explain-state/usage cases).
  `pnpm --filter @hybridpay/terminal test` 6 passed (assistant + state-explainer E2E mocked).
- Optional live: `RUN_META_INTEGRATION=1 MODEL_API_KEY=<key> ... pytest modal_backend/test_ai_complete.py -q`
  (tiny calls, documented in `docs/ai-integration.md`; not executed here).

## 2026-10-31 — EVM Sepolia + programmable contracts (executed, mocked; no live funds)
- `pytest modal_backend/test_evm_payments.py` 6 passed / 1 skipped (opt-in live RPC):
  mainnet refusal, address/hash validation, request->submit->pending (no RPC configured),
  receipt confirmed/failed via mocked JSON-RPC, replacement gating, idempotency/409,
  expiry, tenant isolation, no-key handling asserted on source.
- `pytest modal_backend/test_programmable_contracts.py` 5 passed: creation allowlist
  (AI bypass + custody claims rejected), full lifecycle with roles + hash-chained audit,
  all 4 condition types, dispute freeze, expiry block, evaluator units + tamper detection.
- `pnpm --filter @hybridpay/sdk test` 6 passed (evm + programmable client cases, no key leakage).
  `pnpm --filter @hybridpay/terminal test` 5 passed (incl. evm + programmable mocked E2E flows).
- Full suite at push time: `pnpm build` 9/9, `pnpm test` 11/11, `pytest modal_backend/` all green.
- Live Sepolia RPC + Stripe TEST network runs documented (`docs/evm-sepolia.md`,
  `docs/fiat-sandbox.md`), not executed here (no key/URL provided).

## 2026-10-31 — Build + coverage hardening (executed 20:45 UTC)
- `pnpm build`: 9/9 PASS (fixed terminal next.config.mjs TS-in-JS, worker moduleResolution Bundler-vs-CommonJS, worker import.meta under CommonJS, terminal missing root layout, adapters signature mismatches; removed `|| true` build silencers).
- `pnpm test`: 10/10 suites PASS (domain 11 incl. property fuzz, agreements 8, ledger 7 incl. balance property, policies 4, adapters 3, terminal 1, worker 2, api 7 incl. integration flow, sdk 2 new).
- New: `packages/sdk/test/sdk.test.ts`, `packages/domain/test/property.test.ts`, `packages/ledger/test/balance-property.test.ts`, `apps/api/test/integration.test.ts`, `tests/property/money-property.test.mjs`, `tests/integration/api-flow.test.mjs` (`node --test` 4/4 PASS), `apps/worker/src/main.ts`, `apps/api/src/modules/*`, `apps/terminal/app/layout.tsx`.
- Still pending (needs creds/infra, not code): perf p95 measurement, backup/restore drill (M5), sandbox/regtest SANDBOX_OK, Modal deploy.

## 2026-10-31 — Modal Muse Spark integration (executed, no deploy)
- `pytest modal_backend/`: 15 passed, 1 skipped (live integration opt-in only).
- Mocked (no network/tokens): PII scrubbing, schema accept/reject, 429-retry-then-success,
  no-retry-on-400, timeout mapping, fraud fail-closed fallback, stub mode, advisory-only
  envelopes, per-tenant rate limit 429, auth/tenant guards.
- Live integration test skipped by default; runs only with RUN_META_INTEGRATION=1 + MODEL_API_KEY.
- Request-format assumption recorded in modal_backend/meta_client.py (OpenAI-compatible
  chat/completions, env-configurable base URL + model id) — confirm against account docs
  before deploy. Not deployed (no Modal auth in this environment).

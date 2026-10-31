# Test report (living)

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

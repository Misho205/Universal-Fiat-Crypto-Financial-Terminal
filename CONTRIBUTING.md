# Contributing

## Ground rules
- Sandbox/testnet only. Never commit secrets (`.env` is gitignored; only `*_TEST` placeholders in `.env.example`).
- Money code: exact decimals as strings, integer minor units in storage, balanced per-asset journals.
- Every money path needs: idempotency key, tenant scoping, fail-closed auth, and a test (mocked provider).
- AI is advisory only — it must never import provider/payment modules or change payment state.
- Run before pushing: `pnpm build`, `pnpm test`, `HYBRIDPAY_DB_MEMORY=1 API_SHARED_TOKEN=dev-shared-token pytest modal_backend/ -q`.

## Layout
`apps/terminal` (Next.js) · `apps/api` (NestJS, system of record) · `apps/worker` (Temporal) ·
`packages/*` (domain, agreements, ledger, policies, adapters, sdk) ·
`modal_backend/` (FastAPI sandbox) · `migrations/` · `infra/` · `docs/` · `tests/`.

## Adding a provider
1. Implement `PaymentProvider` in `modal_backend/payments.py` (or `PaymentAdapter` in `packages/adapters`).
2. Map all outcomes into the lifecycle (`created/pending/succeeded/failed/canceled/refunded/unknown`).
3. Refuse live credentials in sandbox code paths; gate live behind `docs/live-mode.md`.
4. Add mocked tests + document the sandbox run in `docs/fiat-sandbox.md` (or provider-capabilities).

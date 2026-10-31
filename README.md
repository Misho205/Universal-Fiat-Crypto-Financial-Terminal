# HybridPay Terminal — merchant web/PWA terminal + customer QR checkout with deterministic conditional-payment engine.

> Live mode OFF. No custody of merchant keys. Technical receipt is NOT a fiscal receipt.

## Quickstart (M1)
1. `cp .env.example .env`
2. `docker compose -f infra/docker-compose.yml up -d postgres redis temporal opa otel`
3. `pnpm install && pnpm test` (10 suites green)
4. `psql $DATABASE_URL -f migrations/001_init.sql`
5. Run api: `pnpm --filter @hybridpay/api build && PORT_API=3001 node apps/api/dist/main.js`
6. E2E mock: `API_BASE=http://localhost:3001 node tests/e2e/mock-flow.mjs`
7. Terminal: `pnpm --filter @hybridpay/terminal dev` (BG/EN toggle, QR payload from checkout-token endpoint)

## Layout
apps/terminal (Next.js PWA, bg/en), apps/api (NestJS modular monolith), apps/worker (Temporal activities/workflows),
packages/domain|agreements|ledger|policies|adapters|sdk, infra/docker-compose.yml, migrations/, docs/, tests/e2e.

## Docs
docs/PRMD.md→PRD.md, architecture.md, threat-model.md, money-flows.md, provider-capabilities.md (verified 2026-10-31),
regulatory-boundaries.md, ADRs/, deployment.md, credentials-runbook.md, test-report.md. OpenAPI: apps/api/openapi.yaml.

## Money safety
Exact-decimal strings + BIGINT minor/atomic units; balanced per-asset journal; idempotency `tenant:op:sha256(content)` with 409 on conflict;
tenant-scoped queries; revoked-device fail-closed; atomic day-limit reservations; UNKNOWN + reconcile, no unsafe failover.
Stripe sandbox = Direct charges; BTCPay = regtest invoices; both BLOCKED without TEST creds (mock used). Live disabled.

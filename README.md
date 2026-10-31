# Universal Hybrid Payment Terminal (HybridPay)

Merchant web/PWA terminal + customer QR checkout with a deterministic conditional-payment
("fiat smart contract") engine, crypto testnet support, advisory AI, and a Modal sandbox backend
for hackathon demos.

> **Live mode OFF.** Sandbox/testnet only. No custody of merchant keys. No real money can move
> (fail-closed without a signed live approval + live credentials, which are absent).
> Technical receipt is NOT a fiscal receipt.

## What is here
- **Terminal** (`apps/terminal`, Next.js, BG/EN): unified **Dashboard** (summary cards +
  filterable history), order/QR, fiat sandbox, crypto testnet,
  **EVM Sepolia** (wallet connect via viem, sign-in-wallet, receipt + explorer links),
  **Agreements** (programmable fiat contracts: create/monitor/execute), contract validator,
  transaction status + **AI assistant** (validated, fallback-safe, read-only), visual **simulator** (`/simulator`) for human trial tests.
  Responsive (mobile/desktop), keyboard-focus visible, `aria-live` states, memory-only session token + role badge.
- **NestJS API** (`apps/api`): modular monolith, system of record (PostgreSQL + Prisma migrations).
- **Worker** (`apps/worker`): Temporal activities/workflows (provider calls live outside DB tx).
- **Modal backend** (`modal_backend/`, FastAPI): stateless executor + **advisory AI**
  (explain fiat/crypto, contract analysis, fraud indicators, routing, agreement-state
  explainer, natural-language assistant — all validated, all fallback-safe, key server-side),
  role-based auth (operator/admin bearer, server-enforced) + `/api/me`,
  unified dashboard (`/api/dashboard/summary|recent`),
  fiat sandbox payments E2E (`POST /api/payments/fiat` → `/confirm` → retrieve/cancel/refund),
  HMAC-verified Stripe webhook, **EVM Sepolia tracking** (`/api/payments/evm/*`: request/submit/
  receipt/replace/list, mainnet refused), **programmable agreements** (`/api/contracts/programmable/*`:
  create/activate/approve/evidence/execute/cancel/dispute with audit chain),
  durable store (SQLite on Modal Volume `/mnt/data`, or Postgres via `DATABASE_URL`;
  versioned migrations; Postgres stays system of record for Nest API).
- **Packages**: `domain` (exact money), `agreements` (DSL validator), `ledger` (balanced journal),
  `policies` (OPA), `adapters` (mock/Stripe-sandbox/BTCPay-regtest), `sdk` (typed browser client).

## Quickstart (local, sandbox)
1. `cp .env.example .env` — keep `LIVE_MODE=false`; fill only `*_TEST` keys. Frontend uses only
   `NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_MODAL_API_URL`, `NEXT_PUBLIC_API_TOKEN` (sandbox bearer,
   memory-only session). Backend roles: `API_SHARED_TOKEN` (operator) + `API_ADMIN_TOKEN`
   (admin: cancel/refund/dispute/execute).
2. `docker compose -f infra/docker-compose.yml up -d postgres redis temporal opa otel`
3. `pnpm install && pnpm build && pnpm test` (9/9 builds, 11/11 suites green)
4. `psql $DATABASE_URL -f migrations/001_init.sql`
5. Nest API: `pnpm --filter @hybridpay/api build && PORT_API=3001 node apps/api/dist/main.js`
6. Modal backend (local): `API_SHARED_TOKEN=dev-shared-token API_ADMIN_TOKEN=dev-admin-token uvicorn modal_backend.api:app --port 8000`
7. Terminal: `pnpm --filter @hybridpay/terminal dev` → `http://localhost:3000` (Dashboard tab default, `/simulator`)
8. E2E: `API_BASE=http://localhost:3001 node tests/e2e/mock-flow.mjs`;
   `API_SHARED_TOKEN=dev-shared-token API_ADMIN_TOKEN=dev-admin-token pytest modal_backend/ -q`
9. Database: SQLite `./data/hybridpay.db` by default; Postgres via `DATABASE_URL`; Modal Volume
   `/mnt/data`; migrations in `modal_backend/migrations/` — see `docs/database.md`.

## Modal (operator step — no auto-deploy)
`modal serve modal_backend/app.py` (preview) / `modal deploy modal_backend/app.py` (demo only).
Full checklist, secrets, costs, verification, rollback, readiness: `docs/modal-deploy-checklist.md`.
`modal secret list` must show `hybridpay-test`; `/health` must report `liveMode: OFF`.

## Docs (start here)
- `IMPLEMENTATION_STATUS.md` — what works / what was tested / exact next steps (no invented results).
- `docs/fiat-sandbox.md` — fiat E2E architecture + mocked tests + documented Stripe TEST run.
- `docs/modal-deploy-checklist.md` — deploy procedure, verification, rollback, costs, readiness.
- `docs/live-mode.md` — LIVE guardrails (fail-closed).
- `docs/real-money-roadmap.md` — what real money + on-chain contracts require (license, fiscal, KYC, audit).
- `docs/PRD.md`, `docs/architecture.md`, `docs/money-flows.md`, `docs/provider-capabilities.md`,
  `docs/threat-model.md`, `docs/regulatory-boundaries.md`, `docs/deployment.md`,
  `docs/credentials-runbook.md`, `docs/test-report.md`, `docs/ADRs/`. OpenAPI: `apps/api/openapi.yaml`.
- `docs/database.md`, `docs/fiat-sandbox.md`, `docs/evm-sepolia.md`, `docs/programmable-contracts.md`,
  `docs/ai-integration.md`, `docs/modal-deploy-checklist.md`, `docs/live-mode.md`,
  `docs/real-money-roadmap.md`, `IMPLEMENTATION_STATUS.md`, `CONTRIBUTING.md`, `SECURITY.md`.
- `CONTRIBUTING.md`, `SECURITY.md`, `CHANGELOG.md`.

## Money safety (enforced, tested)
Exact-decimal strings + BIGINT minor/atomic units; balanced per-asset journal; idempotency
`tenant:op:sha256(content)` with 409 on conflict; tenant-scoped queries; revoked-device fail-closed;
atomic day-limit reservations; UNKNOWN + reconcile, no unsafe failover; provider status always
authoritative (frontend never marks success); AI advisory-only, never moves funds.

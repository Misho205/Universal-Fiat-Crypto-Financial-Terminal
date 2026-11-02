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
  Design system (`/design-system` showcase): Tailwind + tokens, light/dark themes, shadcn-style
  components, Lucide icons, accessible charts. **Banking Workspace** (`/banking`, admin-gated:
  overview, operations, contracts, **approvals (maker-checker intents)**, risk, admin, analytics, assistant) + **Personal Workspace**
  (`/personal`: dash, send, receive, program, assistant, history, settings). Responsive (mobile/desktop), keyboard-focus visible,
  `aria-live` states, memory-only session token + role badge. Architecture: `FRONTEND_IMPLEMENTATION_PLAN.md`.
  Embeddable (`?embed=1` chrome-less iframe) and white-labelable (`NEXT_PUBLIC_BRAND_*`,
  CSS variables) — see `docs/white-label-embed.md`; bank/exchange onboarding in
  `docs/bank-integration-guide.md`.
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
  Readiness probe `GET /ready` (migrations + store) for bank load-balancers;
  AI guardrails (`modal_backend/ai_guardrails/`, default-deny policy engine,
  allowlisted read-only tools, injection screening, kill-switch) + institutional
  guardrails (`modal_backend/institutional.py`, maker-checker intents, quorums,
  JIT, emergency, tamper-evident audit) — see `AI_SECURITY_POLICY.md`,
  `AI_TOOL_PERMISSIONS.md`, `AI_RED_TEAM_TESTS.md`.
- **Financial Rights Protection** (`modal_backend/financial_rights/`, migration
  `005_rights_pdp.sql`): explicit legal/contractual grounds, reason codes +
  evidence, proportionality, time limits + review deadlines, independent review,
  appeals with correction/restoration, AI-scores-never-auto-enforce,
  jurisdiction profiles with legal-review gate, abuse monitoring —
  see `FINANCIAL_RIGHTS_POLICY.md`, `RESTRICTION_REVIEW_WORKFLOW.md`,
  `CUSTOMER_APPEALS_SPEC.md`.
- **Centralized PDP/PEL** (`modal_backend/pdp/`): embedded deterministic
  default-deny policy decision point (OPA-vs-Cerbos evaluation:
  `docs/PDP_EVALUATION.md`), 23-action matrix (`docs/POLICY_MATRIX.md`),
  enforcement on all sensitive endpoints, simulation + decision audit.
- **Agreement/crypto guardrails**: terms-hash binding, versioned amendments
  (dual consent), replay/double-execution protection, chain-bound EVM ids,
  wallet-side signing only — see `docs/AGREEMENT_CRYPTO_GUARDRAILS.md`.
- **Cryptographic approval binding** (`modal_backend/approval_binding.py`, migration
  `006_approval_audit.sql`): canonical op digests (SHA-256), single-use atomic
  consume, alt-account-resistant maker-checker, expiry+amount revalidation —
  see `APPROVAL_BINDING_SECURITY.md`.
- **Independent audit storage** (`modal_backend/audit_store.py`): structured
  append-only events, hash-chained with seq, HMAC option, fail-closed writes,
  JSONL export + outbox, read-only auditor dashboard — see
  `AUDIT_ARCHITECTURE.md`, `AUDIT_INTEGRITY_TEST_REPORT.md`.
- **Security audit package**: `SECURITY_AUDIT.md` (15 scenarios), `GUARDRAIL_TEST_REPORT.md`,
  `THREAT_MODEL.md`, `REMEDIATION_PLAN.md`. Tests are evidence, not guarantees.
- **Packages**: `domain` (exact money), `agreements` (DSL validator), `ledger` (balanced journal),
  `policies` (OPA Rego mirror for the NestJS/docker path; the Modal runtime PDP is
  the embedded `modal_backend/pdp/` — see `docs/PDP_EVALUATION.md`),
  `adapters` (mock/Stripe-sandbox/BTCPay-regtest), `sdk` (typed browser client).

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
- `docs/bank-integration-guide.md` — embed the terminal in a bank/exchange (iframe, white-label, headless API, webhooks, go-live gates).
- `docs/white-label-embed.md` — `?embed=1`, `NEXT_PUBLIC_BRAND_*`, palette overrides.
- `AI_SECURITY_POLICY.md`, `AI_TOOL_PERMISSIONS.md`, `AI_RED_TEAM_TESTS.md` — AI + institutional guardrails.
- `FINANCIAL_RIGHTS_POLICY.md`, `RESTRICTION_REVIEW_WORKFLOW.md`, `CUSTOMER_APPEALS_SPEC.md` — financial rights, review, appeals.
- `docs/PDP_EVALUATION.md`, `docs/POLICY_MATRIX.md` — centralized PDP (OPA-vs-Cerbos selection) + authorization matrix.
- `docs/AGREEMENT_CRYPTO_GUARDRAILS.md` — programmable-agreement + Sepolia guardrails, adversarial coverage.
- `SECURITY_AUDIT.md`, `GUARDRAIL_TEST_REPORT.md`, `THREAT_MODEL.md`, `REMEDIATION_PLAN.md` — independent audit (15 scenarios), findings, residual risks.
- `APPROVAL_BINDING_SECURITY.md`, `AUDIT_ARCHITECTURE.md`, `AUDIT_INTEGRITY_TEST_REPORT.md` — digest-bound approvals, independent audit storage.
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

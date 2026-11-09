# HybridPay — System Inventory (Phase 1)

> Prototype audit. No claim of legal compliance, certification, regulatory
> authorization, or production readiness. Sandbox/testnet only. `LIVE_MODE=OFF`
> default, fail-closed. Branch: `audit/eu-security-readiness-2026-11-09`.
> Evidence verified against code on this branch; file:line references are
> the source of truth, not prior reports.

## 1. Repository layout

| Path | Purpose | Notes |
|---|---|---|
| `apps/terminal/` | Next.js 15 frontend (Dashboard, Personal, Banking, Private, Simulator, design-system) | `app/page.tsx`, `app/personal/page.tsx`, `app/banking/page.tsx`, `app/private/page.tsx`, `app/simulator/page.tsx`; `src/components/session.tsx` (memory-only token), `src/simulator-results.ts` (result mapper) |
| `packages/sdk/src/index.ts` | Browser API client (`ModalBackendClient`, `HybridPayClient`) | `resolveBaseUrl()` → `NEXT_PUBLIC_MODAL_API_URL \|\| NEXT_PUBLIC_API_URL \|\| localhost:8000`; network failure → `503 Backend unreachable`, no silent fallback |
| `packages/domain|ledger|agreements|policies|adapters` | Money math, balanced journal, DSL validator, OPA Rego mirror, mock/Stripe-sandbox/BTCPay-regtest adapters | Exact-decimal strings; Nest/docker path only for `policies` Rego |
| `apps/api/src/` | NestJS modular monolith (system of record: Postgres + Prisma) | `main.ts:7` `app.enableCors()` — open, no allowlist (finding, §7) |
| `apps/worker/src/` | Temporal workflows/activities | Provider calls outside DB tx; no live server in scope |
| `modal_backend/` | FastAPI sandbox executor + advisory AI (demo backend) | `api.py` (1737 lines, all routes), `auth.py`, `config.py`, `payments.py`, `evm.py`, `contracts.py`+`programmable.py`, `pdp/`, `ai.py`+`meta_client.py`+`ai_guardrails/`, `approval_binding.py`, `audit_store.py`, `breakglass.py`, `disputes.py`, `institutional.py`, `rights_api/store`, `financial_rights/`, `db.py`/`store.py`, `app.py` (Modal) |
| `modal_backend/migrations/` | Versioned DDL `001_core`–`007_breakglass_ai_disputes.sql` | Durable store; `db.migrate()` on `/ready` |
| `migrations/001_init.sql`, `schema.prisma` | NestJS Postgres mirror | Tenant/Order/Instruction/Journal/Outbox/Inbox |
| `infra/docker-compose.yml` | Local postgres/redis/temporal/opa/otel | No secrets; `hybridpay:hybridpay` dev-only |
| `modal_frontend.py`, `modal_site_server.py` | Static Next.js hosting + same-origin `/api/*` proxy | Frontend holds no secrets |
| `tests/e2e|integration|property` | Mock flow, API flow, money-property tests | — |
| `modal_backend/test_*.py` (30 files) | Backend regression suite | fiat/evm/tenant/approval/audit/breakglass/disputes/AI/PDP/live-mode/load |
| `.env.example` / `.env` | Example vs local runtime env | `.env` exists locally, gitignored (`check-ignore` OK), **not tracked** — content never read per rules |
| `docs/` | Architecture, threat model, guardrail reports, deploy gates | See `IMPLEMENTATION_STATUS.md`, `SECURITY_AUDIT.md`, `THREAT_MODEL.md` |

## 2. Runtime topology (sandbox)

```
Browser (apps/terminal, memory-only bearer)
  → Modal FastAPI (modal_backend/api.py) → MockFiatProvider (default)
  │                                      → StripeTestProvider (only if sk_test_* set)
  │                                      → Sepolia RPC read-only (evm.py, chainId 11155111 only)
  │                                      → Meta Muse Spark (meta_client.py, scrubbed prompts)
  → NestJS apps/api (Postgres system of record, local/docker path)
  → SQLite ./data/hybridpay.db | Modal Volume /mnt/data | Postgres via DATABASE_URL
```

- Money movement: none live. `config.live_mode_status()` = OFF default; BLOCKED if `LIVE_MODE=true` without signed `LIVE_APPROVAL_FILE`; ON-APPROVED only with both (absent in demo). `assert_sandbox()` fail-closed (`config.py:89-93`).
- Frontend never signs EVM: wallet (viem/`window.ethereum`) signs; backend tracks only.

## 3. API surface (modal_backend/api.py, verified)

- Health: `GET /health` (liveMode flag), `GET /ready` (migrations+store, unauth by design), `GET /api/me`, `GET /admin/overview`.
- Fiat sandbox: `POST /api/payments/fiat → POST /confirm → GET /retrieve → GET /list → POST /cancel (admin) → POST /refund (admin)`; `POST /simulate`, `POST /webhooks/stripe[/test]`, `GET /api/transactions/{id}`.
- EVM Sepolia: `POST /request|/{id}/submit|/{id}/replace`, `GET /list|/{id}`; mainnet refused.
- Agreements: `POST /contracts/programmable/* (create/activate/approve/evidence/amend/execute/cancel/dispute)`, `GET`, `POST /contracts/validate`.
- AI advisory-only: `POST /api/ai/* (analyze, explain-*, fraud, routing, contract, assistant, decision)`, `GET /usage|/policy`, `POST /admin/ai/*`. All return `{advisoryOnly:true, validated}`; fraud fails closed to `high` without key.
- Governance: approvals intents (`/api/approvals/intents[/{id}/approve]`), elevation/emergency, grants/audit, breakglass, disputes, rights routers.

## 4. Payment state machines (verified)

- Fiat `STATES` (`payments.py:26`): `created, pending, succeeded, failed, canceled, refunded, unknown`. Create→pending; confirm→succeeded|failed|TIMEOUT_UNKNOWN→unknown (never fake success); cancel only non-terminal (admin); refund only succeeded (admin). Provider status authoritative; frontend never marks success.
- EVM (`evm.py`): `requested, pending, confirmed, failed, expired, replaced`; Sepolia `11155111` only; confirmations ≥ 2.
- Agreements: `draft→active→conditions_pending→eligible_for_execution→completed|canceled|expired|disputed`; `AMENDABLE=(draft,active,conditions_pending)`; custody language rejected.
- Simulator mapping (`apps/terminal/src/simulator-results.ts`, verified): `success→AUTHORIZED/PASSED`; `422 PROVIDER_ERROR→DECLINED/PASSED`; `422 other→REJECTED/PASSED`; `502 TIMEOUT_UNKNOWN→UNKNOWN/PASSED`; `401/403/409→UNKNOWN/FAILED`. Prior "inconsistent AUTHORIZED/DECLINED" reports are **resolved in current code** — single mapper, no ad-hoc strings.

## 5. Auth, RBAC, tenant isolation (verified)

- Bearer `API_SHARED_TOKEN`=operator / `API_ADMIN_TOKEN`=admin, `hmac.compare_digest` (`auth.py:25-37`). No tokens configured → `dev-caller` bypass **local only** (`auth.py:41-43`); must never reach shared/prod.
- `require_auth` / `require_role("admin")` server-enforced; cancel/refund/dispute/execute admin-only; admin implies operator.
- PDP (`pdp/`): default-deny, bundle `2026.11.02-v1`, 23-action matrix; `needs_intent`+`step_up` (confirm+reason+Idempotency-Key) for cancel/refund.
- Tenant (`auth.py:76-102`): `TENANT_FOR_{SHARED,ADMIN}_TOKEN` set → tenant DERIVED from token, `X-Tenant-Id` ignored; unset → header accepted (local-dev only). All `db.*(…,tenant)` scoped; audit chains per-tenant (`GENESIS` per tenant).
- Institutional maker-checker: maker≠checker incl. credential-hash alt-account resistance, quorum 1 (2 if ≥50000 minor), `STRICT=1` requires approved+unexpired+amount-bound intent; binding `approved→consumed` atomic conditional UPDATE.
- Frontend session (`session.tsx`): token in `useState` only, never `localStorage`; `NEXT_PUBLIC_API_TOKEN` dev bearer; role via `/me`.

## 6. Execution boundaries (verified)

| Boundary | Enforcement |
|---|---|
| No live money | `assert_sandbox()` on every provider call; Stripe only `sk_test_*` (`payments.py:111-114`); EVM never signs |
| No card data | No PAN/CVV/PIN/seed fields exist in schemas (`FiatCreateIn`, `EvmSubmitIn`); provider-hosted collection only (clientSecret for provider SDK) |
| Webhook trust | `verify_stripe_webhook` HMAC-SHA256 `{t}.{body}`, 300 s tolerance, `compare_digest`, JSON check, dedupe `stripe:{event.id}` + `tx_by_provider_ref` (`payments.py:177-198`) |
| Idempotency | `Idempotency-Key` header; key `{tenant}:{route}:{key‖sha256(body)}` (`api.py:560-562`), 409 on payload mismatch; Stripe `hybridpay:{instructionId}`; binding single-use |
| AI never moves funds | `ai.py` advisory wrappers only; `test` asserts AI modules never import `payments.py` |

## 7. CORS, fallback, preflight — prior issues re-verified

- **Modal backend: FIXED/OK.** `CORSMiddleware allow_origins=config.ALLOWED_ORIGINS` (default `localhost:3000,3001`), `allow_credentials=False`, `methods=[GET,POST]`, `headers=[Authorization,Content-Type,X-Tenant-Id,Idempotency-Key]` (`api.py:202-208`, `config.py:20-22`). Explicit allowlist via `ALLOWED_ORIGINS` env; preflight `OPTIONS` handled by middleware (methods cover all used verbs; no PUT/PATCH/DELETE routes exist to be blocked).
- **NestJS: OPEN — finding.** `app.enableCors()` with no origin allowlist (`apps/api/src/main.ts:7`). Permissive cross-origin on the Postgres system-of-record API. Sandbox-only impact today, must be tightened before any shared deployment.
- **Local simulation fallback: SAFE by design.** SDK throws `503 Backend unreachable` on fetch failure (`packages/sdk/src/index.ts:122`); simulator `mode: backend|local` radio defaults to backend with no silent switch; `localDemoResult()` only on explicit local mode, labeled `LOCAL_SIMULATION`; AI panel fallback is text guidance flagged `validated:false`. No evidence of unintended fallback in current code.

## 8. AI + prompt-injection surface (verified)

- Sole model egress `meta_client.py`: `POST {BASE}/chat/completions` (`muse-spark-1.3`, temp 0, max 800, json_object), 15 s timeout, 2 retries on 429/5xx, per-tenant 20/min, pydantic schema gate, `tenant_hash()` in logs only.
- Guards: `scrub_payload()` (PAN-runs, `sk/pk/rk_*`, BTC addresses, password/secret/seed/mnemonic/private-key, CVV, 4000 ch cap), injection screening, default-deny tool policy, allowlisted read-only tools, execution-time tool re-auth, kill-switch (`ai_guardrails/control.py`, DB-backed, per-feature flags, circuit breaker, dual-control re-enable).
- Prompt content is tenant transaction/agreement data; responses validated, never executed as actions.

## 9. Logging, secrets, data (verified without reading secrets)

- Logging `logging_util.py`: `_redact` pan/cvv/secret/api_key/password/seed/private_key/token; JSON `log_event`; meta logs sizes/latency/tokens only.
- Secrets: env + Modal Secret `hybridpay-test` (`config.py`, `app.py`); `.env` gitignored + untracked (verified). Browser env only `NEXT_PUBLIC_*` (no secrets; SDK comment `index.ts:38`).
- Data: SQLite local / Modal Volume / Postgres via `DATABASE_URL`; migrations versioned; stores refs/states/minor-amounts/tenant-ids; no PAN/CVV/seeds stored by design.
- Third parties: Stripe TEST (EU/BG Connect, EUR), BTCPay regtest (`bcrt1` only), Sepolia public RPC + Etherscan + faucets, Meta Model API (US cloud, scrubbed prompts), Modal hosting (US infra). No SCC/DPA evidenced — legal review item.

## 10. Tests, CI, SBOM status

- Backend `pytest modal_backend/` (30 files); frontend `pnpm build/test` (turbo 9/9, 11/11 per README — **NOT re-run in this phase**); e2e/integration/property under `tests/`.
- No `.github/` CI found — manual gates only. No SBOM generation found. Dependency scan **not yet run** (Phase 6).
- Prior reports (`SECURITY_AUDIT.md`, `GUARDRAIL_TEST_REPORT.md`, `SECURITY_INTEGRATION_AUDIT.md`, `REMAINING_RISKS.md`) treated as claims to re-verify, not evidence.

## 11. Known residual risks (to be ranked in Phase 3)

1. NestJS open CORS (`main.ts:7`).
2. `_idem_key` fallback hash uses `str(body)` — field-order/format fragile; explicit header keys unaffected.
3. `dev-caller` bypass + header-tenant trust when no tokens configured — local-dev only by design, must be deployment-gated.
4. SQLite single-conn + audit `last-hash read+insert` race; binding consume relies on conditional UPDATE rowcount (verify under concurrency).
5. `store.tx_get` tenant scoping relies on caller check at `api.py:635` — keep/verify.
6. EVM `evm_by_tx_hash` tenant-scoped — cross-tenant same-hash replay not detected (wallet-signed hashes are globally unique in practice; note).
7. Frontend `DEV_TOKEN` bake-in, `TxTable isAdmin=false` hardcode, `StatusTimeline` linearization, pagination `total` trust — UX/integrity notes, not fund-movement paths.

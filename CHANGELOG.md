# Changelog

## Unreleased (local only — NOT deployed; deploy needs explicit approval)
- Bank/exchange integration package: `GET /ready` readiness probe (migrations + store,
  load-balancer friendly; SDK `ready()`; probe step), `docs/bank-integration-guide.md`
  (iframe/headless/white-label patterns, auth + tenant binding, core-banking and exchange
  mappings, webhook receiver sketch, testing checklist, go-live gates),
  `docs/white-label-embed.md` (`?embed=1` chrome-less mode, `?tenant=` prefill,
  `NEXT_PUBLIC_BRAND_*`, palette overrides, print/a11y guarantees).
- Professional workspace redesign: shared `src/components/workspace.tsx` (WorkspaceHeader
  + status strip, icon SectionNav, KPI cards, SectionCards, StatusTimeline, AccessGate),
  `src/brand.ts` white-label config, embed mode in `Shell`, institutional hero band + KPI
  system + timeline/detail-grid/print CSS. Banking Workspace: 8 icon sections incl. new
  **Approvals** view (list/detail/step-up approve wired to backend intents); Operations
  money actions now create + approve a backend intent before executing; Admin adds AI
  kill-switch, audit-chain verification, readiness. Personal Workspace: same header/nav/
  card system, stepped Send wizard with progress rail, status badges in history.
- OpenAPI snapshot 53 paths; SDK already covered new methods; probe covers `/ready`.
- Tests: backend 101 passed / 4 skipped; SDK 14; terminal vitest (a11y contract kept green).
- AI Guardrails framework (`modal_backend/ai_guardrails/`): deterministic default-deny
  policy engine, read-only allowlisted tools, prompt-injection/role-spoof screening,
  sensitive-data redaction, output schema validation, per-tenant rate limits,
  tamper-evident AI audit log, emergency kill-switch (`POST /api/admin/ai/kill-switch`,
  503 AI-only blast radius — payments unaffected). Policy docs: `AI_SECURITY_POLICY.md`,
  `AI_TOOL_PERMISSIONS.md`, `AI_RED_TEAM_TESTS.md`, `ai_guardrails/README.md`.
- Institutional/human guardrails (`modal_backend/institutional.py` + migration
  `004_guardrails.sql`): RBAC/ABAC default-deny, maker-checker intents, multi-party
  quorum for high-risk amounts, no self-approval (incl. same-credential alt accounts),
  step-up confirmation, time-limited purpose-bound JIT elevation, emergency access with
  mandatory independent review, tenant-scoped tamper-evident security audit
  (`/api/admin/audit`), strict mode (`INSTITUTIONAL_STRICT=1`) that fails closed
  direct money calls without an approved intent.
- Bug fixes: test auth helpers now set both shared+admin tokens (6 failures fixed);
  removed double AI usage counting in `analyze_contract`; fixed persist test to reset
  `_sqlite_conn`; confined static server to `SITE_ROOT` (path-traversal guard);
  fixed `004_guardrails.sql` comment-semicolon migration bug; corrected OTel image to
  `otel/opentelemetry-collector-contrib:0.104.0`; per-tenant audit hash chains.
- API +12 paths (52 in OpenAPI snapshot): `/api/ai/policy`, `/api/ai/decision`,
  `/api/admin/ai/*`, `/api/approvals/intents*`, `/api/admin/elevation|grants|emergency*`,
  `/api/admin/audit`; SDK + probe extended. AI assistant screens injections at the
  boundary; fraud responses carry a deterministic `policyDecision` gate.
- Tests: backend 101 passed / 4 skipped (35 new guardrail/red-team tests), SDK 14,
  node property+integration 4/4 (explicit files). Nothing deployed.
- English-only UI (all pages default `en`, toggles removed, `<html lang="en">`).
- Banking Ops/Personal History pagination UI (Prev/Next + totals); server CSV download; reconcile sweep button.
- Send wizard inline field errors; EvmPanel migrated to design-system primitives with validation.
- Backend: idempotent cancel/refund (`Idempotency-Key`), `POST /api/reconcile/runs`, `GET /api/dashboard/export?format=csv`, `POST /api/webhooks/stripe/test`, per-tenant AI usage, `GET /api/admin/overview` (admin-only, no secret echo) + Admin UI wiring.
- OpenAPI snapshot 40 paths; `probe_live.py` 46 checks; SDK `adminOverview/reconcileRun/dashboardExportCsv/webhookTest`.
- Tests: backend 66 passed / 4 skipped (opt-in live), SDK 14, terminal 22 (incl. 11 static a11y-contract checks), `pnpm build` 9/9, full `pnpm test` 11/11.
- In-process load probe (`test_load.py`): p95 3.6–8.2ms across hot paths (TestClient, seeded 200 fiat/50 evm/20 agreements; NOT network latency).
- Docs: `docs/modal-deploy-checklist.md` refreshed (counts, crash-loop guards, staging tenant binding §3b); audit reports updated.

## 2026-10-31 — Permanent deploy (approved)
- Backend: `modal deploy modal_backend/app.py` → stable public URL (health verified OFF/sandbox).
- Frontend: `modal deploy modal_frontend.py` → stable public URL (all pages 200, proxy 201/200 verified).
- Rollback documented in test report. No live credentials; no paid resources (CPU-only, min_containers=0).

## 2026-10-31 — Banking + Personal workspaces (full modules) + crash-loop fixes
- Crash-loop root causes with log evidence: blocking web_server fn → Popen; relative
  import on cold start → bake package + absolute import (`test_modal_mount.py` guards it);
  `modal-function-call-id` forwarded both ways → allowlist/strip. Kill-restart
  KeyboardInterrupts identified as expected shutdown artifacts.
- Banking (6 modules, admin-gated money actions): overview/alerts/AI usage, ops with
  detail + maker-checker, contracts + audit, risk queue + escalate-via-dispute, admin
  (RBAC matrix, users/seats gap flagged, API/security), analytics (real-data charts + CSV).
- Personal (7 screens): dashboard, 5-step send wizard with review+confirm, receive
  (shareable Sepolia request), programmable wizard (plain language → DSL), assistant,
  history (search/detail/JSON receipt), settings (session-only, no seed requests).
- No invented metrics/balances; AI advisory-only; tenant isolation enforced.

## 2026-10-31 — Design system + Banking/Personal workspaces
- `FRONTEND_IMPLEMENTATION_PLAN.md`: audit (36 Modal + 12 Nest endpoints), feature matrix,
  architecture, token/component specs, auth/RBAC, missing-backend list, P0-P2.
- Stack: Tailwind v3 + CSS-variable tokens (light/dark) + shadcn-style ui + Lucide +
  next-themes + recharts; `/design-system` showcase with a11y contract (WCAG 2.2 AA target).
- `/banking` (admin-gated: overview charts, tx table + ConfirmDialog-gated cancel/refund,
  agreements, risk, assistant) + `/personal` (pay, activity, assistant). Existing routes untouched.
- Tests: terminal 11 (new `design-system.test.ts`). Full suite green. No deploy, no live funds.

## 2026-10-31 — User-facing app + persistent data layer
- Unified Dashboard tab (default): summary cards + filterable combined history
  (`/api/dashboard/summary|recent`, operator-readable, tenant-scoped).
- Auth: operator/admin bearer roles, server-enforced (admin-only: fiat cancel/refund,
  agreement execute/cancel/dispute) + `/api/me` role badge; memory-only session token
  + logout in UI; no secrets or payment creds in browser/DB.
- Durability: Postgres via `DATABASE_URL` (psycopg2) or SQLite on Modal Volume
  `/mnt/data` (auto-default; never ephemeral FS); versioned migrations
  (`modal_backend/migrations/001-003`, `schema_migrations`, idempotent `migrate()`);
  indexes for tenant/state/provider paths; fail-fast validation.
- Frontend a11y/responsive: viewport, responsive CSS, focus-visible, aria-live,
  labelled filters, keyboard-operable tabs; improved UI preserved (no rewrite).
- Tests: `test_dashboard_auth.py` (RBAC matrix, /me, summary/recent filters, isolation),
  `test_migrations.py` (fresh apply, idempotent rerun, indexes, validation).
- Docs: `docs/database.md` (env, Volume, Postgres, migrations, backups).
- Full suite green (see test report). No deploy, no live funds.

## 2026-10-31 — Meta Muse Spark AI completion
- New endpoints: `/api/ai/explain-crypto`, `/api/ai/explain-state`, `/api/ai/assistant`,
  `/api/ai/usage` (counters: calls/fallbacks/tokens); explicit NOT-certified-fraud disclaimer;
  usage recorded on every call + fallback.
- New: `AssistantPanel` (chat + validated/stub badges + usage), state explainer in Agreements,
  crypto explainer in EVM tab; SDK `aiAssistant/aiExplainCrypto/aiExplainState/aiUsage`.
- Tests: `test_ai_complete.py` 6/1 skipped, SDK 8, terminal 6. Docs: `docs/ai-integration.md`.
- Full suite green. No deploy, no live calls, no key in repo.

## 2026-10-31 — EVM Sepolia workflow + programmable fiat contracts
- New: `modal_backend/evm.py` + `/api/payments/evm/*` (request/submit/receipt/replace/list;
  Sepolia-only chain guard, receipt + confirmations via JSON-RPC, explorer links, chain != settlement).
- New: `modal_backend/programmable.py` + `/api/contracts/programmable/*` (draft/active/
  conditions_pending/eligible_for_execution/completed/canceled/expired/disputed; 4 condition
  types; role-gated transitions; hash-chained audit; execute = eligibility AND human executor
  AND sandbox fiat provider; escrow/custody claims rejected).
- Frontend: viem wallet (sign-in-wallet, keys never leave), EVM Sepolia tab, Agreements tab.
- Tests: `test_evm_payments.py` 6/1 skipped, `test_programmable_contracts.py` 5/5, SDK 6, terminal 5.
- Docs: `docs/evm-sepolia.md` (setup/faucet/verification), `docs/programmable-contracts.md`.
- Results: `pnpm build` 9/9, `pnpm test` 11/11, `pytest modal_backend/` all green. No deploy, no live funds.
- Verified `modal serve modal_backend/app.py` starts clean (no traceback); hardened imports/config; secret `hybridpay-test` present.
- New: `modal_backend/payments.py` (provider ABC + mock + Stripe TEST), `modal_backend/db.py` (SQLite durability),
  7 fiat endpoints + verified Stripe webhook in `modal_backend/api.py` (legacy `simulate` kept).
- New tests: `modal_backend/test_fiat_payments.py` (7/7: lifecycle, idempotency/409, gating, webhook, AI guard, durability).
- SDK: fiat create/confirm/retrieve/list/cancel/refund; terminal fiat tab uses authoritative confirm flow.
- Docs: `README.md` rewritten, `IMPLEMENTATION_STATUS.md`, `docs/fiat-sandbox.md`, `docs/modal-deploy-checklist.md`,
  `docs/live-mode.md`, `docs/real-money-roadmap.md`, `CONTRIBUTING.md`, `SECURITY.md`.
- Results: `pnpm build` 9/9, `pnpm test` 11/11, `pytest modal_backend/` 25 passed / 1 skipped. No deploy performed.

## 2026-10-31 — Terminal↔Modal connection, LIVE guardrails, simulator
- Typed `ModalBackendClient`, env-based URLs, dashboard forms + states, idempotency, demo E2E, simulator, deploy checklist.

## 2026-10-31 — Builds green + missing tests
- Fixed terminal/worker/adapters builds (9/9), added worker entry, API modules, property/integration/SDK tests.

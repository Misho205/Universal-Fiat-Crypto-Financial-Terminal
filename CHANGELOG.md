# Changelog

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

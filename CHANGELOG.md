# Changelog

## 2026-10-31 — Modal startup verified + fiat sandbox E2E + project docs
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

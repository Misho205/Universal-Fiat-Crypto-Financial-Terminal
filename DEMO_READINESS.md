# Demo Readiness — Universal Hybrid Payment Terminal
> **Update 2026-11-01 (follow-up):** All workspaces are now English-only (default locale `en`, toggles removed). New demo actions: Ops “Run reconcile sweep” + “Download server CSV”, History Prev/Next pagination, EVM panel with validated inputs, Send wizard with inline errors.

Date: 2026-11-01. **Sandbox/testnet demo ONLY. Not production-ready. Do not move real money.**

## 1. One-system access (single deployment, all dashboards)

All workspaces ship in **one Next.js app** (`apps/terminal`) behind one nav (`src/components/shell.tsx`):

- Terminal (merchant home, 9 tabs): `/`
- **Banking Workspace** (admin-gated, 6 modules + assistant): `/banking`
- **Personal Workspace** (7 screens): `/personal`
- Simulator (5 trial scenarios): `/simulator`
- Design system showcase + a11y contract: `/design-system`

### Stable public demo URLs (last approved deploy `9b5971b`)

- Backend (Modal FastAPI, sandbox): `https://michail-tsvetanov--hybridpay-sandbox-fastapi-app.us-east.modal.run`
  - Health: append `/health` → expect `{"ok":true,"liveMode":"OFF","sandbox":true}`
- Frontend (Modal static + same-origin `/api` proxy): `https://michail-tsvetanov--hybridpay-terminal-serve.us-east.modal.run`
  - Banking: append `/banking`
  - Personal: append `/personal`
  - Simulator: append `/simulator`

> Note: code changed after that deploy (tenant binding, SDK validation, pagination, this audit's two fixes). The links above serve the **last deployed** build, not today's tree. Redeploy is an operator step (`docs/modal-deploy-checklist.md`) and was NOT run in this audit. For the current tree, run locally (below) — behavior is otherwise identical (all tests green).

### Local (current tree)

1. `cp .env.example .env` (keep `LIVE_MODE=false`; only `*_TEST` keys)
2. `pnpm install && pnpm build` (expect 9/9)
3. Backend: `API_SHARED_TOKEN=dev-shared-token API_ADMIN_TOKEN=dev-admin-token uvicorn modal_backend.api:app --port 8000`
4. Frontend: `pnpm --filter @hybridpay/terminal dev` → `http://localhost:3000`
5. Open `http://localhost:3000/banking` and `http://localhost:3000/personal`

## 2. Demo script (5 minutes, both workspaces)

1. **Personal → Send** (fiat sandbox): Recipient → Fiat → 1000 minor EUR → Review (check sandbox/testnet + no-real-money note) → Confirm → Status `pending/succeeded` + paymentId.
2. **Personal → Receive**: enter Sepolia `0x…` → Create request → share paymentId → Track (live polling, explorer link after wallet signature).
3. **Personal → Programmable**: amount + party + condition → human preview → Create & activate → Check status.
4. **Banking → Overview/Ops**: verify counts update; search/filter the new payment; open detail (provider `mock`, `Sandbox` badge, idempotency prefix); maker-checker Cancel/Refund as admin (distinct maker+checker+reason).
5. **Assistant (either)**: ask "why is my payment pending?" → validated/stub answer with advisory notice.
6. **Simulator**: run `fiat-ok` / `crypto-wrong` / `contract-bad` trials.

## 3. Past-prompt completion declaration

- **Integration prompt (12/12, 1 partial)**: all wired and tested; partial = idempotency on cancel/refund (backend accepts no key — documented gap, UI guards double-submit).
- **Personal prompt (7/7 screens)**: Dashboard, Send, Receive, Programmable, Assistant, History, Settings — all present, plain-language, sandbox-labeled, no seed requests, no fake balances, no real money.
- **Banking prompt (6/6 modules)**: Overview, Payment Operations, Programmable Contracts, Risk & Compliance, Administration, Analytics — all present, tenant-isolated, maker-checker, sandbox-labeled, advisory-only AI, no invented metrics, no credential exposure.
- **Single system + links**: one app, one nav, links above. ✅

## 4. What is explicitly NOT ready

- Production payments, mainnet, live Stripe/BTCPay, custody, KYC/KYB, fiscal receipts, central-bank claims, audited contracts, pentest, DPA, SLAs. See `docs/real-money-roadmap.md`, `docs/live-mode.md` (fail-closed), `SECURITY_REVIEW.md §10`.
- Staging hardening before any shared non-local demo: set `TENANT_FOR_SHARED_TOKEN` / `TENANT_FOR_ADMIN_TOKEN`, rotate `API_*_TOKEN`, set `ALLOWED_ORIGINS` to the exact frontend origin, keep `LIVE_MODE=false`.

## 5. Operator checklist before showing the demo

- [ ] `/health` reports `liveMode: OFF`, `sandbox: true`
- [ ] Public URLs return 200 on `/`, `/banking`, `/personal`, `/simulator`
- [ ] One fiat sandbox payment creates + confirms (201 → decided state)
- [ ] Admin token required for cancel/refund/dispute/execute (operator gets 403)
- [ ] AI answers carry `advisoryOnly` + validated/stub tag
- [ ] No `MODEL_API_KEY`/provider secret in browser bundle (grep clean)
- [ ] Rollback plan known (`docs/modal-deploy-checklist.md` + `docs/test-report.md`)

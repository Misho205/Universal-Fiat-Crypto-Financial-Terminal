# UX Audit — Universal Hybrid Payment Terminal
> **Update 2026-11-01 (follow-up):** UI is now English-only (all pages default to `en`, language toggles removed, `<html lang="en">`). Pagination controls added (Banking Ops + Personal History: Prev/Next + record counts). Send wizard has inline field errors. EvmPanel migrated to design-system primitives (Card/Button/Alert/Field, StatusBadge, SandboxBadge) with input validation. Backend gaps closed: idempotent cancel/refund, `POST /api/reconcile/runs`, server CSV export, webhook test-trigger, per-tenant AI usage. Previous "remaining issues" below that are now fixed are marked [FIXED].


Date: 2026-11-01 (UTC). Scope: `apps/terminal` (Next.js 15) — Banking (`/banking`) + Personal (`/personal`) + Terminal (`/`) + Simulator (`/simulator`) + Design system (`/design-system`). Backend: `modal_backend` FastAPI (36 paths). Method: code inspection + `pnpm build` (9/9 green) + `pytest modal_backend/` (59 passed) + local live probe (`uvicorn` + `curl`: health OFF/sandbox, `/api/me` operator, fiat create 201 pending/mock).

Policy: no invented results. Every claim cites a file or an executed command. Sandbox/testnet only — no production readiness claimed (see DEMO_READINESS.md).

## 1. Navigation (all routes work)

- Routes built successfully (verified `pnpm build` output): `/` (15.5 kB), `/banking` (11.6 kB), `/personal` (8.05 kB), `/simulator` (2.37 kB), `/design-system` (6.71 kB). All static-prerendered, no build errors.
- Global nav: `src/components/shell.tsx:8-14,34-47` — Terminal / Banking (ADMIN badge) / Personal / Design system / Simulator. `aria-current="page"`, `aria-label` on nav, skip-link `href="#main"` (`shell.tsx:20-22`), `main#main`.
- Banking views (`app/banking/page.tsx:22`): overview | ops | contracts | risk | admin | analytics | assistant — tab switching via `Tabs` component, state-driven, no route breakage.
- Personal tabs (`app/personal/page.tsx` ~7): dash / send / receive / program / assistant / history / settings — same pattern.
- Footer disclaimer on every page (`shell.tsx:50-51`): "HybridPay sandbox — no real money. Technical receipt is NOT a fiscal receipt." Header SANDBOX badge (`shell.tsx:28`).

## 2. Forms validate correctly

- SDK client-side guards (`packages/sdk/src/index.ts:55-72`): `assertMinorUnits` (integer minor-units string), `assertEvmAddress` (0x+40hex), `assertTxHash`, `assertChainId` (1 → MAINNET_REFUSED 422, else must be 11155111). Tested in `packages/sdk/test/sdk.test.ts:116-141` (13 tests pass).
- Fiat form (`src/components/fiat-pay-form.tsx:18`): regex `^\d+$` on amount, friendly BG/EN error, no junk over the wire.
- Send wizard (`app/personal/page.tsx:157-167`): fiat currency select from `currencies.ts`, amount `inputMode="numeric"`, crypto address placeholder `bcrt1… regtest only`; review step (`:168-173`) shows amount/currency/recipient/fees/network before confirm. Confirm button disabled while busy (`:178`).
- Programmable wizard (`:253-262`): builds valid DSL (`timeCondition`, `partyApproval`/`approvalThreshold`/`deliveryConfirmation`), human-readable preview (`humanTerms()`), create→activate flow.
- Receive (`:193-202`): EVM address input, creates tracked Sepolia request, shows paymentId/to/wei/explorerBase.
- **Defect fixed (this audit)**: `src/EvmPanel.tsx:35` used `BigInt(Math.round(parseFloat(eth)*1e18))` — float precision loss + throw on invalid input. Replaced with exact `ethToWei()` string parser (`/^\d+(\.\d{1,18})?$/`, null on invalid, friendly BG/EN message). Verified with node one-liner (0.001→1000000000000000, 19-decimals→null, abc→null).
- Remaining minor: Send wizard has no inline per-field errors before submit (relies on SDK throw → `out` message). Documented, not blocking for demo.

## 3. Responsive (mobile + desktop)

- Layout: `shell.tsx:24,34,49` — `max-w-6xl`, `overflow-x-auto` nav, `px-4 pb-16 pt-6`.
- Grids: banking overview `grid-cols-2 md:grid-cols-4` (`banking/page.tsx:112-114`), analytics `grid-cols-1 md:grid-cols-2` (`:435`), personal dash `grid-cols-1 md:grid-cols-3` (`personal/page.tsx:87`), settings `grid-cols-1 md:grid-cols-2` (`:389`). `flex-wrap` everywhere on action rows. Tables wrapped in `overflow-x-auto region` (`src/components/ui/table.tsx:6`).
- No horizontal-breakage found in code; physical device matrix not run (documented as remaining).

## 4. Keyboard navigation

- Tabs (`src/components/ui/tabs.tsx:16,21-22`): ArrowLeft/Right/Home/End, roving `tabIndex` (0 active / -1 rest), focus moves on change, `role=tablist/tab`, `aria-selected`.
- Dialog (`src/components/ui/dialog.tsx:14-18,24`): autofocus first button, Escape closes, focus restored to opener, `role=dialog aria-modal`.
- Tables (`table.tsx:6`): scroll region `tabIndex={0}` + `aria-label`. Charts have SR table fallback (`chart.tsx:10` + `tableId`).
- Inputs labeled via `Field` (`field.tsx:12-13`): `aria-invalid`, `aria-describedby` on error. Search/selects have `aria-label` (`personal/page.tsx:340,343`).

## 5. Accessibility (WCAG 2.2 AA targets, testable subset)

- Contrast: design tokens in `globals.css` (`--bg/surface/line/ink/muted/brand-*/ok|warn|danger|info`), status always color+label (`StatusBadge` has `aria-label="status: …"` + text, `badge.tsx:31-32`; dot is `aria-hidden`).
- Live regions: `aria-live=polite` on loading (`banking/page.tsx:231`, `EvmPanel` loading), `role=status` on results (`personal/page.tsx:174,230`), `role=alert` via `Alert danger` (`feedback.tsx`).
- `prefers-reduced-motion` disables animation (`globals.css`); focus-visible styled; `lang=bg` on layout; theme toggle has `aria-label` + `aria-pressed`.
- Not formally audited: full axe run, screen-reader pass, 200% zoom matrix — listed as remaining.

## 6. Sandbox/testnet labeling

Pervasive and correct. Header `SANDBOX` badge, footer fiscal disclaimer, `SandboxBadge` on every tx row (`tx-table.tsx:48`), provider chips (`mock`, `sepolia-rpc`, `deterministic-engine`), Sepolia banner (`EvmPanel.tsx:81-83`), fiat `(sandbox)` titles, crypto `(BTC regtest)` / `(Sepolia)` labels, review-step "Network: sandbox/testnet. No real money.", receipt JSON includes `sandbox:true`, analytics empty-state "Nothing is invented", perf card "only real counts … no invented latencies". No fictional balances found (grep: `Math.random` only in idempotency keys; numbers are form defaults/demo fixtures, never displayed as portfolio).

## 7. Backend integration (real responses)

- Local live probe (this audit): `GET /health` → `{"ok":true,"liveMode":"OFF","sandbox":true}`; `GET /api/me` → operator; `POST /api/payments/fiat` → 201 `pending/mock`. No mocks in UI path — SDK `fetch` hits real backend, errors surfaced via `friendlyError` + retryable flag.
- Contract: `modal_backend/openapi.snapshot.json` (36 paths) + `test_openapi_coverage.py` (every path in `probe_live.py` + typed SDK) + `probe_live.py` 42/42 live sweep (CI-gated). Pagination added this cycle (`limit/offset/state` on fiat/evm/agreement + `recent` offset) — backend + SDK + tests green.

## 8. Loading / error / empty states

- `Outcome idle|loading|ok|err` pattern (`EvmPanel`, `fiat-pay-form`, `AssistantPanel`); `Skeleton` cards (banking overview); `Alert info|ok|warn|danger`; `EmptyState` ("No results — make a payment…", "Review queue empty", "No data — create a sandbox payment…"); retry buttons (`polled.reset`, `live.reset`); polling stops on terminal states (`TERMINAL_STATES`), backoff 3s×1.5 max 15s, abort on unmount.

## 9. Transaction statuses

- Canonical states displayed verbatim from backend via `StatusBadge` + detail JSON: fiat `created/pending/succeeded/failed/canceled/refunded/unknown`; evm `requested/pending/confirmed/failed/expired/replaced`; agreements `draft/active/conditions_pending/eligible_for_execution/completed/canceled/expired/disputed`. Detail view shows provider, idempotency prefix, explorer link, confirmations `n/required`, `businessSettled:false` + settlement note (chain ≠ settlement). No frontend-invented success — confirm/receipt decides.

## 10. AI advisory labeling

- Backend: every AI response carries `advisoryOnly:true + validated + notice` (`api.py:177-180` and AI routes). Fraud carries NOT-certified disclaimer, fail-closed high. Frontend: `[validated|stub]` tags (`AssistantPanel.tsx:49`), `(advisory)` in Risk title, assistant context "institutional/operational", never calls money endpoints.

## 11. Role-based authorization

- Server-enforced: `require_admin` on fiat cancel/refund + agreement execute/cancel/dispute (`api.py:440,457,…`); 403 matrix tested (`test_dashboard_auth.py`); tenant derived from token when bound (`auth.py:require_tenant`, `test_tenant_binding.py`). UI mirrors: `isAdmin` hides admin workspace actions, banking shows "Full access requires admin token" banner for operators; money actions go through maker-checker dialog (distinct maker+checker+reason, `banking-shared.tsx:75,90-91`) — UI-enforced until backend intents endpoint exists (honestly labeled). Row-level Cancel/Refund in `TxTable` intentionally disabled (`isAdmin={false}` in Ops) so all money flows through maker-checker — clarified with code comment this audit.
- **Gap fixed (wording)**: maker-checker previously claimed idempotency-key recording but never sent it; cancel/refund endpoints accept no `Idempotency-Key`. Comment corrected; double-submit guarded by disabling the button in flight. Backend idempotent cancel/refund remains a documented gap.

## 12. Fixes applied in this audit

1. `EvmPanel.ethToWei` exact conversion + invalid-input message (was float `parseFloat` + throw).
2. Banking `makerApprove` comment corrected (no false idempotency claim); `TxTable isAdmin={false}` intent documented.
3. SDK coverage hints relaxed for template-literal list URLs (`test_openapi_coverage.py`) after pagination change.

## 13. Remaining issues (not fixed — see DEMO_READINESS.md)

- Banking Ops/Analytics + Personal History use fixed `limit` (100/50) with no offset UI (backend supports it; UI pagination controls missing).
- `EvmPanel` still uses inline styles/plain buttons instead of design-system primitives (functional, weaker consistency).
- Send wizard lacks inline field-level errors; fiat requests are not a backend primitive (honestly messaged in Receive panel).
- Backend gaps (plan §7): user/seat management, Modal `POST /api/reconcile/runs`, server-side CSV, per-tenant AI history, webhook test-trigger, idempotent cancel/refund — UI labels "not available" instead of faking.
- No formal axe/screen-reader/device-matrix run; no load/perf measurement (p95 explicitly marked unmeasured).

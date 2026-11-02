# FRONTEND_IMPLEMENTATION_PLAN.md — Banking + Personal workspaces

Status: analysis complete 2026-10-31. No code modified by this document.
Stack decision: **keep Next.js 15 + TypeScript** (existing, working, static-exportable),
**add Tailwind CSS v3 + shadcn-style components + Lucide + next-themes + recharts**.
Rationale: existing UI is functional but styled with ad-hoc inline styles; Tailwind +
design tokens give the institutional consistency required, without replacing any
working business logic, SDK method, or backend endpoint.

## 1. Existing frontend inventory (`apps/terminal`)
- Framework: Next.js 15 App Router, React 18, TypeScript, `viem` (wallet). No Tailwind,
  no component library — `globals.css` (~40 lines) + inline `style={}` objects.
- Routes: `/` (9 tabs: dashboard, order, fiat, crypto, evm, contract, agreements,
  assistant, status), `/simulator` (5 trial scenarios). All client components.
- Panels (`src/`): `DashboardPanel`, `EvmPanel`, `AgreementsPanel`, `AssistantPanel`
  + `evm.ts` (EIP-1193/viem helpers), `currencies.ts` (12 fiat + 3 crypto assets),
  `i18n.ts` (28 keys, BG/EN parity enforced by test).
- Auth: bearer token in React state only (never localStorage), role badge via
  `GET /api/me` (operator/admin/anonymous), admin-only buttons hidden without admin —
  backend still enforces (tested 403 matrix).
- API integration: `@hybridpay/sdk` (`HybridPayClient` for Nest v1 API +
  `ModalBackendClient` with 30+ typed methods), env-based base URLs
  (`NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_MODAL_API_URL`), static export with
  same-origin `/api` proxy (`modal_site_server.py`).

## 2. Backend surface (verified live 2026-10-31, 36 Modal paths)
Fiat: `POST /api/payments/fiat` → `POST .../confirm` → `GET .../{id}` → `GET /api/payments/fiat`
→ `POST .../cancel|refund` (admin) + legacy `simulate`, `GET /api/transactions/{id}`,
`POST /api/webhooks/stripe` (HMAC, admin service token). Crypto: BTC regtest `simulate`;
EVM Sepolia: `request/submit/status/replace/list` (chainId 11155111 enforced, mainnet refused).
Contracts: `validate` + programmable `create/get/activate/approve/evidence/execute/cancel/dispute/list`
(admin-gated execute/cancel/dispute). AI (advisory-only, validated, stub fallback):
`explain-transaction|explain-crypto|explain-state|fraud-signals|routing-recommendation|
contract-analysis|assistant` + `GET /api/ai/usage`. Platform: `/health`, `/api/me`,
`/api/dashboard/summary|recent` (tenant-scoped). Nest v1 API: orders, agreements,
eligible-methods, quotes, instructions (+refund), evidence, reconcile, devices, checkout tokens.

## 3. Feature matrix
| Area | Status |
|---|---|
| Order/QR, fiat create→confirm, crypto simulate, EVM wallet flow, contract validate | Implemented + tested (mocked E2E) |
| Programmable agreements lifecycle, AI panels, dashboard history/filters, simulator | Implemented + tested |
| Provider execution | **Simulated** (mock default; Stripe TEST only with `sk_test_*`; BTCPay regtest needs docker profile; Sepolia RPC optional) — UI labels this everywhere |
| Live money, mainnet, custody, fiscal receipts | Intentionally absent (fail-closed) |
| Pagination on fiat/evm/agreement lists (fixed limit 50), server-side date ranges, CSV export, reconcile trigger in Modal backend, per-tenant AI usage history, webhook test-trigger, user/tenant management | **Missing** (see §7) |
| Visual polish, dark theme, charts, workspace separation | Missing — this plan |

## 4. Target architecture
```
apps/terminal/
  app/
    layout.tsx                # theme provider, viewport, a11y skip-link
    globals.css               # Tailwind + CSS-variable design tokens (light/dark)
    page.tsx                  # router hub: workspace switcher (keeps all 9 existing tabs)
    banking/page.tsx          # Banking Workspace (admin-gated)
    personal/page.tsx         # Personal Workspace (operator)
    design-system/page.tsx    # component showcase + a11y notes
    simulator/page.tsx        # unchanged trial scenarios
  src/
    components/ui/*           # shadcn-style: button, card, badge, table, dialog,
                              # input, select, textarea, alert, skeleton, tabs,
                              # status-badge, money, empty-state, confirm-dialog, chart
    components/{banking,personal,shared}/*
    tokens.ts                 # TS mirror of CSS-variable tokens
    lib/{format.ts,cn.ts}     # money/date formatters, classnames
  tailwind.config.js + postcss.config.js (darkMode: 'class')
```
Dependencies to add: `tailwindcss@3`, `postcss`, `autoprefixer`, `clsx`,
`tailwind-merge`, `class-variance-authority`, `lucide-react`, `next-themes`, `recharts`.

## 5. Workspaces
**Banking Workspace** (`/banking`, requires `admin` role — enforced by `require_admin`
on cancel/refund/execute/dispute endpoints; UI hides the workspace otherwise):
Overview (volume by state chart + KPI cards), Transactions (filterable table, confirm/cancel/refund actions),
Agreements pipeline (state board, approve/evidence/execute), Approvals queue,
Risk (fraud indicators, NOT certified — disclaimer), Audit (hash-chained history viewer),
AI assistant (institutional context). Acceptance: every money action shows sandbox badge,
409/403 states render friendly copy, no action fires without confirmation dialog.
**Personal Workspace** (`/personal`, `operator` role): Pay (fiat/crypto/EVM cards),
My activity (tenant history + explorer links), QR checkout (existing flow),
Agreements I participate in (approve only), Assistant. Acceptance: 3-click payment,
plain-language amounts, no admin controls visible.

## 6. Design tokens (single source: CSS variables + `tokens.ts`)
Colors (light/dark pairs): `--bg,--surface,--border,--ink,--muted,--brand-* (indigo scale, AAA on surface),
--success/--warning/--danger/--info` with AA contrast on both themes. Typography: system stack,
scale 12/14/16/20/24/32, tabular-nums for money. Spacing 4-pt scale. Borders: 8/12/16 radius.
Elevation: 3 restrained shadow levels (light only; dark uses borders). Motion: 150 ms ease,
`prefers-reduced-motion` disables. Status → color+label map shared by badges and charts.

## 7. Missing backend functionality required by the UI (to be added only if approved)
1. Pagination (`?limit&offset|cursor`) on fiat/evm/agreement lists — currently fixed 50
   (dashboard `recent` has `limit`; lists do not). Priority P1.
2. Server-side date-range + state filters on lists (client filters don't scale). P1.
3. CSV export endpoint for statements (banks). P2.
4. `POST /api/reconcile/runs` in Modal backend (today Nest-only) for the banking
   Reconcile view. P2.
5. Persistent per-tenant AI usage history (today in-memory counters only). P2.
6. Sandbox webhook test-trigger (signed sample event) for demoing verification. P2.
None of these is implemented by this plan; the UI works fully without them.

## 8. Auth / tenant / RBAC requirements (already server-enforced; UI mirrors)
- Bearer in memory only, logout clears; role from `/api/me`; tenant header per request;
  admin-only UI (banking workspace, cancel/refund/execute/dispute buttons) hidden for
  operators; every gate re-checked server-side (403 matrix tested). No secrets, no keys,
  no card data in the browser; no payment credentials stored anywhere.

## 9. Priorities + acceptance criteria
- P0: tokens + Tailwind + dark/light theme, ui primitives, sidebar/topnav, status/money
  components, banking + personal shells reusing existing panels, showcase page,
  `pnpm build` + `vitest` green, pushed. WCAG 2.2 AA: focus-visible, aria labels/live,
  keyboard-operable tabs/dialogs, 4.5:1 text contrast, non-color status cues.
- P1: charts with data-table fallbacks, confirm dialogs on all money actions,
  empty/error/skeleton states everywhere, keyboard shortcuts.
- P2: backend gaps from §7 (needs approval), e2e against live dev backend, perf pass.

## 10. Session 2026-11-02 — professional redesign + integration package (implemented)
- Shared workspace system `src/components/workspace.tsx`: `WorkspaceHeader` (eyebrow/title/
  status strip), icon `SectionNav`, `KpiCard`/`KpiGrid`, `SectionCard`, `StatusTimeline`,
  `AccessGate`, `TenantRoleStrip`. Banking: 8 sections incl. **Approvals** (backend intents
  list/detail/step-up approve); Operations executes via intent-create → intent-approve →
  money call. Personal: same system, stepped Send wizard with progress rail.
- `src/brand.ts` (`NEXT_PUBLIC_BRAND_*`), `Shell` embed mode (`?embed=1`), tenant prefill
  (`?tenant=`), print CSS, refined institutional palette. All a11y-contract tests kept green
  (tabs/dialog/badge/field/table/chart primitives untouched).
- Integration: `GET /ready`, `docs/bank-integration-guide.md`, `docs/white-label-embed.md`.

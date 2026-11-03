# Personal Workspace Audit — backend integration repair (sandbox only)

Date: 2026-11-03. Scope: Personal (`apps/terminal/app/personal/page.tsx`),
simulator (`apps/terminal/app/simulator/page.tsx`), Banking regression check.
No Modal Secrets touched, no deploys, no live payments, no real transactions.

## 1. Root cause analysis

**R1 — Personal had no visible sign-in; every panel 401'd on load.**
Personal's only sign-in lived inside the Settings tab, while Dashboard
auto-calls `dashboardSummary` and History auto-searches on mount
(`personal/page.tsx`). With the page-local session unsigned, both fail with
401 and the page looks "multiply broken". Sessions are intentionally
page-local (`useSession` per page, memory-only) — signing in on Banking
does NOT sign in Personal/Private/simulator. Banking works because the
operator signed in there.

**R2 — Simulator hid backend answers behind the local fallback.**
Any thrown error (including backend 401/422/502 *responses*) fell into one
`catch` that rendered a "local simulation". Consequences observed:
"FAILED mock declined (local simulation)" even with a healthy backend
(the 422 `mock declined` IS the backend answer), and any backend error
(including unsigned 401) rendered as "backend unreachable".

**R3 — "Backend unreachable" is NOT a dead backend.**
Verified 2026-11-03 from this environment:
- `GET https://michail-tsvetanov--hybridpay-sandbox-fastapi-app.us-east.modal.run/health`
  → 200 `{"ok":true,"liveMode":"OFF","sandbox":true}`.
- `POST …/api/payments/fiat/simulate` without token → 401 `missing bearer token`
  (auth gate alive on the deployed backend).
- CORS preflight from the frontend origin → 200 with
  `access-control-allow-origin: https://michail-tsvetanov--hybridpay-terminal-serve.us-east.modal.run`
  (`ALLOWED_ORIGINS` correctly configured — no action needed).
- `modal app list`: `hybridpay-sandbox` and `hybridpay-terminal` both `deployed`
  since 2026-10-31.
- Deployed simulator chunk hash equals the source build chunk
  (`page-8f74d80a00123d19.js`) → frontend/backend versions compatible.
Remaining explanations for a browser-side "unreachable": cold start
(`min_containers=0`), local network/VPN/ad-blocker, or a malformed copied
token. The simulator now shows a live health indicator so the next
occurrence is diagnosable (see §5).

**R4 — Declined mock was mislabeled, not mis-executed.**
`fiat-fail` → backend 422 `mock declined` is the *expected* sandbox outcome;
it was displayed as a local/offline artifact. Fixed by labeling (§5).

## 2. Files changed (this repair)

- `apps/terminal/app/personal/page.tsx`
  - `PersonalSignIn` banner (banking-style `ws-gate` + `Sign in` button) shown
    while the page session has no token — same memory-only `useSession` flow.
  - `PersonalDash` errors now via `friendlyError` (was raw `Error.message`,
    leaking e.g. bare "missing bearer token" without guidance).
  - `ReceivePanel` default address `0x000…` → empty + `0x…` placeholder
    (zero-address requests are no longer one click away; SDK validates).
- `apps/terminal/app/simulator/page.tsx`
  - Backend *responses* (401/422/502/…) recorded as backend sandbox results
    (`simulated:false`); negative scenarios labeled `DECLINED-AS-EXPECTED`,
    `UNKNOWN-AS-EXPECTED (query-original)`, `REJECTED/INVALID-AS-EXPECTED`.
  - Local simulation only on genuine network failure (`fetch` threw) AND
    explicit opt-in via new "Local demo mode" checkbox (default off);
    otherwise a `BACKEND-UNREACHABLE` card with diagnostics is shown.
  - Live backend health indicator (`reachable · liveMode OFF · sandbox true`
    vs `UNREACHABLE · …`) fetched from public `/health` on load.
- Prior related (already in tree): `app/private/page.tsx` (new Private
  Workspace, banking-style sign-in), `shell.tsx` Private nav, `i18n.ts`
  `Sign in` label, `test_dashboard_auth.py` 401-gate test,
  `test/auth-headers.test.ts`, `modal_frontend.py`/`modal_site_server.py`
  doc fixes. Backend untouched by this repair.

## 3. API connectivity test results (live, read-only + unsigned probe)

| Check | Result |
|---|---|
| `GET /health` (backend) | 200, `liveMode OFF`, `sandbox true` ✅ |
| `POST /api/payments/fiat/simulate` unsigned | 401 `missing bearer token` ✅ (gate alive) |
| CORS preflight (frontend origin) | 200, correct allow-origin/headers ✅ |
| `modal app list` | both apps `deployed` ✅ |
| Deployed vs source frontend chunk | identical hash ✅ |
| `GET /simulator/` (frontend) | 200 ✅ |

## 4. Authentication test results

- Unsigned → 401, wrong token → 401 `invalid token`, operator → 201,
  operator-on-admin-path → 403, admin → 200 (verified end-to-end through the
  real proxy topology earlier; backend suites `test_dashboard_auth`,
  `test_fiat_payments`, `test_modal_backend`, `test_tenant_binding` green).
- Secrets (`API_SHARED_TOKEN`/`API_ADMIN_TOKEN`) never in the browser bundle:
  `NEXT_PUBLIC_API_TOKEN=""` baked (verified `useState("")` in bundle),
  bundle secret-name scan clean (one UI help string naming the secret, no value).
- No auth bypass added; RBAC/tenant isolation unchanged (backend untouched).

## 5. Personal feature matrix (after repair)

| Feature | Endpoint(s) | Status |
|---|---|---|
| Dashboard KPIs + Recent activity | `dashboard/summary`, `dashboard/recent` | ✅ works signed in; friendly 401 guidance when not |
| Sign-in banner | `api/me` (public, role label) | ✅ new |
| Send fiat (create + confirm) | `fiatCreate` → `POST /api/payments/fiat`, `fiatConfirm` | ✅ payloads match `FiatCreateIn`; needs operator token |
| Send crypto (regtest) | `cryptoSimulate` → `POST /api/payments/crypto/simulate` | ⚠️ honest 503 `BLOCKED_NO_CREDENTIALS` unless Secret holds `BTCPAY_*_TEST` (config-dependent, not a UI bug) |
| Receive (Sepolia request + track/live poll) | `evmRequest`, `evmStatus` | ✅ correct; empty-address default fixed |
| Scheduled (programmable) | `pagCreate` + `pagActivate(role creator)` | ✅ terms/roles validated against `ALLOWED_CONDITIONS`, `_ROLE_ALLOW` |
| Assistant (advisory) | `aiAssistant`, `aiUsage` | ✅ advisory-only contract unchanged |
| History search/pagination/details/receipt | `dashboardRecent`, `fiatGet`, `evmStatus`, `pagGet` | ✅ correct tenant scoping |
| Disputes (file/track) | `disputeCreate/List/Get` | ✅ SDK calls correct |
| Settings (sign-in/out, wallet, notif) | session-local + `window.ethereum` | ✅ unchanged |

## 6. Banking Workspace regression results

No banking/shared-component logic changed (only additive: nav entry, new
pages, personal-local banner, simulator-local logic). `next build` green for
all routes (`/`, `/banking`, `/personal`, `/private`, `/simulator`,
`/design-system`); frontend vitest **28/28** green. No regressions observed.

## 7. Remaining blockers (no code action taken)

1. **Deploy required** for any of this to be visible (dirty tree + new
   `/private` route): rebuild frontend with backend origin + empty token,
   `modal deploy modal_backend/app.py`, `modal deploy modal_frontend.py`
   (manual, approved operator step — not done here).
2. **Simulator "unreachable"** — backend/CORS/versions ruled out (§3);
   if it persists in one browser, capture devtools Network entry for the
   failing POST (status vs CORS vs timeout) — the new health indicator +
   `BACKEND-UNREACHABLE` card now surface this directly.
3. **Crypto 503 without `BTCPAY_*_TEST`** — expected sandbox behavior; add
   test credentials to `hybridpay-test` only if regtest invoice flow is
   wanted (dashboard Edit, never delete/recreate).
4. **Pre-existing test debt** (unchanged, non-blocking): 9 PDP/break-glass
   failures from missing `_admin` fixtures (test-harness drift, production
   gates proven correct), plus cross-file pollution in ad-hoc multi-file
   pytest runs (each file green alone; also present on clean HEAD).

## 8. Startup and deployment instructions (manual)

```bash
# Local startup (dev)
cp .env.example .env   # adjust only local ports/tenants; never real secrets
python -m uvicorn modal_backend.api:app --port 8000        # backend
pnpm --filter @hybridpay/terminal dev                      # frontend :3000

# Sandbox deploy (operator, explicit approval)
modal deploy modal_backend/app.py
NEXT_PUBLIC_MODAL_API_URL=https://michail-tsvetanov--hybridpay-sandbox-fastapi-app.us-east.modal.run \
NEXT_PUBLIC_API_URL=https://michail-tsvetanov--hybridpay-sandbox-fastapi-app.us-east.modal.run \
NEXT_PUBLIC_API_TOKEN="" pnpm --filter @hybridpay/terminal build
BACKEND_URL=https://michail-tsvetanov--hybridpay-sandbox-fastapi-app.us-east.modal.run \
modal deploy modal_frontend.py

# Post-deploy smoke (do NOT sign in with anything but the Secret token)
# 1. GET <backend>/health → 200 OFF/sandbox
# 2. GET <frontend>/{,banking/,personal/,private/,simulator/} → 200
# 3. Unsigned POST fiat/simulate → 401; sign in (operator) → 201 sandbox:true
# 4. Simulator fiat-fail → DECLINED-AS-EXPECTED (simulated:false, no LOCAL tag)
# 5. Personal unsigned → Sign in banner; signed → dashboard KPIs load
# 6. Banking unchanged; /api/me roles correct; no token echoed anywhere
```

Rollback: `modal app stop hybridpay-terminal|hybridpay-sandbox`, or
`git revert` + redeploy. Live payments stay disabled (`LIVE_MODE=false`,
no approval file, mock/BTCPay-test only).

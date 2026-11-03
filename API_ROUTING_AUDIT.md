# API Routing Audit — Universal Hybrid Payment Terminal

Date: 2026-11-04. Backend live-verified `/health` 200
(`liveMode OFF, sandbox true`). No code changed by this audit that alters
routing; tree already contains the simulator/personal fixes (uncommitted?
No — committed `0a96023`).

## 1. Frontend API clients (all in `packages/sdk/src/index.ts`)

| Client | Base URL source | Used by | Routes hit |
|---|---|---|---|
| `HybridPayClient` (`index.ts:75-96`) | `NEST_URL` = `NEXT_PUBLIC_API_URL` (`app/page.tsx:12`) | main page Order/QR tab only | `POST /v1/orders`, `/v1/orders/{id}/checkout-token`, `/v1/instructions/{id}` (NestJS `apps/api` — **not** the Modal backend) |
| `ModalBackendClient` (`index.ts:100-107`) | `MODAL_URL` = `NEXT_PUBLIC_MODAL_API_URL ?? NEXT_PUBLIC_API_URL ?? http://localhost:8000` (`app/page.tsx:13`, `app/simulator/page.tsx:9`, `src/components/session.tsx:5`) | main fiat/crypto/contract/status tabs, Banking, Personal, Private, simulator | `/api/…`, `/health`, `/ready` on the Modal FastAPI backend |

URL construction: `` `${baseUrl}${path}` `` with paths always starting in
`/api/` (`index.ts:120,133`). `resolveBaseUrl` (`index.ts:46-52`) only
allows `http(s)://…` or same-origin paths — a base of `/api` would
double-prefix to `/api/api/…` → 404, so the base MUST be the backend origin
(documented in `modal_frontend.py:7-9`, `modal_site_server.py:56-66`).

## 2. Deployed bundle: baked URL == verified URL

Extracted from the live frontend chunks (2026-11-04):
- `app/simulator/page-8f74d80a00123d19.js` → `https://michail-tsvetanov--hybridpay-sandbox-fastapi-app.us-east.modal.run`
- shared `314-d7e8a00d0cadbdfa.js` (useSession → Personal/Banking/Private) → same origin
- `app/page-*.js` (main) → same origin (×2: `MODAL_URL` + `NEST_URL`)

All pages point at the verified backend. **No hardcoded wrong URL, no stale
endpoint, no env mismatch.** The `localhost:8000/3001` strings in the bundle
are unreachable fallbacks (`??` branches), never taken in the deployed build.

## 3. Scenario traces (button → handler)

Common request shape (`index.ts:109-116,131-135`): `POST {base}/api/payments/fiat/simulate`,
headers `Content-Type`, `X-Tenant-Id: demo-tenant`, `Authorization: Bearer …`
(iff signed in), `Idempotency-Key: sim-<ts>-<scenario>` (unique per click —
no auto-retry, no accidental 409).

- **fiat-ok** (`instructionId …-sim-ok`): `fiat_authorize` (`providers.py:42-55`)
  → `ok/AUTHORIZED` → `api.py:584-591` mints `tx-…`, stores, returns **201**
  `{transactionId, state, providerRef, sandbox}` (`TxStatus`, `index.ts:131`).
- **fiat-fail** (`…simfail` → `scenario_for` = `failure`): `providers.py:49`
  → `ok=False, PROVIDER_ERROR` → `api.py:581-583` raises **422**
  `PROVIDER_ERROR: mock declined`. Same route/auth/payload as fiat-ok —
  only the instruction suffix differs.
- Response parsing: `request()` (`index.ts:117-130`): transport throw → 503
  `Backend unreachable…`; `!r.ok` → `ApiError(status, detail)`.
  Simulator maps via `src/simulator-results.ts:57,92` (success vs error);
  Personal/Banking use `friendlyError` (401 text preserved).

## 4. Direct calls vs proxy

Browser → backend is **direct** (absolute baked origin, cross-origin, CORS
allow-listed — see `CORS_AUDIT.md`). `modal_site_server.py:56-89` (`_proxy_api`)
is a same-origin /api/* forwarder for manual curl checks; it forwards ONLY
`content-type, authorization, x-tenant-id, idempotency-key, accept,
stripe-signature, btcpay-sig` and drops Modal-internal headers. It is NOT on
the browser path. `BACKEND_URL` must equal the backend origin at serve/deploy
time (`modal_frontend.py:25-27`).

## 5. Personal vs Banking integration

Identical client (`ModalBackendClient` via `useSession`), identical headers,
identical 401-when-unsigned semantics. Observed difference was session state,
not integration: page-local in-memory tokens (sign-in on Banking does not
carry to Personal/simulator). Personal now shows a sign-in banner when
unsigned (`app/personal/page.tsx: PersonalSignIn`); Banking unchanged.

## 6. Known stale reference (documented, NOT changed)

Main-page Order/QR tab → `HybridPayClient` → `POST {MODAL_URL}/v1/orders` →
**404** live-verified: the NestJS `apps/api` is not deployed on Modal, so
`/v1/*` does not exist there. Sandbox fiat/crypto/contract flows are
unaffected. Fix options (operator decision): hide the tab in the Modal build
or deploy the Nest API; no change made here to avoid altering working flows.

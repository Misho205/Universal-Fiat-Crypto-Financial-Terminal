# Payment Error Handling Report — simulator consistency

Date: 2026-11-04. Backend contract preserved (no `api.py` change);
fix is a frontend normalization layer + explicit execution mode.

## 1. Root causes (exact)

**R1 — Decline misclassified as outage.** `fiat-fail` returns HTTP **422**
`PROVIDER_ERROR: mock declined` (`api.py:581-583` over
`providers.py:48-49`). The old simulator `catch` treated every throw as
"backend unreachable" + local simulation. A structured backend *response*
was presented as a transport failure.

**R2 — Auth conflated with network.** Unsigned/wrong-token runs return 401
`missing/invalid token` (`auth.py:40-48`, verified live). Old UI appended
"backend … does not respond" to them as well. Auth is per-page in-memory
state — Banking looked fine only because it was signed in there.

**R3 — Silent fallback.** Any error could render `LOCAL` results without an
explicit operator decision.

## 2. Backend handling (kept as-is — correct)

- Decline = **422 business error**, not transport error: no `transactionId`
  minted, nothing stored, audit-logged only on success path (`api.py:589`).
- Timeout = **502** `TIMEOUT_UNKNOWN` with "query original before retry"
  (`providers.py:50-52`, `api.py:582`); no tx id exists for legacy
  `/simulate`, so the UI must NOT mint a new payment — it reuses the SAME
  idempotency key on manual retry (already unique-per-click; no auto-retry).
- 409 on key+payload mismatch, 400 on schema, 401/403 via `require_auth` /
  `require_role` (`auth.py`), tenant isolation in `require_tenant`.

## 3. Unified result model (`apps/terminal/src/simulator-results.ts`)

`{scenarioId, transactionId, paymentState, testOutcome, executionSource,
providerReference, errorCode, userMessage, timestamp, sandbox}` —
`PaymentState: AUTHORIZED|DECLINED|REJECTED|UNKNOWN`;
`TestOutcome: PASSED|FAILED`;
`ExecutionSource: BACKEND_SANDBOX|CRYPTO_TESTNET|LOCAL_SIMULATION`.

Mapping (`errorToResult`, `:92`; `successToResult`, `:57`):
- 422 `PROVIDER_ERROR` → `DECLINED/PASSED/BACKEND_SANDBOX` ("backend WAS reached").
- 502 `TIMEOUT_UNKNOWN` → `UNKNOWN/PASSED` + same-key retry guidance.
- 422 other / 200 `ok:false` contract → `REJECTED/PASSED` (expected).
- 400 client validation → `REJECTED/PASSED/LOCAL_SIMULATION` (rejected pre-network).
- 401 missing/invalid → `UNKNOWN/FAILED/AUTH_MISSING|AUTH_INVALID` + sign-in guidance.
- 403 → `AUTHZ_FORBIDDEN/FAILED`; 409 → `IDEMPOTENCY_CONFLICT/FAILED`.
- Only `isNetworkFailure` (`:37`: non-ApiError, or 503 "Backend unreachable at…")
  → `UNKNOWN/FAILED/NETWORK_UNREACHABLE` with connectivity diagnostics and
  the explicit guarantee "Nothing was executed; no local result was substituted".
- 400/401/403/409/422 are NEVER classified as network failures (unit-tested).
- Headlines: `Scenario PASSED — Payment DECLINED` / `Scenario PASSED — Payment
  AUTHORIZED` / `Scenario FAILED — Backend unreachable|Authentication required`.

## 4. Simulator UX (`app/simulator/page.tsx`)

- Execution-mode radio: **Backend sandbox** (default, real HTTP, failures
  shown as-is, no silent fallback) vs **Local demo** (explicit, deterministic,
  every card labeled `LOCAL_SIMULATION`).
- Consistent cards: headline + all 10 model fields + userMessage; expected
  declines render green/PASSED with provider decline text, not red outage text.
- Live backend health line (`/health`, public) + unchanged token sign-in
  (memory-only). Banking/Personal untouched by this change.

## 5. Verification (end-to-end, no claim without test)

- Live unsigned: fiat/contract/AI → 401 ✅; wrong token → 401 ✅; evil-origin
  preflight → rejected ✅; stale `/v1/orders` → 404 (documented, untouched) ✅.
- Local signed TestClient: 201 AUTHORIZED, 422 PROVIDER_ERROR, unsigned/wrong 401,
  operator-cancel 403, admin-cancel 200, contract 200, AI 200 ✅.
- Frontend vitest **43/43** (incl. 15 new `simulator-results` cases: success,
  decline, timeout+guidance, invalid, 401×2, 403, wrong-network ×2, contract ×2,
  unreachable, CORS-TypeError, 409, local demo ×5); `next build` green ✅.
- Banking regression: no shared-logic change; all routes build; backend suites
  `test_dashboard_auth/test_fiat_payments/test_modal_backend/test_tenant_binding`
  green ✅.
- Pre-existing, unrelated: `test_security_integration::test_high_risk…`
  (bare-dev 404-vs-401, missing `_admin` fixture) + 8 sibling PDP/break-glass
  fixture-drift failures + cross-file pytest pollution — all reproduce on clean
  HEAD, production gates proven correct elsewhere.
- Deployed/frontend parity: deployed simulator chunk (`page-8f74d80a…`) lacks
  `executionSource`/`NETWORK_UNREACHABLE`; local build is `page-1eff0a13…` →
  **fixes are NOT yet deployed** (expected — no auto-deploy).

## 6. Remaining blockers / manual deployment

1. Redeploy frontend (rebuild bakes backend origin + empty token), backend
   redeploy optional (unchanged, but tree moved — redeploy for consistency):
  ```bash
  modal deploy modal_backend/app.py
  NEXT_PUBLIC_MODAL_API_URL=https://michail-tsvetanov--hybridpay-sandbox-fastapi-app.us-east.modal.run \
  NEXT_PUBLIC_API_URL=https://michail-tsvetanov--hybridpay-sandbox-fastapi-app.us-east.modal.run \
  NEXT_PUBLIC_API_TOKEN="" pnpm --filter @hybridpay/terminal build
  BACKEND_URL=https://michail-tsvetanov--hybridpay-sandbox-fastapi-app.us-east.modal.run \
  modal deploy modal_frontend.py
  ```
2. Post-deploy: `/health` 200 OFF/sandbox; all 6 routes 200; unsigned simulate
  → 401; signed fiat-ok → `Scenario PASSED — Payment AUTHORIZED`;
  fiat-fail → `Scenario PASSED — Payment DECLINED` (no LOCAL tag);
  mode toggle visible; `/api/me` role correct; no token echoed.
3. Guardrails preserved: sandbox/testnet only, `LIVE_MODE=false`, auth/RBAC/
   tenant/audit untouched, no secrets in bundles, no live transactions.

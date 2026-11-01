# Security Review — Universal Hybrid Payment Terminal
> **Update 2026-11-01 (follow-up):** Cancel/refund are now idempotent (`Idempotency-Key` supported, 409 on conflict, replay returns stored response). AI usage is now per-tenant (`usage_snapshot(tenant)`; fresh tenants see zeros). Gaps #1 (non-idempotent cancel/refund) is CLOSED; per-tenant AI history CLOSED.

Date: 2026-11-01. Scope: `apps/terminal`, `packages/sdk`, `modal_backend` (auth/config/api). Method: code inspection + `pytest` (59 passed) + local live probe. Sandbox/testnet only. No production claim.

## 1. Verdict

No hardcoded secrets in the frontend bundle. Auth is server-enforced (bearer + tenant binding). Money actions are admin-gated + maker-checker (UI) with backend re-check. AI/provider keys stay server-side. Fail-closed on live money (no approval file, no live creds). Three low-severity gaps documented below; no critical finding blocking a sandbox demo.

## 2. Secrets in frontend — PASS

- Grep `MODEL_API_KEY|STRIPE_SECRET|BTCPAY|private key|mnemonic|seed phrase` in `apps/terminal` + `packages/sdk`: only negative test assertions (`sdk.test.ts:46,70`), user warnings ("Never share seed phrases…", `personal/page.tsx:411`), and code comments ("keys never leave wallet", `evm.ts:2-3`; "NEVER a provider secret", `sdk/src/index.ts:6-8`). No `sk_live/sk_test`, no key material.
- Browser env: only `NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_MODAL_API_URL`, `NEXT_PUBLIC_API_TOKEN` (dev sandbox bearer), `NEXT_PUBLIC_LIVE_MODE` (`.env.example:19-22`). SDK comment: "Next.js exposes only NEXT_PUBLIC_* … secrets can never leak here" (`index.ts:38`).
- Token handling: in-memory React state only (`session.tsx:17-19`, `page.tsx:36`), `type="password"` inputs, logout clears (`setToken("")`). Never localStorage. Error strings truncate to 200 chars and never echo tokens (`friendlyError`, `session`).
- Backend secrets (`config.py`): `API_SHARED_TOKEN`, `API_ADMIN_TOKEN`, `MODEL_API_KEY` (+legacy alias), `STRIPE_SECRET_KEY_TEST`, `STRIPE_WEBHOOK_SECRET_TEST`, `BTCPAY_URL/API/STORE_TEST`, `SEPOLIA_RPC_URL`, `*_LIVE_*` — all `os.environ`, injected via Modal secret `hybridpay-test`, never returned by any endpoint (`/api/me` returns role label only, no token echo).

## 3. Authentication & authorization — PASS with notes

- `auth.py`: `role_of` uses `hmac.compare_digest` (admin first, then operator). `require_auth` → 401; `require_admin` → 401/403; dev bypass (`dev-caller`) only when NO tokens configured (bare local dev). Tested: RBAC matrix (`test_dashboard_auth.py`), tenant binding (`test_tenant_binding.py`).
- Tenant isolation: `require_tenant` derives tenant from the token when `TENANT_FOR_SHARED_TOKEN` / `TENANT_FOR_ADMIN_TOKEN` is set and **ignores** `X-Tenant-Id` (`auth.py`). Unset = local-dev header mode (explicitly marked). Demo deployment intentionally leaves bindings unset (open demo tenant) — documented in INTEGRATION_REPORT; set them for any shared staging.
- Sensitive paths: fiat `cancel/refund`, agreement `execute/cancel/dispute` = `require_admin` (`api.py:440,457,…`). Webhook requires auth + HMAC (`stripe-signature`), forged→401, stale→410, dedupe via idempotency store. Evidence submission requires authenticated source; AI bypass/custody claims rejected by validator (`test_programmable_contracts.py`).
- UI mirrors server (never replaces it): banking hides admin modules for operators + banner "Full access requires admin token"; `TxTable` row actions disabled by design — all money goes through `MakerCheckerDialog` (distinct maker ≠ checker + reason required, `banking-shared.tsx:75,90-91`) which the backend re-gates with admin token.

## 4. Tenant-header trust — ADDRESSED

Past prompt required: do not trust user-controlled tenant headers. Implemented: bound mode ignores the header entirely (covered by `test_tenant_binding.py::test_unbound_uses_header_but_bound_ignores_it`, `test_admin_binding_applies_to_sensitive_paths`). Deploy checklist sets `TENANT_FOR_*` (`docs/modal-deploy-checklist.md`). Residual: demo deployment leaves them unset by choice — must be set before any shared staging (tracked in DEMO_READINESS).

## 5. Input validation & injection

- Client: `assertMinorUnits/EvmAddress/TxHash/ChainId`, URL allowlist (`http(s)` or same-origin, rejects `javascript:`), all tested.
- Server: pydantic models on every POST, `assert_testnet` (mainnet refused 422 `MAINNET_REFUSED`), address/hash regex, provider errors mapped to 422/409 (never 500 leak; global handler returns generic "internal error").
- Webhook: raw-body HMAC verify before JSON parse; `STALE_EVENT` → 410.

## 6. Transport & platform

- CORS allowlist from `ALLOWED_ORIGINS` (default localhost:3000,3001), `allow_credentials=False`, methods GET/POST only, headers limited to Auth/Content/X-Tenant/Idempotency (`api.py:46-52`). No cookies, no CSRF surface (bearer in memory).
- Modal static frontend proxies `/api/*` same-origin (`modal_site_server.py`) — no browser CORS to third parties, no secrets in bundle.
- Logs redacted (`logging_util`), PAN scrubbed in AI tests, no provider refs in error strings beyond truncated 200ch.

## 7. Keys & wallets

- EVM: wallet signs locally (`viem`), backend only tracks/verifies receipts, never receives keys (`evm.py`, `EvmPanel`, SDK `never holds keys`). Mainnet refused both client (`assertChainId`) and server (`assert_testnet`).
- BTC: regtest `bcrt1…` only, client pre-validates prefix; server validates network.
- Settings explicitly warns against seed sharing; connect-wallet uses `eth_requestAccounts` only, disconnect clears state.

## 8. AI safety

Advisory-only envelope on every AI route; fraud NOT-certified disclaimer + fail-closed; assistant strips unsafe actions (read-only); rate limit 20/min → 429; usage counters; no MODEL_API_KEY in browser (server-side `meta_client` only, opt-in live `RUN_META_INTEGRATION`).

## 9. Gaps (low severity, sandbox-scoped)

1. **Cancel/refund not idempotent**: endpoints accept no `Idempotency-Key`; UI disables button in flight but a retried request could double-execute if the first actually succeeded and the response was lost. Mitigation for demo: confirm via retrieve before retry; backend idempotent cancel/refund is a requested API (plan §7).
2. **Maker-checker is UI-only**: distinct maker/checker enforced in dialog, but no backend intent object; a raw admin-token call bypasses the two-person rule. Server still requires admin — acceptable for hackathon, must not be presented as institutional control.
3. **No user/seat management endpoint**: admin view honestly states "No users/seats endpoint … access via Modal Secrets" instead of faking. Fine for demo; required before any multi-user staging.
4. **Demo tenant unbound**: `TENANT_FOR_*` unset on the public demo deployment (open tenant by design). Set before shared staging.

## 10. What was NOT done (and must precede any real money)

No mainnet, no live Stripe/BTCPay wiring, no KYC/KYB, no fiscal (NRA H-18) integration, no custody, no audit of contracts, no pentest, no DPA. `docs/real-money-roadmap.md` + `docs/live-mode.md` (fail-closed) govern. Do not deploy production payments on this build.

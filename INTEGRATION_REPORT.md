# End-to-end integration report — workspaces ↔ Modal FastAPI backend

Date: 2026-10-31. Backend: `https://michail-tsvetanov--hybridpay-sandbox-fastapi-app.us-east.modal.run`
(deployed, sandbox, `liveMode: OFF`). Frontend: static export served on Modal with
same-origin `/api/*` proxy (no CORS, no browser secrets).

Method: `modal_backend/openapi.snapshot.json` (40 paths / 20 schemas, captured live)
is the contract. `modal_backend/probe_live.py` exercises every path against the real
deployment — **46/46 verified green** (run 2026-10-31, plus `test_live_integration.py`
which runs the same sweep in CI-gated opt-in mode). `test_openapi_coverage.py` fails
the suite if any snapshot path lacks probe + SDK coverage (no silent Swagger-only endpoints).

## Verified working (live, real backend)
- Health + identity: `GET /health` (OFF/sandbox), `GET /api/me` (role labels, no token echo).
- Fiat sandbox: create (idempotent, 409 on conflict) → confirm (authoritative provider
  state) → retrieve (now includes `idempotencyKey`) → cancel/refund (admin-gated 403 for
  operator, verified both), list, legacy `simulate`, `GET /api/transactions/{id}` + 404 isolation.
- EVM Sepolia: request (chain guard; mainnet 422 `MAINNET_REFUSED`; bad address 422) →
  submit → status (confirmations, explorer link, `businessSettled:false`) → replace →
  list. No keys ever leave the wallet (asserted on source).
- Programmable contracts: create (validator rejects AI bypass + custody claims) →
  get → activate → approve → evidence (unauthenticated rejected) → execute
  (eligibility AND executor AND admin token; never from eligibility alone) →
  cancel/dispute (admin). Full lifecycle verified live incl. audit chain.
- Dashboard: `summary` counts + `recent` with kind/state/q filters + tenant isolation;
  `recent` now also returns `provider` + `sandbox` per item (shown as badges in UI).
- AI (all advisory-only, validated-or-stub): explain fiat/crypto/state, fraud (with
  NOT-certified disclaimer, fail-closed high), routing, contract analysis, assistant
  (unsafe actions stripped), `GET /api/ai/usage` counters.
- Webhooks: forged → 401, stale → 410, valid → 200/deduped, state applied from
  verified events only. (Server-to-server; intentionally NOT in the browser SDK.)
- Auth model: bearer operator/admin + server-side tenant binding when
  `TENANT_FOR_*` is set (header ignored; covered by `test_tenant_binding.py`);
  unset in demo → header mode with dev-caller marking. No MODEL_API_KEY, provider
  secrets, PAN, or private keys in the browser or logs (scanned).
- Frontend wiring: typed `ModalBackendClient` generated from the snapshot schemas
  (`modal-schema.ts`), env-based base URL with scheme validation, client-side
  validation (fail fast, no junk over the wire), loading/success/failure/retry states,
  idempotency keys per submit, live status polling with backoff + terminal-state stop,
  provider/sandbox badges + idempotency keys in detail views, AI analysis buttons.

## Incomplete / explicitly not done (no silent substitution anywhere)
1. **Live provider execution**: Stripe TEST network calls, BTCPay regtest stack, Sepolia
   live-RPC receipt checks, Meta live calls — all mocked in CI; operator-run docs exist
   (`docs/fiat-sandbox.md`, `docs/evm-sepolia.md`, `docs/ai-integration.md`). The UI
   labels every one of these sandbox/testnet and shows provider names verbatim.
2. **Backend gaps** (UI shows "not available" instead of faking): user/seat management,
   maker-checker intent objects (UI enforces 2-person rule client-side only),
   `POST /api/reconcile/runs` on Modal (Nest-only), pagination on fiat/evm/agreement
   lists, per-tenant AI history, webhook test-trigger. See FRONTEND_IMPLEMENTATION_PLAN §7.
3. **On-chain smart contracts, fiscal receipts, KYC/KYB, mainnet, custody** — roadmap only.
4. Tenant binding env (`TENANT_FOR_*`) is implemented + tested but **not set** on the
   demo deployment (deliberate: open demo tenant). Set it for any shared staging.

## How to re-verify
```
# full live sweep (sandbox only, ~30s):
BACKEND_URL=https://<backend> python modal_backend/probe_live.py   # expect 46/46
# pytest gate (skipped unless both vars set):
RUN_LIVE_BACKEND_TESTS=1 BACKEND_URL=https://<backend> pytest modal_backend/test_live_integration.py -q
# contract drift guard (offline, always runs):
pytest modal_backend/test_openapi_coverage.py -q
```

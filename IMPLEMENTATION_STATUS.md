# IMPLEMENTATION_STATUS.md — Universal Hybrid Payment Terminal

Generated: 2026-10-31 (UTC). Scope: Modal startup fix + fiat sandbox E2E + EVM Sepolia + programmable contracts.
Policy: no invented results — every claim below cites an executed command or a file.

## 1. Modal startup failure — reproduction & fix
- **Reproduce**: `modal serve modal_backend/app.py` — image builds (fastapi/httpx/pydantic/stripe/uvicorn),
  functions `fastapi_app` + `reconcile_tick` created, `Serving... Watching ./modal_backend` — **no traceback;
  startup succeeds** in this environment (modal 1.6.3, secret `hybridpay-test` present).
- **Root-cause analysis (no failure to fix, hardened instead)**:
  - Working directory: repo root `/workspaces/Universal-Fiat-Crypto-Financial-Terminal`; Modal uploads
    `modal_backend/app.py` as a package (`modal_backend/__init__.py` present) so relative import
    `from .api import app` resolves under both `modal serve` and `python -c "import modal_backend.app"`.
  - Deps: `requirements.txt` pins == image pins in `app.py` (fastapi 0.115.6, uvicorn 0.34.0,
    pydantic 2.10.4, httpx 0.28.1, stripe 11.3.0); local interpreter is 3.14.2 vs image 3.11 —
    local-only skew, image is authoritative and builds clean.
  - Config: `app = modal.App("hybridpay-sandbox")`, CPU-only (`cpu 0.5/0.25`, `memory 512/256`),
    no GPU args, `min_containers=0`, no `schedule=` (removed for cost control), secrets via
    `modal.Secret.from_name("hybridpay-test")` — verified present (`modal secret list`).
  - Import check: `python -c "import modal_backend.app; import modal_backend.api"` → OK, 13 routes.
- **Verify**: `API_SHARED_TOKEN=dev-shared-token uvicorn modal_backend.api:app --port 8123` →
  `GET /health` → `{"ok":true,"liveMode":"OFF","sandbox":true}`; `pytest modal_backend/` → **25 passed, 1 skipped**.
  Dev serve not left running (operator step; needs `modal token` on their machine).

## 2. Requirement audit (fiat / crypto / contracts / AI / frontend / db / auth / deploy)
| Area | Status | Evidence |
|---|---|---|
| Fiat sandbox E2E | ✅ implemented + tested | `payments.py` (ABC + Mock + Stripe TEST), `db.py` (SQLite), 7 fiat endpoints, `test_fiat_payments.py` 7/7, `docs/fiat-sandbox.md` |
| Stripe test mode | ✅ implemented, mocked-tested; live-network run documented, not executed here | `StripeTestProvider` (`sk_test_*` enforced), factory fallback to mock, `docs/fiat-sandbox.md` integration steps |
| Crypto testnet | ✅ implemented, partially tested | `crypto/simulate` + regtest validation, `test_modal_backend.py`; full regtest stack needs docker profile (not run) |
| Programmable contracts | ✅ implemented + tested | `contracts.py` allowlist validator + `validate_terms` tests; on-chain contracts out of scope (see `docs/real-money-roadmap.md`) |
| AI integration | ✅ implemented + tested | explain fiat/crypto, contract analysis, fraud (NOT certified), routing, state explainer, assistant (read-only, safe actions) + usage endpoint; mocked tests + opt-in live; `docs/ai-integration.md` |
| Frontend | ✅ implemented + tested | dashboard tabs incl. EVM Sepolia + Agreements + simulator, `demo-flow.test.ts` E2E (mocked), `i18n` parity, builds green |
| Database | ✅ implemented + tested | `db.py` SQLite durable (+ evm_payments, contract_agreements) + persist tests; Postgres remains system of record for Nest API |
| Auth | ✅ implemented + tested | bearer + tenant guards, 401/400 paths tested, CORS allowlist tested |
| Deploy | 🟡 code-ready, NOT deployed | `modal serve` verified locally; `modal deploy` is an operator step (no approval given) — see `docs/modal-deploy-checklist.md` |

## 3. Implemented and verified (executed in this session)
- `modal serve modal_backend/app.py` → Serving, no error.
- `pnpm build` → 9/9 green. `pnpm test` → 11/11 suites green (sdk 6, terminal 5 incl. evm + programmable E2E).
- `pytest modal_backend/` → all green incl. `test_evm_payments.py` (6 passed, 1 skipped opt-in live RPC)
  and `test_programmable_contracts.py` (5 passed).
- `node --test tests/property tests/integration` (explicit files) → 4/4.
- `POST /api/payments/fiat/simulate` live local → 201 `AUTHORIZED`; `/health` → `liveMode OFF`.

## 4. Implemented but NOT live-tested (needs operator key/infra)
- Stripe TEST network calls (`StripeTestProvider.create/confirm/retrieve`) — mocked path tested; real
  `sk_test_*` exchange documented in `docs/fiat-sandbox.md`, not executed (no key provided).
- Sepolia live RPC receipt check — mocked JSON-RPC tested; read-only live run documented in
  `docs/evm-sepolia.md`, not executed (no RPC URL / known tx provided).
- BTCPay regtest stack (docker profile bitcoind + btcpay) — code ready, `SANDBOX_BLOCKED` without creds.
- Meta model live call — skipped by design (`RUN_META_INTEGRATION` unset).
- `modal deploy` — not run (explicitly withheld without approval).

## 5. Missing / out of scope for this session
- On-chain smart contracts (Solidity/Vyper + audit) — roadmap only (`docs/real-money-roadmap.md`).
- Fiscal (NRA H-18) integration, KYC/KYB vendor wiring, mainnet/CASP — roadmap only.
- Postgres-backed Modal writes (SQLite file is the durable store for the sandbox backend; Postgres stays
  behind `apps/api`).

## 6. Blocking issues
- None for sandbox/demo. Live money is blocked by design (no approval file, no live creds — fail-closed).

## 7. Exact next steps
1. Operator: `modal serve modal_backend/app.py`, run `docs/modal-deploy-checklist.md` §§3+6 (health + UI + simulator 5/5).
2. Optional Stripe TEST: follow `docs/fiat-sandbox.md` integration steps with `sk_test_*`, record paymentId/state/webhook count.
3. Optional regtest: `docker compose --profile btc up`, set `BTCPAY_*_TEST`, rerun crypto tests.
4. For production: work through `docs/real-money-roadmap.md` in order (license/partner → fiscal/KYC → mainnet → CASP → audited contracts).

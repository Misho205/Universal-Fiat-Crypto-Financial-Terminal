# Modal deploy checklist — hackathon demo (sandbox only, no live deploy without approval)

> BG резюме: този документ е пълният чеклист за качване на Modal backend-а за демото. Без одобрение НЕ се деплойва live и НЕ се местят реални пари.

## 0. Preconditions (do NOT deploy if any fail)
- [ ] `pnpm build` 9/9 green, `pnpm test` 11/11 suites green, `pytest modal_backend/` green (66 passed, 4 skipped opt-in live).
- [ ] `modal_backend/openapi.snapshot.json` in sync: `python -c "from modal_backend.api import app; assert len(app.openapi()['paths'])==$(python3 -c "import json;print(len(json.load(open('modal_backend/openapi.snapshot.json'))['paths']))")"` (currently 40 paths).
- [ ] `LIVE_MODE=false`, no `*_LIVE` keys in env or Modal Secrets (scan: `grep -r "LIVE_SECRET\|sk_live" --include="*.py" --include="*.ts" .` returns nothing).
- [ ] `modal_backend/app.py` uses CPU only (`cpu<=0.5`, `memory<=512`), no GPU args, `min_containers=0`, no `schedule=` (on-demand reconcile only).
- [ ] Durable store: Modal Volume `hybridpay-data` mounted at `/mnt/data` (auto-created); Postgres via `DATABASE_URL` for prod. OpenAPI guard `test_openapi_coverage.py` green (no Swagger-only endpoints).
- [ ] Crash-loop guards green: `pytest modal_backend/test_modal_mount.py` (absolute import + `add_local_dir` bake + non-blocking `Popen` in `modal_frontend.py`).
- [ ] CORS `ALLOWED_ORIGINS` set to demo domains only (no `*`).
- [ ] `GET /health` returns `liveMode: OFF` (or `BLOCKED`), `sandbox: true`.

## 1. Authenticate with Modal (operator step, interactive)
```
pip install modal
modal token new        # opens browser, stores ~/.modal.toml (never commit it)
modal secret list      # verify access
```

## 2. Configure secrets (never in source, never in browser bundle)
```
modal secret create hybridpay-test \
  API_SHARED_TOKEN="$(openssl rand -hex 24)" \
  API_ADMIN_TOKEN="$(openssl rand -hex 24)" \
  TENANT_FOR_SHARED_TOKEN="demo-tenant" \
  TENANT_FOR_ADMIN_TOKEN="demo-tenant" \
  HYBRIDPAY_DB_PATH=/mnt/data/hybridpay.db \
  DATABASE_URL="" \
  STRIPE_SECRET_KEY_TEST="" \
  STRIPE_WEBHOOK_SECRET_TEST="" \
  BTCPAY_URL_TEST="http://localhost:23000" \
  BTCPAY_API_KEY_TEST="" \
  BTCPAY_STORE_ID_TEST="" \
  MODEL_API_KEY="" \
  META_MODEL_BASE_URL="https://api.meta.example/v1" \
  META_MODEL_ID="muse-spark-1.3" \
  ALLOWED_ORIGINS="https://<terminal-demo-domain>,http://localhost:3000"
```
Verify: `modal secret list | grep hybridpay-test`. Rotate with `modal secret create ... --force` + redeploy.

## 3. Dev preview (no traffic switch)
```
modal serve modal_backend/app.py
# note the printed https://<user>--hybridpay-sandbox-fastapi-app.modal.run
curl https://<preview-url>/health   # expect {"ok":true,"liveMode":"OFF","sandbox":true}
```

## 3b. Staging tenant binding (required before any shared staging)
- When `TENANT_FOR_SHARED_TOKEN` / `TENANT_FOR_ADMIN_TOKEN` are set, the tenant is
  derived from the bearer token and any client `X-Tenant-Id` is ignored
  (`require_tenant`, covered by `test_tenant_binding.py`). When unset, the header
  is accepted (local-dev / open-demo mode only).
- For any shared staging URL, set explicit tenants
  (`TENANT_FOR_SHARED_TOKEN`, `TENANT_FOR_ADMIN_TOKEN`) + redeploy; never run
  shared staging unbound. Re-run `pytest modal_backend/test_tenant_binding.py -q`
  after changing bindings.

## 4. Stable hackathon deploy
```
modal deploy modal_backend/app.py
# pin the printed URL as PUBLIC_BACKEND_URL, e.g.
# https://misho205--hybridpay-sandbox-fastapi-app.modal.run
```

## 5. Connect frontend
```
# terminal hosting (Vercel/Netlify/Static):
NEXT_PUBLIC_MODAL_API_URL=https://<public-backend-url>
NEXT_PUBLIC_API_URL=https://<nest-api-url>   # or same Modal URL if proxied
NEXT_PUBLIC_API_TOKEN=<dev-shared-token>     # sandbox only; prod uses session auth
NEXT_PUBLIC_LIVE_MODE=false
```
Rebuild + redeploy terminal. Dashboard shows `LIVE MODE: OFF` banner.

## 6. Verification (demo E2E, all sandbox)
```
curl $PUBLIC_BACKEND_URL/health
API_SHARED_TOKEN=<tok> pytest modal_backend/ -q
pnpm --filter @hybridpay/terminal test   # includes hackathon demo-flow E2E (mocked)
# live UI: open /, run Order/QR → Fiat sandbox → Crypto (wrong-network rejected) →
# Contract validate → Status + AI; open /simulator and run all 5 scenarios.
```

## 7. Rollback
- Code: `git revert <sha> && modal deploy modal_backend/app.py` (previous URL stays valid until redeploy finishes).
- Secrets: `modal secret create hybridpay-test ... --force` with previous values + redeploy.
- Data: Modal store is ephemeral — nothing to roll back; source of truth is `apps/api` + PostgreSQL (`pg_restore` per `docs/deployment.md`, then `POST /v1/reconcile/runs` before restarting workers).
- Emergency: `modal app stop hybridpay-sandbox` halts all traffic immediately.

## 8. Cost controls (enforced in code)
- CPU only (`cpu 0.5/0.25`, `memory 512/256`), `timeout 60s`, `min_containers=0` (scale to zero).
- No `schedule=` jobs (reconcile is on-demand). No GPU. No always-on workers.
- External costs (not Modal): Stripe sandbox free; BTCPay regtest self-hosted (~$0); Meta API tokens pay-per-use (only when `MODEL_API_KEY` set; stub otherwise).

## 9. Demo readiness assessment (fill before stage)
- [ ] `/health` OFF, dashboard banner OFF, simulator 5/5 scenarios behave as labeled.
- [ ] No `sk_live`, no mainnet addresses, no `LIVE_APPROVAL_FILE` present.
- [ ] Rollback command tested once. Owner + kill-switch operator named.

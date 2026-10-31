# Modal deploy checklist — hackathon demo (sandbox only, no live deploy without approval)

> BG резюме: този документ е пълният чеклист за качване на Modal backend-а за демото. Без одобрение НЕ се деплойва live и НЕ се местят реални пари.

## 0. Preconditions (do NOT deploy if any fail)
- [ ] `pnpm build` 9/9 green, `pnpm test` 10/10 green, `pytest modal_backend/` green (18 passed, 1 skipped).
- [ ] `LIVE_MODE=false`, no `*_LIVE` keys in env or Modal Secrets (scan: `grep -r "LIVE_SECRET\|sk_live" --include="*.py" --include="*.ts" .` returns nothing).
- [ ] `modal_backend/app.py` uses CPU only (`cpu<=0.5`, `memory<=512`), no GPU args, `min_containers=0`, no `schedule=` (on-demand reconcile only).
- [ ] `store.py` is ephemeral — acknowledged: durable money state lives in external PostgreSQL / `apps/api` (system of record), Modal never authoritative.
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
  HYBRIDPAY_DB_PATH=/mnt/data/hybridpay.db \
  DATABASE_URL="" \
  STRIPE_SECRET_KEY_TEST="" \
  STRIPE_WEBHOOK_SECRET_TEST="" \
  BTCPAY_URL_TEST="http://localhost:23000" \
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

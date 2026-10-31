# Modal sandbox backend — local development (no deploy)

Sandbox/testnet only. `apps/api` (NestJS) remains the system of record;
this FastAPI service is a stateless executor + advisory AI helper.

## AI integration (Meta Muse Spark, advisory only)

Architecture: Frontend → Authenticated Modal API → Meta Model API →
Validated AI response → Frontend.

- Model id: `muse-spark-1.3` (env `META_MODEL_ID`, account must have access).
- Key: env `MODEL_API_KEY` (`META_MODEL_API_KEY` accepted as legacy alias),
  injected via the `hybridpay-test` Modal Secret — never in source, never in
  the frontend, never logged.
- Request format assumption (recorded 2026-10-31, confirm against your
  account's official docs): OpenAI-compatible
  `POST {META_MODEL_BASE_URL}/chat/completions` with
  `{model, messages, response_format: {type: "json_object"}}`. Base URL and
  model id are env-configurable (`meta_client.REQUEST_PATH` otherwise fixed).
- Advisory endpoints (every response carries `advisoryOnly: true`):
  - `POST /api/ai/explain-transaction` — plain-language transaction explanation
  - `POST /api/ai/fraud-signals` — risk indicators; fails CLOSED to `high`
  - `POST /api/ai/routing-recommendation` — route suggestion from allow-list
  - `POST /api/ai/contract-analysis` — per-condition status + gaps
  - `POST /api/ai/analyze` — legacy draft helper (unchanged contract)
- Guards: PII/key scrubbing before send, pydantic schema validation,
  15 s timeout, max 2 retries (429/5xx only, bounded backoff), per-tenant
  rate limit (`AI_RATE_LIMIT_PER_MIN`, default 20/min → HTTP 429), usage
  logging (sizes/token counts/latency only — no content, no key).
- AI can never approve, sign, release, or transfer funds. Payment
  authorization and contract execution are enforced exclusively by the
  deterministic backend (`contracts.validate_terms`, policy decisions,
  provider adapters).

## Install
```
pip install -r modal_backend/requirements.txt
```
(Pinned versions target the Modal image, Python 3.11. On newer local
interpreters, if a wheel fails to build, install unpinned instead:
`pip install fastapi uvicorn pydantic httpx pytest`.)

## Configure (no secrets in source)
```
export ALLOWED_ORIGINS="http://localhost:3000,http://localhost:3001"
export API_SHARED_TOKEN="dev-shared-token"   # operator role (required by tests/clients)
export API_ADMIN_TOKEN="dev-admin-token"     # admin role: cancel/refund/dispute/execute
export HYBRIDPAY_DB_PATH="./data/hybridpay.db"  # local file; omit on Modal (Volume /mnt/data)
export DATABASE_URL=""                       # empty = SQLite; postgresql://... for production
# sandbox provider keys (optional; without them the mock/blocked path is used)
export STRIPE_SECRET_KEY_TEST="" BTCPAY_API_KEY_TEST="" BTCPAY_STORE_ID_TEST=""
export MODEL_API_KEY=""                      # empty => offline-safe AI stub
export META_MODEL_BASE_URL="https://api.meta.example/v1"  # confirm per account docs
export META_MODEL_ID="muse-spark-1.3"
```

## Run tests (no Modal account, no network, no paid tokens)
```
API_SHARED_TOKEN=dev-shared-token API_ADMIN_TOKEN=dev-admin-token pytest modal_backend/ -q
# 47+ passed, 3 skipped (live integrations, opt-in only — see below)
```

Live integration test (consumes tokens; runs ONLY when explicitly enabled):
```
RUN_META_INTEGRATION=1 MODEL_API_KEY=<key> META_MODEL_BASE_URL=<url> \
  API_SHARED_TOKEN=dev-shared-token pytest modal_backend/test_meta_ai.py -q
```

## Serve locally (no deploy)
```
API_SHARED_TOKEN=dev-shared-token uvicorn modal_backend.api:app --port 8000
curl localhost:8000/health
```

## Deploy to Modal (operator step — do NOT run for production)
Prerequisite: `modal token new` (one interactive login), then:
```
modal secret create hybridpay-test API_SHARED_TOKEN=... API_ADMIN_TOKEN=... \
  HYBRIDPAY_DB_PATH=/mnt/data/hybridpay.db DATABASE_URL=... STRIPE_SECRET_KEY_TEST=... \
  BTCPAY_URL_TEST=... BTCPAY_API_KEY_TEST=... BTCPAY_STORE_ID_TEST=... \
  MODEL_API_KEY=... META_MODEL_BASE_URL=... META_MODEL_ID=muse-spark-1.3
modal serve modal_backend/app.py   # preview
modal deploy modal_backend/app.py  # sandbox deploy only
```
Then: run the checks in `docs/test-report.md`, confirm the deployed
`/health` reports `liveMode: OFF`, and exercise the AI endpoints with a
sandbox tenant before any demo. Live funds / live credentials are
forbidden. Modal container disk is ephemeral — durable state lives in
the external PostgreSQL / apps/api.

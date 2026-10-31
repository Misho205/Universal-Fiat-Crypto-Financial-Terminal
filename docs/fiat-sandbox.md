# Fiat sandbox payments — end-to-end (TEST mode only)

> No real money. `LIVE_MODE=false`. Live credentials are refused by construction.

## Architecture
- `modal_backend/payments.py` — `PaymentProvider` ABC (`create/confirm/retrieve/cancel/refund/verify_webhook`),
  `MockFiatProvider` (deterministic, no network), `StripeTestProvider` (official `stripe` SDK, `sk_test_*` only).
  Factory `get_fiat_provider()` picks Stripe TEST when a test key is present, else mock.
- `modal_backend/db.py` — SQLite durability (`./data/hybridpay.db`, `HYBRIDPAY_DB_PATH` for volumes,
  `HYBRIDPAY_DB_MEMORY=1` for tests). Survives restarts; Modal containers stay stateless.
- `modal_backend/api.py` — `POST /api/payments/fiat` (create, idempotent) → `POST .../confirm`
  (provider-authoritative) → `GET ...` (retrieve, re-queries provider when TEST key present) →
  `.../cancel`, `.../refund`, `GET /api/payments/fiat` (list), `POST /api/webhooks/stripe`
  (HMAC-verified, idempotent ingest, the only writer of webhook-driven state).
- Frontend `Fiat sandbox` tab: create → confirm → display both states + retry only on 429/5xx.

## Lifecycle
`created` → `pending` → `succeeded` | `failed` | `unknown` (timeout: query original, never failover);
`succeeded` → `refunded`; `created|pending|unknown` → `canceled`. Terminal states never re-confirm.

## Security properties (enforced + tested)
- Test credentials only (`sk_test_*` prefix enforced; live keys refused).
- No PAN/CVV fields exist anywhere; provider-hosted collection via `client_secret` (TEST).
- Frontend state is never trusted: confirm/retrieve always go through the provider or verified webhook.
- Webhook: `t,v1` HMAC-SHA256 check + 300 s tolerance + eventId dedupe + tenant isolation.
- AI modules cannot move money (`test_ai_endpoints_cannot_move_money` asserts advisory-only + no provider imports).

## Automated tests (mocked, no network)
```
HYBRIDPAY_DB_MEMORY=1 API_SHARED_TOKEN=dev-shared-token pytest modal_backend/test_fiat_payments.py -q
# 7 passed: lifecycle, idempotency+409, cancel/refund gating, webhook valid/forged/stale/dedupe,
# AI guard, SQLite durability across reconnects
```

## Documented sandbox integration test (Stripe TEST, operator step, consumes no real funds)
Prerequisite: `modal secret create hybridpay-test STRIPE_SECRET_KEY_TEST=sk_test_... STRIPE_WEBHOOK_SECRET_TEST=whsec_...`
(or local env for the API process only — never commit).
```
API_SHARED_TOKEN=dev-shared-token STRIPE_SECRET_KEY_TEST=sk_test_... \
  uvicorn modal_backend.api:app --port 8000 &
curl -s -X POST localhost:8000/api/payments/fiat \
  -H "Content-Type: application/json" -H "X-Tenant-Id: t1" \
  -H "Authorization: Bearer dev-shared-token" -H "Idempotency-Key: sandbox-1" \
  -d '{"amountMinor":"200","currency":"EUR","instructionId":"sandbox-intent-1"}'
# -> {"paymentId":"pay-...","state":"pending","provider":"stripe-test",...,"clientSecret":"pi_..._secret_..."}
curl -s -X POST localhost:8000/api/payments/fiat/<paymentId>/confirm \
  -H "X-Tenant-Id: t1" -H "Authorization: Bearer dev-shared-token"
# -> {"state":"succeeded"|"pending"|"failed"} — value comes from PaymentIntent retrieve, not the request.
# Webhook: Stripe CLI -> `stripe listen --forward-to localhost:8000/api/webhooks/stripe`
# then trigger `payment_intent.succeeded`; re-post the same event -> {"deduped":true}.
```
Record the resulting `paymentId`, `state`, and webhook `updated` count in the demo report. Tear down with
`unset STRIPE_SECRET_KEY_TEST` — mock fallback resumes automatically.

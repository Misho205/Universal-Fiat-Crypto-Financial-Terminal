# Credentials runbook (no secrets in repo)

Copy `.env.example` to `.env`. All live keys MUST remain empty (live mode OFF enforced by `LIVE_MODE=false` guard in code).

| Var | Purpose | How to obtain | Status without it |
|---|---|---|---|
| STRIPE_SECRET_KEY_TEST | Stripe sandbox auth | Stripe Dashboard test mode | stripe-sandbox SANDBOX_BLOCKED, mock used |
| STRIPE_WEBHOOK_SECRET_TEST | Webhook verify | Stripe CLI `listen` | webhooks unverifiable -> rejected |
| BTCPAY_URL_TEST / BTCPAY_API_KEY_TEST / BTCPAY_STORE_ID_TEST | Regtest invoices | `docker compose --profile btc up`, create store + API key | btcpay SANDBOX_BLOCKED, mock used |
| OIDC_ISSUER / OIDC_CLIENT_ID / OIDC_CLIENT_SECRET | Merchant login | Auth0/Clerk sandbox tenant | fallback dev JWT (local only, never prod) |
| DATABASE_URL | Postgres | docker compose | required for api/worker |
| TEMPORAL_ADDRESS | Workflows | docker compose | required; unit tests use in-memory stub |
| OPA_URL | Policies | docker compose | fallback embedded evaluator in dev |

Live keys (`*_LIVE`) are rejected at startup when `LIVE_MODE=false`. To request sandbox access for Revolut: developer.revolut.com portal + api-requests@revolut.com. Record grant date in provider-capabilities.md. Never commit `.env`.

# Architecture

Date: 2026-10-31. Stack: TypeScript, Next.js (apps/terminal), NestJS modular monolith (apps/api), Temporal (apps/worker), PostgreSQL + Prisma migrations, OPA, OIDC (Auth0/Clerk sandbox), Docker Compose, OpenTelemetry. Redis: cache/rate-limit only. pnpm + Turborepo.

## Components
- `apps/terminal`: merchant POS + customer QR checkout, BG/EN via next-intl dictionaries. Talks only to `apps/api` via `packages/sdk`. No secrets.
- `apps/api`: NestJS modules — tenancy, devices, catalog/assets, orders, agreements, quotes, instructions, evidence, refunds/disputes, webhooks, reconcile, audit. Prisma + outbox/inbox tables. OPA decisions via `packages/policies`. Emits Temporal signals; never calls providers inline (enqueues outbox -> worker).
- `apps/worker`: Temporal workers + activities. Activities perform adapter calls (mock/stripe/btcpay) with idempotency keys, verify webhooks, reconcile UNKNOWN.
- `packages/domain`: Money (string amounts, integer minor units), AssetRegistry, CapabilityMatrix, state machines (instruction, funding, settlement), idempotency key derivation.
- `packages/agreements`: DSL types + deterministic validator, version hashing, index calculator, quote freezer.
- `packages/ledger`: journal builder (balanced per asset, FX legs via clearing accounts), invariants checker.
- `packages/policies`: Rego bundles (allow/review/deny + reason codes), versioned, evaluated server-side.
- `packages/adapters`: `PaymentAdapter` interface (collect/authorize/capture/cancel/refund/transfer/payout/recurring/conditionalRelease/exchange -> data or UNSUPPORTED_CAPABILITY), mock + stripe-sandbox + btcpay-regtest + openbanking/CASP interfaces.
- `packages/sdk`: typed fetch client for internal API + checkout token flow.

## Data flow (happy path, direct payment)
1. Cashier creates order (tenant, store, lines, denomination EUR).
2. Select agreement (fixed v1 or conditional DSL) -> price calc -> freeze index amount if indexed.
3. `GET eligible-methods` filters CapabilityMatrix by asset/route/policy.
4. `POST quotes` (executable, expiring) -> `POST instructions` (idempotent) -> outbox -> Temporal `PaymentWorkflow`.
5. Worker activity calls adapter (mock returns deterministic outcome; stripe creates PaymentIntent on connected account; btcpay creates invoice).
6. Webhook/chain poll -> inbox -> workflow advances instruction/funding/settlement states -> journal posts balanced entries -> receipt issued.

## Safety properties
- Secrets server-side only (secret manager env in prod; `.env` local). KMS envelope for sensitive columns (documented; local dev uses age-test key, NOT prod).
- External calls outside DB tx; timeout -> query original before retry; no provider failover while original may execute.
- Redis never authoritative for money; only cache/rate limits.
- OTEL traces across terminal->api->worker->adapter with redacted attributes.

## Infra (infra/docker-compose.yml)
postgres:16, temporal (auto-setup + postgres), opa (bundle from packages/policies), otel-collector, redis, btcpay-regtest profile (bitcoind regtest + btcpay). API + worker + terminal as local services.

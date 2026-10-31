# ADRs

## ADR-001 Modular monolith (2026-10-31)
Choose NestJS modular monolith + Temporal over microservices. Smallest operationally sound design; reliability via workflows, not distributed sagas.

## ADR-002 Stripe sandbox leads; Revolut distinct APIs (2026-10-31)
Stripe Connect Direct charges as leading fiat sandbox (clear docs + liability). Revolut Merchant/Business/Open Banking modeled separately. No Business API as customer-account authority.

## ADR-003 BTCPay regtest, no Lightning MVP (2026-10-31)
Greenfield v1 invoices, merchant xpub, no platform keys. Lightning UNSUPPORTED_CAPABILITY until implemented+tested.

## ADR-004 Prisma + integer money (2026-10-31)
PostgreSQL + Prisma migrations. Amounts as strings in API, BIGINT minor/atomic units in DB. No float. Balanced per asset.

## ADR-005 Temporal + outbox/inbox (2026-10-31)
External calls only in activities outside DB tx. Query-original-before-retry. No provider failover while original may execute. UNKNOWN + reconcile.

## ADR-006 OPA fail-closed policies (2026-10-31)
Versioned ALLOW/REVIEW/DENY + reason codes. Fail closed for money movement; reconciliation continues.

## ADR-007 OIDC sandbox login (2026-10-31)
Auth0/Clerk sandbox for login + MFA/passkey. Login, acceptance, provider authorization are separate artifacts.

## ADR-008 pnpm+Turborepo, PWA first (2026-10-31)
Web/PWA terminal + QR checkout (BG/EN). Native reader only when approved SDK requires. No raw NFC/EMV/PIN.

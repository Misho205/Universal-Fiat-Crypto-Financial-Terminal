# Provider capabilities (verified 2026-10-31)

Legend: MOCK_OK = working mock; SANDBOX_OK = real sandbox tested; SANDBOX_BLOCKED = needs credentials; LIVE_BLOCKED = always blocked in MVP; INTERFACE_ONLY = no execution.

CAUTION: country availability alone is not evidence for a reader/method. Each cell needs country + merchant eligibility + currency + device + SDK + operation + commercial approval.

## 1. Mock adapter — MOCK_OK
Operations: collect/authorize/capture/cancel/refund/transfer + conditionalRelease (simulated) + exchange (indicative only, never presented as executable). Scenarios: success, failure, timeout->UNKNOWN, dispute. No network.

## 2. Stripe sandbox — leading fiat adapter (docs verified 2026-10-31, https://docs.stripe.com/connect/charges)
- API: Stripe Connect v2, Direct charges (charge on connected account + application_fee to platform). SDK: stripe-node 17.x (to pin on install). Currency: EUR. Country: BG/EU connected accounts require `card_payments` capability active (to verify at onboarding).
- Supported in code: authorize, capture (within expiry), cancel, refund, transfer(payout via connected balance). Recurring: interface only. ConditionalRelease: UNSUPPORTED_CAPABILITY (no escrow product used). Exchange: UNSUPPORTED_CAPABILITY.
- Webhooks: Stripe-Signature verification; idempotent inbox.
- Status: code MOCK_OK now; SANDBOX_BLOCKED until `STRIPE_SECRET_KEY_TEST` + `STRIPE_WEBHOOK_SECRET_TEST` + Connect account provisioned (see credentials-runbook). LIVE_BLOCKED.
- Liability: Direct charges — connected account balance debited for refunds/chargebacks; application fee to platform. Destination/split documented but NOT implemented (would put liability on platform balance).

## 3. Revolut — three distinct APIs, INTERFACE_ONLY in MVP
- Merchant API (accept payments, Web SDKs, Reader/Terminal/POS per developer.revolut.com guides). Business API (manage own accounts — NOT authority over customer accounts). Open Banking API (AIS/PIS banking-app auth).
- SDKs: merchant-web/ios/android (to pin when sandbox granted). Readers require approved hardware + commercial approval; no evidence yet -> all reader capabilities LIVE_BLOCKED.
- Status: SANDBOX_BLOCKED (needs sandbox access via api-requests@revolut.com + developer portal). No endpoints fabricated. No Business API used as customer-account authority.

## 4. BTCPay Greenfield v1 regtest — MOCK_OK code, SANDBOX_BLOCKED until local stack up
- Docs: https://docs.btcpayserver.org/API/Greenfield/v1/ (verified 2026-10-31, minimal public spec page; full OpenAPI pulled from self-hosted instance at runtime).
- Config: merchant store + xpub receiving; platform stores no private keys. Invoice: amount, asset BTC, network `bitcoin-regtest`, address format bech32, confirmations policy (default 1 regtest / 2 testnet configurable), no Lightning in MVP (UNSUPPORTED_CAPABILITY).
- Statuses: invoice pending/settled/expired/invalid; chain reorg -> incident. Observation via BTCPay webhook + node; customer txid never trusted alone.
- Status: code ready; needs `BTCPAY_URL_TEST` + `BTCPAY_API_KEY_TEST` + `BTCPAY_STORE_ID_TEST` (local docker profile) to become SANDBOX_OK. LIVE_BLOCKED.

## 5. Open-banking partner / CASP converter — INTERFACE_ONLY
- `OpenBankingPartner` (PIS authorize/initiate) and `CryptoToFiatProcessor` (quote + convert + payout) interfaces defined; no execution, no fake rates. Live requires licensed partner + verified permissions + Travel Rule handling.

## Unresolved questions (blocking sandbox/live, not mock)
Q1 Stripe: BG v2 account onboarding + card_payments activation steps for test merchant. Q2 Revolut: sandbox tenant provisioning + Merchant API OAuth scopes. Q3 BTCPay: regtest faucet/mining cadence for CI. Q4 Fiscal: Bulgarian NRA receipt integration requirements (future interface only). Q5 Accounting: principal/agent confirmation for journal design.

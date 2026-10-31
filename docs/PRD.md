# HybridPay Terminal — PRD (condensed, binding for implementation)

Source: user task specification (2026-10-31). Contract denomination default: EUR. Initial market: Bulgaria / EU. Live mode: OFF.

## 1. Objective
Merchant payment terminal accepting extensible fiat + crypto methods, with deterministic conditional-payment agreement engine ("fiat smart contract"). The engine evaluates accepted conditions and submits only authorized provider operations. It does not control banks, guarantee finality, create money, or create legal escrow by itself.

## 2. Form factor
Default: merchant web/PWA terminal + customer QR checkout. Native Android/iOS integration only when an approved reader or Tap-to-Pay SDK requires it. Never implement raw card NFC/EMV/PIN handling.

## 3. Merchant flow
Create order -> select fixed or conditional agreement -> calculate price -> show eligible methods -> present QR or approved reader -> track payment -> technical receipt.

## 4. Customer flow
Verify merchant + beneficiary -> review exact contract version, conditions, fees, quote -> accept -> authorize with provider/wallet -> track status.

## 5. Receipts
A technical receipt MUST NOT be labeled a statutory fiscal receipt. Provide interface for future local fiscal/accounting integrations; no compliance claim before validation.

## 6. Money identity
- Contract denomination, payment asset, settlement asset are independent.
- EUR contract paid in BTC and settled in EUR requires an approved executable conversion route. If absent, hide/reject that route.
- Fiat asset: ISO code, exponent, jurisdictions, limits.
- Crypto asset: network/chain ID, native/token, exact token contract, decimals, address format, memo/tag, gas asset, confirmation/finality policy. Token symbol alone is never sufficient identity.
- No cross-chain bridges in MVP.

## 7. Method capabilities
`collect, authorize, capture, cancel, refund, transfer, payout, recurring, conditionalRelease, exchange`. Return `UNSUPPORTED_CAPABILITY` for unavailable ops. New assets/methods only after validation + policy review + adapter-contract tests + feature flag.

## 8. Providers
1. Mock adapter: deterministic success/failure/timeout/dispute.
2. Stripe sandbox (leading fiat sandbox): Connect Direct charges documented; Destination/split documented only. Revolut Merchant/Business/Open Banking modeled as distinct APIs/interfaces.
3. BTCPay Greenfield v1 Bitcoin regtest invoices. Merchant-controlled xpub; platform holds no merchant private keys. No Lightning in MVP.
4. Interfaces for licensed open-banking partner and CASP/crypto-to-fiat processor. No fake exchange execution.

Auth: provider-required OAuth/API keys server-side; tokenized/hosted card collection; verified webhooks. Login, agreement acceptance, payment authorization are separate artifacts.

## 9. Agreement engine
Typed allowlisted DSL only: `timeCondition, externalEvent, partyApproval, approvalThreshold, milestone, disputeWindow`. No eval. AI may draft; deterministic validator + human acceptance control executable terms.
Immutable versions, version-bound acceptance, parties, amounts, fees, beneficiaries, conditions, deadlines, cancel/refund/dispute rules, index policy, consent scope. Amendments create new versions. Beneficiary change requires step-up + independent approval in production.
Evidence: authenticated source, eventId, timestamp, expiry, replay protection. Merchant assertion alone is not conclusive.
Execution models (select one per agreement): (a) initiate after condition with valid authorization; (b) authorize now/capture later within expiry; (c) approved conditional payout/escrow product only; (d) future audited crypto escrow — disabled in MVP.
Direct wallet receipts are received funds; cannot be held/reversed by DB. No simulated escrow via platform bank account or pooled wallet.

## 10. Ledger & reliability
Separate agreement/instruction/funding/settlement/refund/dispute states. `UNKNOWN` for ambiguous outcomes. Authorization != settlement; redirect/broadcast != proof; settlement != no dispute risk.
Append-only double-entry journal, balanced per asset, integer minor/atomic units, immutable posted entries, compensating entries. FX legs via clearing accounts + recorded fees.
Atomic reservations + limits survive concurrent workers. Outbox/inbox, stable idempotency keys (tenant+operation+content), uniqueness constraints. External calls in Temporal activities outside DB tx. Reconcile after crash. No unsafe provider failover. Duplicate/out-of-order webhooks safe.
Crypto: validate asset/network/destination/amount/reference; confirmation policy, reorgs, replace/drop, doublespend, partial/late/overpayment queues. Reorg after fulfillment = incident/exposure. Never trust customer screenshots/txids alone.
Refunds: fiat via original rail; crypto = new transfer to verified recipient (MVP may emit signing request + observe). Refund denomination/amount/quote/fee policy defined. Split tender/change disabled unless implemented.

## 11. Indexation / FX / stablecoin guardrails
Fixed nominal default. Indexing opt-in for future obligations only. Formula: `raw = base * eligible_index / base_index` on comparable positive official CPI/HICP levels. Lock series, geography, base period, cutoff, revision/vintage, frequency, floor/deflation, per-adjustment cap, cumulative cap, ceiling, rounding at acceptance. Inconsistent -> REVIEW. Missing/stale/discontinuous/unapproved change pauses instruction. Executed calculations immutable with inputs.
Quotes: source, timestamp, expiry, in/out assets, fees, max debit, min out, slippage. Expired quotes refresh + re-accept if terms change. Indicative != executable.
Stablecoins: depeg thresholds, freeze risk, liquidity stops. Thresholds are test defaults, not guarantees. No autonomous invest/hedge/borrow/leverage/mint.

## 12. Security / compliance / AI
Versioned ALLOW/REVIEW/DENY + reason codes. Limits by tx/day/merchant/user/device/asset/provider; cross-currency only with approved conversion. Fail closed on money movement when auth/risk fails; reconciliation continues.
KYC/KYB, sanctions, AML, wallet-risk, Travel Rule gates with partner responsibilities documented. Least privilege, MFA, tenant isolation, encryption, short-lived creds, rotation, redacted logs, retention/deletion, tested backups (proposed RPO 5min / RTO 60min to validate).
Never collect PAN/CVV/PIN, seeds, banking passwords. Never put personal/payment data on-chain.
AI holds no credentials, signs nothing, changes no beneficiaries, authorizes no refunds, adjudicates no disputes, bypasses no policies. External evidence/text treated as untrusted.

## 13. Entities & API
Tenants, stores, devices, users/roles, assets/networks, capability versions, orders, agreement versions/acceptances, evidence, consents/mandates, quotes, instructions/attempts, provider/chain events, reservations, journal entries/lines, index observations/calculations, risk decisions, refunds, disputes, reconciliation runs, inbox/outbox, audit.
Internal OpenAPI for orders, agreements/acceptances, eligible methods, quotes, instructions/status, evidence, refunds, reconciliation. Short-lived checkout tokens. Idempotency scoped; conflicting reuse rejected.

## 14. Acceptance
Automated: balanced journals, rounding, concurrent reservations, webhooks replay/order, crash recovery, UNKNOWN/cancel races, tenant isolation, revoked device/consent, reorg/partial/overpayment/wrong-network, index caps/revisions/missing/rebasing, quote expiry/depeg, refund substitution, QR tamper, beneficiary/approval separation. E2E mock flow; real sandbox/regtest when configured. Internal p95 <500ms measured excl. provider latency. Backups + restore exercised.

## 15. Non-goals (MVP)
Live mode, custody of merchant keys, crypto escrow module, bridges, new tokens, on-chain PII, raw card handling, statutory fiscal compliance claim, blockchain anchoring (later: salted commitments only).

# Legal Review Questions — HybridPay (prototype → enterprise path)

> For qualified Bulgarian/EU counsel (financial-regulatory, data-protection,
> and AI-law). These are the points this technical audit could not resolve.
> No live activity, licence applications, or customer commitments should proceed
> on assumptions about the answers.

## Financial regulation (BNB / FSC competence)

- **L-01 — PSD2/ЗПУПС licence perimeter.** Do sandbox fiat simulations with
  Stripe TEST (no fund movement) fall outside ЗПУПС authorization? At which
  exact live function (collection, payout, PIS, AIS) is authorization
  triggered, and is PI/EMI licence vs. agent/partner-PI viable for a
  single-developer entity? Which BNB ordinances and reporting apply?
- **L-02 — MiCA CASP perimeter.** Does Sepolia-only tracking with wallet-side
  signing constitute any crypto-asset service? What is the minimal mainnet
  function that triggers CASP authorization in Bulgaria (BNB vs. КФН
  competence split), and is a partner-CASP model acceptable for transfer-only
  flows? Confirm ART/EMT non-issuance has no duties.
- **L-03 — AML obliged-person scope.** At what point (CASP, PI, or earlier —
  e.g., fiat-referenced crypto flows) does HybridPay become a ЗМИП obliged
  person? Confirm FIA (САД/Д АНС) registration, STR, and record-keeping
  expectations; confirm sanctions-screening expectations pre-licence.

## Data protection (CPDP / КЗЛД)

- **L-04 — Transfers + processors.** Are Meta (US model API), Modal (US
  hosting), Stripe, and public Sepolia RPC endpoints processors/sub-processors
  or independent controllers for in-scope data? Validate SCC/TIA approach and
  whether testnet transaction hashes linked to users are personal data.

## AI law

- **L-05 — AI Act classification.** Confirm HybridPay's role (deployer vs.
  provider) for the advisory stack; confirm whether fraud-risk scoring with a
  human-in-loop, never-auto-enforce design is high-risk under Annex III(5);
  validate Art. 50 disclosure wording (BG/EN) and GPAI-downstream documentation
  duties given Meta Muse Spark as the model.

## Digital operational resilience / security

- **L-06 — NIS2 transposition (Bulgaria).** Current transposition status and
  whether a small SaaS provider to banks could fall in scope (size-cap,
  Annex I/II); confirm expected supply-chain flow-downs.
- **L-07 — DORA customer contracting.** Required Art. 30 clause set for a
  non-EU-hosted (US Modal/Meta) ICT subcontractor chain serving EU banks;
  confirm Lead-Overseer/CTPP irrelevance at this scale.

## Tax / fiscal (merchant pilots)

- **L-08 — Fiscal receipts (NRA Ordinance H-18).** Confirm that HybridPay
  technical receipts must never resemble fiscal receipts; what integration
  (certified fiscal device/service) is required before any merchant pilot
  handling real payments.

## General instruction to counsel

For each answer, cite the controlling article/ordinance and state whether the
conclusion changes if (a) the developer incorporates, (b) hosting moves to the
EU/EEA, or (c) only software (no operated service) is supplied to banks.

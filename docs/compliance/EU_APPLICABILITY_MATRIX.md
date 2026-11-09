# EU Regulatory Applicability Matrix — HybridPay (prototype)

> Prototype assessment only. NOT legal advice. Does NOT claim compliance,
> certification, authorization, or production readiness. Where applicability is
> uncertain the entry is marked **LEGAL_REVIEW_REQUIRED** and mirrored in
> `LEGAL_REVIEW_QUESTIONS.md`. Current as of 2026-11-09; legal acts evolve —
> re-validate with qualified Bulgarian/EU counsel before any live activity.
>
> Product baseline (verified, see `docs/audit/SYSTEM_INVENTORY.md`):
> Bulgarian individual developer, no financial licence; sandbox fiat
> simulations (mock + Stripe TEST), Sepolia testnet tracking (backend never
> signs), programmable-agreement concepts, advisory AI (Meta Muse Spark),
> `LIVE_MODE=OFF` fail-closed, no custody, no real fund movement.

Status values: **Applicable** / **Conditional** (triggered by defined future
functions) / **Not applicable** / **Unknown**.

---

## 1. GDPR — Regulation (EU) 2016/679

**Status: Applicable (proportional, from first personal-data processing).**

- Official source: ELI https://eur-lex.europa.eu/eli/reg/2016/679/oj
- Triggering functions: any identified/identifiable data — tenant contact
  details, dispute filings (`disputes.py`, evidence metadata), audit logs with
  actor identifiers, IP/access logs, support correspondence, Meta-model prompts
  containing customer data. Even sandbox demos with real names/emails count.
- Relevant provisions: Art. 5 (principles), Art. 6 (lawfulness), Art. 12–22
  (data-subject rights), Art. 25 (data protection by design/default), Art. 28
  (processors), Art. 30 (records of processing), Art. 32 (security), Art. 33–34
  (breach notification 72 h / without undue delay), Art. 35 (DPIA), Art. 44–50
  (third-country transfers — Meta API / Modal US hosting), Art. 37–39 (DPO).
- Technical controls present: tenant scoping, `scrub_payload()` redaction,
  minimal stores (refs/states/amounts), hash-chained audit log.
- Organizational/legal still required: RoPA, privacy notices, DPA/SCCs with
  Meta/Modal/Stripe/Sepolia-RPC providers, retention/deletion policy, DSR
  workflows, breach playbook, DPIA for fraud-scoring/disputes.
- Missing evidence: no RoPA, no notices, no DPAs, no transfer assessment, no
  retention enforcement in code.
- External review: Bulgarian CPDP (КЗЛД) practice; EU counsel for processor mapping.

## 2. DORA — Regulation (EU) 2022/2554 (in application since 17 Jan 2025)

**Status: Not applicable directly now; Conditional as ICT third-party provider.**

- Official source: ELI https://eur-lex.europa.eu/eli/reg/2022/2554/oj
- Why not direct: HybridPay is not a financial entity (Art. 2 — credit
  institutions, payment institutions, CASPs, etc.); developer holds no licence.
- Conditional trigger: supplying the terminal/backend to EU banks/exchanges as
  an ICT third-party provider. Then the *customer financial entity* owes
  Art. 28 (ICT third-party risk management), Art. 29 (pre-contractual risk
  assessment), Art. 30 (mandatory contractual clauses: audit rights, security
  measures, incident cooperation, exit strategies), and incident reporting
  (Art. 17–19) flows through HybridPay contractually. Critical-CTPP oversight
  (Art. 31–42) is a later-stage consideration.
- Relevant now: voluntary alignment (incident classification, resilience
  testing `test_load.py`, change management) strengthens bank procurement.
- Technical controls present: `/ready` probe, audit chain, break-glass
  procedures, kill-switch, structured logging.
- Missing: DORA-grade incident playbook mapping, contractual clause pack,
  concentration/subcontractor register (Meta/Modal/Stripe chain).
- External review: financial-regulatory counsel before first bank contract.

## 3. MiCA — Regulation (EU) 2023/1114 (stablecoin titles from 30 Jun 2024; CASP regime from 30 Dec 2024)

**Status: Not applicable to current prototype; Conditional (authorization boundary).**

- Official source: ELI https://eur-lex.europa.eu/eli/reg/2023/1114/oj;
  supervision: EBA/ESMA; national authority: BNB / FSC (КФН)
  — **LEGAL_REVIEW_REQUIRED** on competent-authority split in Bulgaria.
- Why not now: no crypto-asset service provided — Sepolia testnet tracking
  only, backend never signs, no custody, no exchange, no transfer of
  crypto-assets on mainnet, no EMT/ART issuance. Testnet tokens are not
  MiCA crypto-assets in scope of a service.
- Conditional triggers (each needs CASP authorization, Art. 59–63, or a
  licence-partner model): mainnet transfer/execution (Art. 3(1)(26),
  Art. 75–76 custody/transfer services), custody of private keys, operating a
  trading platform, exchange crypto↔fiat, reception/transmission of orders.
- Relevant provisions if triggered: Art. 59 (authorization), Art. 60–63
  (passporting), Art. 66–73 (governance, safeguarding, complaints), Art. 75
  (custody), Art. 76–77 (transfers), Title IV/VI (ART/EMT — only if issuing).
- Technical controls present: chain-bound IDs, replay/double-execution
  protection, mainnet refusal, wallet-side signing only.
- Missing: CASP licence, safeguarding arrangements, complaints handling
  (disputes module is NOT a MiCA complaints procedure), own-funds, white paper
  duties (n/a unless issuing).
- External review: **mandatory** before any mainnet function — authorization
  strategy (own CASP vs. partner CASP).

## 4. PSD2 — Directive (EU) 2015/2366 + Bulgarian Payment Services and Payment Systems Act (ЗПУПС)

**Status: Not applicable to sandbox simulations; Conditional (licence boundary) for any live fiat execution.**

- Official source: ELI https://eur-lex.europa.eu/eli/dir/2015/2366/oj;
  national: ЗПУПС (BNB supervision) — **LEGAL_REVIEW_REQUIRED** on current
  consolidated text and exemptions practice.
- Why not now: mock/Stripe-TEST simulations move no funds; Annex I payment
  services (credit transfers, direct debits, payment initiation, account
  information) are not provided.
- Conditional triggers: live collection/payout, payment initiation (PIS),
  account information (AIS), issuing payment instruments → authorization as
  payment institution / e-money company (BNB), or agent/distributor model;
  safeguarding (Art. 98–100 PSD2), SCA (Commission Delegated Reg. 2018/389),
  incident reporting to BNB.
- Technical controls present: maker-checker intents, idempotency, reconciliation runs, provider-status-authoritative design.
- Missing: licence, safeguarding accounts, SCA implementation, BNB reporting.
- External review: **mandatory** before live fiat — licence vs. partner-PI strategy.

## 5. Regulation (EU) 2023/1113 — Transfer of Funds / Travel Rule (applies from 30 Dec 2024)

**Status: Not applicable now; Conditional with MiCA CASP scope.**

- Official source: ELI https://eur-lex.europa.eu/eli/reg/2023/1113/oj
- Why not now: no transfers of funds or crypto-assets (testnet only).
- Trigger: any CASP transfer service → originator/beneficiary information
  collection, verification, transmission (Art. 14–16), suspicious-transfer
  procedures, data protection (Art. 25), alignment with AML Regulation.
- Missing: full Travel-Rule data model, counterparty-CASP due diligence, secure transmission channel.
- External review: with MiCA counsel; EBA Travel-Rule guidance monitoring.

## 6. AML/CFT — EU AML package + Bulgarian ЗМИП + EU restrictive measures

**Status: Not an obliged entity now; Conditional; sanctions law applies to everyone.**

- Official sources: Regulation (EU) 2024/1624 (AML Regulation), Directive (EU)
  2024/1640 (AMLD6), Regulation (EU) 2024/1620 (AMLA); national: Закон за
  мерките срещу изпирането на пари (ЗМИП) — **LEGAL_REVIEW_REQUIRED** on
  current obliged-person scope for crypto/payment intermediaries in Bulgaria.
- Why not now: individual developer providing sandbox software is not currently
  an obliged entity (no listed activity).
- Conditional triggers: CASP authorization or payment-institution licence →
  full AML programme (risk assessment, CDD/KYC, ongoing monitoring, STRs to
  FIA–САД/Д АНС, record-keeping, compliance officer, training).
- Sanctions: EU restrictive measures (Council regulations) bind all persons;
  live product needs sanctions-screening design even before licence.
- Technical controls present: advisory fraud signals (fail-closed to `high`),
  human-review gates, audit trail — **supportive only, not an AML control**.
- Missing: everything organizational (risk assessment, KYC vendor, screening, STR workflow).
- External review: AML counsel + FIA guidance before live/KYC decisions.

## 7. EU AI Act — Regulation (EU) 2024/1689 (in force 1 Aug 2024; phased application)

**Status: Applicable in part (transparency + GPAI-deployer duties); high-risk classification: Unknown → LEGAL_REVIEW_REQUIRED.**

- Official source: ELI https://eur-lex.europa.eu/eli/reg/2024/1689/oj
- Role mapping: Meta = GPAI model provider; HybridPay = deployer (and
  downstream provider for its guardrail/validation layer) — confirm with counsel.
- Triggering functions: `fraud_signals` (fraud-risk scoring), `routing_recommendation`,
  `analyze_contract`, assistant chat, agreement-state explainer.
- Risk analysis:
  - Prohibited (Art. 5): none identified (no social scoring, no manipulative/exploitative systems, no real-time remote biometrics).
  - High-risk (Art. 6 + Annex III): fraud-scoring in financial services is the
    closest call — Annex III(5) lists creditworthiness/recourse and risk
    assessment for insurance; general fraud-prevention scoring is **not
    expressly listed**, hence **Unknown**. The `AI-scores-never-auto-enforce`
    + human-review design argues against high-risk deployment use, but this
    needs counsel confirmation.
  - Transparency (Art. 50): AI-generated content/advisory outputs shown to
    users likely trigger disclosure duties → **Applicable** (label AI output,
    already partially done via `[validated|stub]` tags).
  - GPAI downstream (Art. 53–55 chain): comply with Meta's use policies, keep
    technical documentation of the advisory system, post-market monitoring
    proportionate to a prototype.
- Technical controls present: validated/fallback envelopes, injection
  screening, allowlisted read-only tools, kill-switch, per-tenant rate limits,
  usage counters, AI audit events, human-approval gates for institutional actions.
- Missing: AI system inventory/register entry, Art. 50 disclosure wording
  review, GPAI documentation file, incident/serious-incident process,
  red-team evidence formalization (red-team tests exist — good start).
- External review: AI-regulatory counsel on (a) deployer duties, (b) fraud-score high-risk question, (c) banking-customer AI procurement clauses.

## 8. eIDAS — Regulation (EU) 910/2014 as amended by 2024/1183 (eIDAS2)

**Status: Not applicable now; Conditional.**

- Official sources: ELI https://eur-lex.europa.eu/eli/reg/2014/910/oj and
  https://eur-lex.europa.eu/eli/reg/2024/1183/oj
- Why not now: wallet sign-in (SIWE) and bearer tokens are not qualified
  electronic signatures/seals; no trust-service reliance.
- Conditional triggers: qualified signatures for agreements/approvals,
  EUDI-Wallet attribute verification for KYC, qualified timestamps for audit
  evidence (would strengthen `audit_store.py` hash chains).
- External review: only when identity roadmap is defined.

## 9. NIS2 — Directive (EU) 2022/2555

**Status: Not applicable as regulated entity at current scale; Conditional via contracts; transposition Unknown.**

- Official source: ELI https://eur-lex.europa.eu/eli/dir/2022/2555/oj
- Why not now: SaaS prototype of an individual developer is not an essential
  or important entity (Annex I/II thresholds, Art. 3); size-cap rule (Art. 2).
- Conditional: bank/exchange customers may flow down supply-chain security
  duties (Art. 21 measures, Art. 23 incident reporting support); future
  managed-service scale could change classification.
- Bulgarian transposition status: **LEGAL_REVIEW_REQUIRED**.
- Technical controls present: logging, access control, backup/migration
  discipline, incident-adjacent playbooks (break-glass, kill-switch).
- Missing: NIS2 Art. 21 measure mapping, coordinated vulnerability disclosure
  contact (`SECURITY.md` exists — verify it names a contact).

## 10. PCI DSS v4.x (contractual card-scheme standard, not EU law)

**Status: Not applicable (no cardholder data in scope).**

- Source: PCI Security Standards Council (contractual via acquirers/schemes).
- Why not: no PAN/CVV/PIN storage, processing, or transmission — provider-hosted
  collection only; Stripe Elements-style SAQ A would be the live posture, owned
  primarily by the provider with HybridPay completing SAQ A as merchant/service
  provider as applicable. EVM flows are out of PCI scope.
- Live trigger: confirm SAQ scope with acquirer/QSA; never add card fields to
  HybridPay schemas (architectural rule — keep).

---

## Cross-framework trigger table (prototype → live)

| If HybridPay adds… | Frameworks triggered | Gate |
|---|---|---|
| Live fiat collection/payout | PSD2/ЗПУПС licence, AML obliged entity, GDPR full, DORA customer clauses, NIS2 flow-down | Licence or partner PI + counsel |
| Mainnet crypto transfer/custody | MiCA CASP, TFR 2023/1113, AML obliged entity, sanctions screening | CASP authorization or partner CASP |
| Card data ingestion | PCI DSS scope explosion | Forbidden by architecture — keep provider-hosted |
| AI auto-decision on funds/access | AI Act high-risk review + financial-rights safeguards | Keep human-in-loop; counsel first |
| Qualified signatures / EUDI KYC | eIDAS trust-service duties | Trust-service provider selection |
| Bank SaaS contracts | DORA Art. 30 clauses, NIS2 flow-down, SOC-type assurance | Contract pack + audits |

*No live payment execution, fund custody, production transfers, or external
money movement is authorized by this assessment.*

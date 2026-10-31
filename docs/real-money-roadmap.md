# Real money + smart contracts — what is still needed (non-advice, requires counsel)

> BG резюме: за да тръгнат реални пари и истински smart contracts, трябва лиценз/партньор, банка/кастоди, одитиран код и одобрения. Долу е пълният списък. Сегашният билд е умишлено заключен в пясъчник.

## Real fiat money (BG/EU)
1. **License or licensed partner**: initiating/collecting for merchants is a payment service (PSD2 / Закон за платежните услуги). Either become a licensed PI/EMI agent or run exclusively through Stripe Connect / licensed open-banking PIS (execution stays with the licensed entity; our DB never settles).
2. **Live provider onboarding**: Stripe live account + `card_payments` capability per connected account (BG/EU), webhook signing live secret, 3DS/SCA handling, dispute/chargeback ops runbook with named owner.
3. **Safeguarding**: no pooled wallets, no platform escrow simulation. Merchant funds go to merchant-owned accounts (e.g. Stripe connected balance); platform holds only its fee. If custody is ever needed → EMI safeguarding + reconciliation + audit.
4. **KYC/KYB + sanctions/AML**: identity verification, sanctions lists, transaction monitoring, Travel Rule for crypto legs, SAR process, data retention/deletion (GDPR).
5. **Fiscal**: NRA Ordinance H-18 integration — our "technical receipt" is NOT a fiscal receipt; a certified fiscal device/service must issue the fiscal bon.
6. **Ops**: independent security review, pen-test, incident runbook, 24/7 on-call, backups tested (RPO 5 min / RTO 60 min), insurance, DPA with processors.

## Real crypto (beyond regtest)
1. Mainnet/testnet node or provider (not regtest), confirmation policy per asset, reorg/double-spend handling, address-format validation per network, no bridges in MVP.
2. **CASP partner** for any fiat↔crypto conversion (MiCA): quotes with source/expiry, depeg/freeze guards, Travel Rule (Regulation 2023/1113) data exchange. No autonomous exchange execution.
3. Key management: merchant self-custody (xpub) or HSM/MPC custodian — platform never holds merchant private keys.

## Smart contracts (programmable money)
Two tracks (both require audit):
- **Off-chain conditional engine (this repo's "fiat smart contract")**: deterministic DSL validator (`timeCondition, externalEvent, partyApproval, approvalThreshold, milestone, disputeWindow`), versioned agreements + human acceptance, evidence from authenticated oracles. Can go live first — no chain needed.
- **On-chain smart contracts** (future): Solidity/Vyper contracts for escrow/split, audited by independent firm, formal verification of money invariants, bug bounty, upgradeability via proxy with timelock + multisig, mainnet deployment runbook, monitoring + pause authority. Estimated: audit 4–8 weeks + remediation; do NOT deploy unaudited contracts with real value.

## Suggested order
1. Live fiat via Stripe Connect Direct (licensed rails) → 2. fiscal + KYC/AML ops → 3. BTC mainnet receiving (self-custody) → 4. CASP conversion → 5. audited on-chain contracts.

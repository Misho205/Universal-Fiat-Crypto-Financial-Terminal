# Regulatory boundaries (BG/EU, non-advice — requires counsel review)

- Payment services (PSD2/Zakon za platezhnite uslugi): initiating/collecting on behalf of merchants may qualify as payment service; using Stripe Connect / licensed open-banking partner keeps e-money execution with licensed entity. Our DB never substitutes settlement.
- E-money/custody: no pooled wallets, no platform bank-account escrow simulation. Holding customer funds would trigger licensing + safeguarding. Architecture is non-custodial by design but that alone does not remove obligations (activity-level assessment required per flow).
- Crypto (MiCA, effective 2024-2026): BTCPay self-custody merchant receiving is software provision, not CASP custody; any conversion to fiat requires approved CASP with Travel Rule (Regulation 2023/1113) handling. No exchange execution without partner.
- AML/KYC/KYB, sanctions, wallet-risk screening gates before payout; partner responsibilities in runbooks.
- Fiscal: Bulgarian NRA Ordinance H-18 / POS receipt rules — our "technical receipt" is explicitly NOT a fiscal receipt. Future integration interface only.
- Data: GDPR minimization, retention/deletion policy, no personal/payment data on-chain. Future anchoring stores salted hashes only.
- AI: drafts only; deterministic validator + human acceptance authoritative.
- Live release gates: verified provider permissions + operating model + independent security review + operational approval. Sandbox work does not request live approvals.

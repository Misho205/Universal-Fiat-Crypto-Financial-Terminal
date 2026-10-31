# Threat model (STRIDE, condensed)

Scope: merchant terminal, QR checkout, api, worker, adapters, webhooks, chain observer.

| # | Threat | Mitigation | Test |
|---|---|---|---|
| T1 | Tampered QR (beneficiary/amount swap) | Signed checkout token (short-lived JWT, aud=tenant+order+agreementVersion+amount); customer UI shows merchant+beneficiary; verify signature server-side | tampered QR rejected |
| T2 | Beneficiary change fraud | Requires step-up auth + independent approver; new agreement version + re-acceptance; audit | approval separation test |
| T3 | Webhook forgery/replay | Provider signature verify (Stripe-Signature / BTCPay HMAC); eventId uniqueness (inbox); reject stale/expired | duplicate/out-of-order/replay |
| T4 | Tenant escape (cross-tenant read/write) | Tenant id in every query (Prisma middleware + RLS-ready schema); object-level checks; file paths tenant-prefixed | tenant isolation tests |
| T5 | Revoked device/consent reuse | Device credential revocation list checked on each instruction; consent scope+expiry checked by validator | revoked device/consent denied |
| T6 | Double-spend / wrong-network crypto | Asset+network+address validation; confirmation policy; reorg handling as incident; address format per network | reorg/partial/overpayment/wrong-network |
| T7 | Refund address substitution | Crypto refund = new transfer to KYC-verified recipient, independent approval; never auto-refund to sender | refund substitution test |
| T8 | Privilege escalation (cashier -> finance) | RBAC roles; OPA policy versioned; MFA for finance/approver | RBAC tests |
| T9 | PAN/CVV/seed collection | Never collected; hosted/tokenized only; secret scanning in CI | static check + review |
| T10 | AI prompt injection via evidence/contract text | Evidence treated untrusted; allowlist DSL, no eval; AI draft never executable without validator+human accept | injection fixtures rejected |
| T11 | Clock skew / quote abuse | Quote expiry enforced; refresh + re-accept on change; monotonic workflow timers | quote expiry test |
| T12 | Concurrent overspend | Atomic reservations (DB constraints + serializable section); aggregate limit checks | concurrency tests |

Residual risks: live PSP liability, custody/regulatory qualification, fiscal compliance — all require independent review; live remains OFF. Logs redact PII/payment data. Backups encrypted; restore drill required before pilot.

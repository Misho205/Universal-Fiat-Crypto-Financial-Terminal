# Regulatory Gap Register — HybridPay (prototype)

> Companion to `EU_APPLICABILITY_MATRIX.md`. Each gap: owner class
> (Technical / Organizational / Legal), severity for enterprise readiness
> (not a compliance verdict), and the evidence that would close it.
> Nothing here constitutes legal compliance or production clearance.

| ID | Framework | Gap | Type | Severity | Current state (verified) | Evidence to close |
|---|---|---|---|---|---|---|
| G-01 | GDPR | No Records of Processing (Art. 30) | Org/Legal | HIGH | No RoPA found in repo | RoPA covering tenants, disputes, logs, AI prompts |
| G-02 | GDPR | No privacy notices / lawful-basis mapping | Org/Legal | HIGH | None found | Public notices + Art. 6 mapping per processing purpose |
| G-03 | GDPR | No processor DPAs / transfer assessments (Meta US, Modal US, Stripe, RPC) | Legal | HIGH | No DPA/SCC evidence | Signed DPAs + Art. 44–49 TIAs |
| G-04 | GDPR | No retention/deletion enforcement | Tech+Org | MEDIUM | Retention noted as roadmap only | Retention config + purge jobs + tests |
| G-05 | GDPR | No DSR workflow (access/erasure/portability) | Tech+Org | MEDIUM | Disputes module exists but is not a DSR flow | DSR procedure + tooling + SLA tracking |
| G-06 | GDPR | No breach notification playbook (72 h) | Org | MEDIUM | Incident-adjacent docs exist (break-glass, kill-switch) | Breach runbook with CPDP/supervisor timelines |
| G-07 | GDPR | No DPIA for fraud-scoring / disputes / AI | Org/Legal | MEDIUM | None found | DPIA file(s), review cadence |
| G-08 | DORA | No ICT-subcontractor chain register (Meta/Modal/Stripe/RPC) | Org | MEDIUM | Vendors scattered across docs | Vendor inventory + concentration view |
| G-09 | DORA | No DORA Art. 30 clause pack for bank customers | Legal | MEDIUM | Bank guide exists, no clauses | Counsel-drafted ICT contract schedule |
| G-10 | DORA | Incident classification not mapped to DORA taxonomy | Org | LOW | `test_load.py`, logging present | Mapping annex in incident playbook |
| G-11 | MiCA | No CASP authorization strategy | Legal | HIGH (if mainnet) | Correctly absent now; testnet-only verified | Board decision: own-CASP vs partner-CASP (pre-mainnet gate) |
| G-12 | MiCA | Disputes module ≠ MiCA complaints-handling procedure | Org/Legal | MEDIUM | `DISPUTE_HANDLING_POLICY.md` exists | Gap analysis vs Art. 71 complaint duties |
| G-13 | PSD2/ЗПУПС | No licence strategy for live fiat | Legal | HIGH (if live fiat) | Correctly absent now; sandbox verified | BNB counsel opinion: PI/EMI vs agent/partner |
| G-14 | TFR 2023/1113 | No Travel-Rule data model / counterparty diligence | Tech+Org | MEDIUM (if CASP) | N/A now | Design gated on CASP decision |
| G-15 | AML | No AML programme (risk assessment, CDD, monitoring, STR) | Org/Legal | HIGH (if obliged) | Advisory fraud signals only (correct scope) | Full programme pre-licence; sanctions-screening design earlier |
| G-16 | AML | Sanctions-screening design missing for live roadmap | Tech+Org | MEDIUM | None | Screening point design + vendor selection |
| G-17 | AI Act | No AI system inventory / technical documentation file | Tech+Org | MEDIUM | Guardrails + red-team tests exist (good base) | Inventory entry + Art. 53–55 downstream file |
| G-18 | AI Act | Art. 50 transparency wording unreviewed | Legal | MEDIUM | `[validated\|stub]` tags present | Counsel-approved disclosure strings (BG/EN) |
| G-19 | AI Act | High-risk classification of fraud-scoring unresolved | Legal | HIGH | Human-in-loop design present | Formal counsel opinion (see L-03) |
| G-20 | eIDAS | No trust-service / EUDI roadmap decision | Org | LOW | N/A now | Decision record when identity scope defined |
| G-21 | NIS2 | No Art. 21 measure mapping; BG transposition unchecked | Org/Legal | LOW | `SECURITY.md` exists | Mapping annex + transposition check (see L-05) |
| G-22 | PCI DSS | Live SAQ scope unconfirmed with acquirer | Org | LOW | In-scope data correctly absent | Acquirer/QSA scoping note pre-live |
| G-23 | Cross | Fiscal-receipt boundary (technical ≠ fiscal receipt, NRA Ordinance H-18) | Legal | MEDIUM | Correct disclaimer in README | Counsel + NRA-practice note before merchant pilots (see L-06) |
| G-24 | Cross | `dev-caller` bypass + header-tenant trust reachable if misdeployed | Tech | HIGH | Local-only by code; deployment-gated | Startup guard: refuse production without token bindings (Phase 4 candidate) |

Closure rule: a gap closes only on merged evidence (doc + code/test where
technical), never on prose alone. Re-audit after each closure.

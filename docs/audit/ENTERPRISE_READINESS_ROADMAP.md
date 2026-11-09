# Enterprise Readiness Roadmap — HybridPay (prototype → financial-sector supplier)

> Defensible path, not a promise. Ordered by risk; each gate states its
> evidence. NOT IMPLEMENTED unless linked to a merged artifact on this branch.

## Gate 0 — Done on this branch (IMPLEMENTED / VERIFIED)
- H-01 NestJS CORS allow-list, H-02 rate limiter, M-05 canonical idempotency,
  M-06 tokenless warning, postcss/multer overrides (10→5 audit vulns).
- 222 backend + 8 api + 43 terminal tests green; E2E mock flow OK; SBOM (python).
- Deliverables: inventory, EU matrix, gap register (24), legal questions (8),
  findings, changelog, scaffolds, vendor flows, this roadmap.

## Gate 1 — Legal strategy (REQUIRES EXTERNAL REVIEW, blocks all live work)
1. Counsel opinions L-01…L-08 (`docs/compliance/LEGAL_REVIEW_QUESTIONS.md`).
2. Licence decision: partner-PI/CASP vs. own authorization; BNB/FSC pre-filing meeting.
3. Corporate form: single-developer entity cannot hold PI/CASP duties (own funds,
   governance, compliance officer) — incorporate + staff or partner.

## Gate 2 — Security hardening (before any shared deployment)
1. `CORS_ORIGINS` + `ALLOWED_ORIGINS` set to exact origins; `TENANT_FOR_*_TOKEN`
   mandatory; rotate `API_*_TOKEN` (≥32 B, secret manager).
2. `RATE_LIMIT_PER_MIN` 300–600 + Modal concurrency caps + edge WAF; re-run load tests.
3. FastAPI/starlette image upgrade (M-01) + pytest 9.x with Modal image rebuild.
4. Vitest 4.x migration (M-03); webhook signature-as-authentication decision (M-04,
   needs approval); startup refusal (not warning) when `PROD=1` without bindings.
5. CI: `.github/workflows/security.yml` (pytest, vitest, pip-audit, pnpm audit,
   CycloneDX SBOMs, secret scan) failing on new critical/high.
6. Independent penetration test + code review by qualified firm (NOT a substitute:
   this audit is internal).

## Gate 3 — Data protection + consumer trust (before personal-data scale-up)
G-01…G-07, G-23: RoPA, notices, DPAs/SCCs+TIA, retention enforcement, DSR
workflow, breach runbook, DPIA, fiscal-receipt counsel note (NRA H-18).

## Gate 4 — Financial-crime + prudential (with licence track)
G-11…G-16: CASP/PI authorization, AML programme (CDD, monitoring, STR, training),
sanctions screening, Travel-Rule data model, MiCA complaints procedure,
safeguarding accounts, SCA, BNB reporting.

## Gate 5 — Bank procurement (DORA/NIS2/AI)
G-08…G-10, G-17…G-19, G-21: subcontractor register, Art. 30 clause pack,
incident-mapping annex, AI inventory + Art. 50 wording + fraud-score counsel
opinion, NIS2 mapping, SOC 2 Type II / ISO 27001 certification path (12–18 mo).

## Stop conditions (do not proceed if)
- Counsel has not answered L-01…L-08. No live funds, custody, mainnet, or card
  data before Gate 1. `LIVE_MODE` stays OFF; no production deploys from this branch.

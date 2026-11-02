# Financial Rights Protection Policy — Universal Hybrid Payment Terminal

Status: sandbox only. No real money movement. No production enforcement.
Last updated: 2026-11-02 (UTC). Implementation: `modal_backend/financial_rights/`.

## 1. Mission

Protect users and institutions against arbitrary, unauthorized, discriminatory,
or disproportionate interference with lawful financial activity — while
preserving every lawful compliance power (AML/CFT, sanctions, court orders,
regulator mandates).

## 2. What the engine guarantees (enforced in code, not just written here)

1. **Explicit grounds.** Every sensitive account restriction carries a known
   `category` + `ground` pair (`modal_backend/financial_rights/models.py`).
   Unknown grounds are rejected (default-deny).
   Categories: `voluntary_control`, `fraud_prevention`, `contractual`,
   `legal_order`, `regulatory_obligation`.
2. **Category distinction.** A ground belongs to exactly one category
   (`GROUND_CATEGORY`). Fraud holds cannot be filed as legal orders and
   vice versa — the engine rejects miscategorized restrictions.
3. **Mandatory reason codes + evidence.** The `reasonCode` must come from the
   allowlist and match the ground; at least one non-AI evidence reference is
   required. Free text is stored for humans but never substitutes for a code.
4. **Authorization + proportionality.** The authorizer role must be eligible
   for the category; `full_freeze` (most restrictive) needs a named
   independent human reviewer + elevated written justification outside
   legal/fraud contexts. Least-restrictive means is the rule:
   `spend_limit` < `instrument_hold` < `outbound_freeze` < `full_freeze`.
5. **Time limits + review deadlines.** `expiresAt` must be future-dated and
   within the jurisdiction/category maximum (fraud holds: 72h default);
   `reviewAt` must be set no later than expiry. No restriction without a
   review deadline. `check_expiry()` reports `active` / `review_due` / `expired`.
6. **Independent review.** Appeal decisions and AI-assisted restrictions
   require a reviewer independent of the original authorizer (enforced by
   identity comparison + credential binding at the API layer).
7. **Notification when permitted.** Customers are notified unless disclosure
   is prohibited by law (`SANCTIONS` / `AML_CTF` / `COURT_ORDER` with a gag
   order → `withheld_by_law`, still fully audited).
8. **Appeals.** Any customer may appeal; see `CUSTOMER_APPEALS_SPEC.md`.
9. **Correction + restoration.** Overturned restrictions trigger a correction
   plan (lift, re-evaluate queued operations, verify no balance was altered,
   notify when permitted) + restoration steps. History is append-only —
   corrections are new entries, never rewrites.
10. **AI scores never auto-enforce.** An AI risk score alone cannot justify a
    restriction; when a score contributed, a named independent human reviewer
    + independent non-AI evidence are mandatory. The monitor flags
    `AI_SCORE_ONLY` records as suspected bypass attempts.
11. **No unauthorized transfers / balance manipulation.** The engine
    authorizes *procedure only*. It holds no balances, initiates no transfers,
    and its records carry no balance mutations. Money moves exclusively via
    provider-mediated paths with authoritative provider status.
12. **Configurable jurisdictions.** Profiles in `jurisdictions.py`
    (`EU_GENERIC`, `BG`) set durations and review cadence. **Enabling a
    jurisdiction for enforcement requires a recorded qualified legal review**
    (reviewer + date + memo) — `require_legal_review()` fails closed without
    it. Profiles encode procedure, never conclusive legal interpretation.
13. **Privacy-preserving audit.** Restrictions, appeals, and PDP decisions are
    tenant-scoped, hash-chained where applicable, and store references —
    not personal-data payloads. Data minimization is structural.
14. **Abuse monitoring.** `monitoring.detect_abuse_patterns()` flags
    `HIGH_VOLUME_AUTHORIZER`, `HIGH_OVERTURN_RATE`, `AI_SCORE_ONLY`,
    `REPEATED_SUBJECT_TARGETING`, `MISSING_REVIEW` for human review. The
    monitor never auto-punishes.
15. **Automated tests.** `test_financial_rights.py` (engine, 15 tests),
    `test_rights_api.py` (HTTP + independence + gates), `test_pdp.py`
    (central policy), `test_agreement_guardrails.py` (adversarial).

## 3. Explicit non-goals (will not be built)

- No universal prohibition of lawful AML/CFT measures, sanctions, court
  orders, or legally mandated restrictions — they remain available with full
  audit (`legalOrderSurvives` obligation).
- No automatic disclosure when prohibited by law.
- No bypasses for legally required compliance checks.
- No claim to determine legal rights conclusively (by AI or otherwise).
  The engine enforces *procedure*; legal interpretation stays with qualified
  humans. Production use requires legal review per jurisdiction.

## 4. API surface (all tenant-scoped, server-authorized)

- `POST /api/rights/restrictions` (operator+) — create (engine + PDP gated)
- `GET /api/rights/restrictions` — list with live expiry status
- `POST /api/rights/restrictions/{id}/lift` (admin, intent-gated) — lift
- `POST /api/rights/appeals` — file appeal
- `POST /api/rights/appeals/{id}/review` — assign independent reviewer
- `POST /api/rights/appeals/{id}/decide` (PDP `appeal.decide`) — uphold/overturn
- `POST /api/rights/jurisdictions/{id}/legal-review` (admin) — record review
- `GET /api/rights/jurisdictions` — profiles + review status
- `GET /api/rights/monitoring/abuse-signals` (admin) — abuse findings
- `GET /api/pdp/decisions` (admin) — decision audit; `POST /api/pdp/simulate`
  — dry-run; `GET /api/pdp/policy-version` — pinned bundle version

Tests: `API_SHARED_TOKEN=dev-shared-token API_ADMIN_TOKEN=dev-admin-token
pytest modal_backend/test_financial_rights.py modal_backend/test_rights_api.py
modal_backend/test_pdp.py -q` → 15 + 6 + 12 green.

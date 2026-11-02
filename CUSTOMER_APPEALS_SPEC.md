# Customer Appeals Specification — Financial Rights Engine

Status: sandbox only. Implementation: `modal_backend/financial_rights/appeals.py`,
routes in `modal_backend/rights_api.py`. Tests: `test_rights_api.py`,
`test_financial_rights.py`.

## 1. Who may appeal

Any authenticated customer may appeal a restriction on their own account
(`POST /api/rights/appeals` with `restrictionId`, `appellant`, `groundsText`,
optional `contact`). Filing is free, requires no reviewer, and is audited.
Cross-tenant appeals are impossible: the restriction must exist in the
caller's tenant.

## 2. States and transitions

```
submitted -> under_review -> upheld | overturned | escalated
escalated -> under_review -> upheld | overturned
overturned -> corrected -> restored -> closed
upheld -> closed | escalated
```

- `under_review` requires naming an independent reviewer.
- A decision requires: `decision` ∈ {upheld, overturned}, a written `reason`,
  and a `reviewer` independent of the original authorizer (else 422).
- `escalated` is available after a decision or when `reviewAt` was breached.

## 3. Correction (overturned restrictions)

`decide` with `overturned` automatically:
1. Lifts the restriction (state → `lifted`, `liftedBy` = reviewer).
2. Returns a `correctionPlan`:
   - lift restriction (append-only audit entry),
   - re-evaluate queued operations blocked by the restriction,
   - verify no balance was altered by the restriction itself,
   - notify the customer (or record `withheld by law` + legal basis),
   - schedule a post-correction review of the authorizer's pattern.
3. Returns `restoration` steps: confirm lift, confirm lawful operations
   resume, close with a written outcome (when permitted), retain the
   tamper-evident trail (no history rewrite).

## 4. Notification rules

- Customers are told the outcome in plain language when legally permitted.
- Under gag orders / tipping-off prohibitions, the outcome is recorded
  internally with the legal basis; nothing is disclosed to the customer.
- The engine never reveals other customers' data, provider secrets, or
  detection tactics in appeal responses (generic fraud wording only).

## 5. Worked example (sandbox)

```
POST /api/rights/restrictions            -> {restrictionId: rst-abc, ...}
POST /api/rights/appeals                 -> {appealId: apl-xyz, state: submitted}
POST /api/rights/appeals/apl-xyz/review  -> {state: under_review}
POST /api/rights/appeals/apl-xyz/decide
  {"decision":"overturned","reason":"no evidence","reviewer":"rev-9"}
-> {decision: overturned, correctionPlan: [...], restoration: [...]}
GET /api/rights/restrictions             -> rst-abc state: lifted
```

## 6. Non-goals

- Appeals do not decide legal rights conclusively; they correct procedure
  and restore access. Disputed legal questions go to qualified humans /
  competent authorities, never to AI verdicts.
- Filing an appeal never pauses a lawful legal-order restriction without an
  independent review decision and (where required) authority clearance.

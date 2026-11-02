# Restriction Review Workflow — Financial Rights Engine

Status: sandbox only. Implementation: `modal_backend/financial_rights/engine.py`,
`appeals.py`, `monitoring.py`, routes in `modal_backend/rights_api.py`.

## 1. Lifecycle

```
proposed -> (engine authorize) -> active -> review_due -> expired
   |                                |           |
   | deny                           | appeal    | appeal
   v                                v           v
(dead, reason kept)        under_review -> upheld | overturned
                                           |           |
                                     closed/escalated  corrected -> restored -> closed
```

- `proposed`: built by `new_restriction()`; unauthorized until
  `authorize_restriction()` returns ALLOW.
- `active`: authorized, within `expiresAt`, before `reviewAt`.
- `review_due`: `reviewAt` passed, `expiresAt` not yet — a human review is
  overdue (`MISSING_REVIEW` signal if unhandled).
- `expired`: `expiresAt` passed — the restriction ceases to authorize any
  interference. Legal-order records survive as *history*, never as silent
  auto-renewal (`NO_SILENT_EXPIRY`).

## 2. Mandatory gates (in order)

1. Tenant + subject present (tenant-scoped, no global restrictions).
2. Known category; ground belongs to that category.
3. Allowlisted reason code matching the ground.
4. Eligible authorizer role (`AUTHORIZER_ROLES`); voluntary controls need a
   `customer-request`/`user-consent` evidence cite unless filed by the
   customer directly.
5. Non-empty evidence; AI score alone rejected.
6. Proportionality: `full_freeze` needs a named independent reviewer (+
   written justification outside legal/fraud contexts).
7. `expiresAt` future + within jurisdiction/category max; `reviewAt` set and
   ≤ `expiresAt`; legal orders need `legalRef`.
8. AI contributed → independent human reviewer (≠ authorizer) + non-AI evidence.
9. Obligations emitted: `notifyCustomer` (or `withheld_by_law`),
   `scheduleReview`, `audit`, plus `independentReviewRequired` for
   legal/regulatory categories.

## 3. Independent review

- Reviewer roles per category (`REVIEWER_ROLES`); the reviewer must differ
  from the authorizer (string inequality + same-credential binding at the
  API layer via `_actor_key`-style checks in the institutional module).
- Appeal decisions (`appeal.decide` PDP action) require step-up and an
  independent reviewer; `reviewer == authorizer` is a 422.
- Emergency grants substitute for intents only when fresh, and always add a
  `retrospective-review` obligation.

## 4. Expiration and renewal

- Expiry is automatic and safe: an `expired` restriction authorizes nothing.
- Renewal = a NEW restriction record with fresh grounds/evidence/review —
  never a silent extension. The audit trail shows the full chain.

## 5. Monitoring (human review, never auto-punishment)

`GET /api/rights/monitoring/abuse-signals` (admin) surfaces:
`HIGH_VOLUME_AUTHORIZER`, `HIGH_OVERTURN_RATE`, `AI_SCORE_ONLY`,
`REPEATED_SUBJECT_TARGETING`, `MISSING_REVIEW`. Thresholds are parameters
with sandbox defaults; see `monitoring.detect_abuse_patterns()`.

## 6. How to run a review (operator checklist)

1. `GET /api/rights/restrictions?state=` — find `review_due` items.
2. Re-verify grounds + evidence (fresh, not copy-pasted).
3. Decide: lift (`POST .../lift`), keep with a NEW record, or escalate.
4. Appeals: `POST .../appeals/{id}/review` → assign independent reviewer →
   `POST .../decide` with written reason.
5. Overturned → run the `correctionPlan` from the response, then confirm
   `restored` via the restoration steps.

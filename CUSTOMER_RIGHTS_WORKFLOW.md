# Customer Rights Workflow — disputes, restrictions, appeals

Status: sandbox only. This document is the customer-facing companion to
`DISPUTE_HANDLING_POLICY.md` (process), `FINANCIAL_RIGHTS_POLICY.md`
(restriction rights), and `CUSTOMER_APPEALS_SPEC.md` (restriction appeals).

## 1. Your rights in this sandbox demo

- File a dispute about any payment, fee, record, restriction, or agreement
  from Personal Workspace → Disputes (you need only your customer ID and the
  payment/case reference).
- Track status any time; every state carries a plain-language explanation.
- Receive a reasoned outcome within the published SLA (7–30 days by category).
- Escalate to an independent reviewer; the person who made the contested
  decision can never be its sole reviewer.
- AI scores and recommendations never decide your case — a named human
  reviewer with a documented non-AI basis always does.
- Appeal account restrictions separately (see `CUSTOMER_APPEALS_SPEC.md`);
  lawful restrictions (sanctions/court/AML with gag orders) get generic
  wording instead of detail, by law.

## 2. Step by step

1. Personal → Disputes → enter customer ID → Track my cases.
2. File: category → link (pay-/rst-/pag- reference) → describe what happened.
3. Optional: attach evidence metadata (PDF/PNG/JPG/TXT/CSV ≤ 10 MB + sha256).
4. Wait for review; check Details for the outcome and the SLA deadline.
5. If upheld: remediation is proposed (corrections/restriction changes;
   refunds need a separate explicit approval — never automatic, never instant).
6. If rejected: the reason is stated; escalation to an independent reviewer
   is available.

## 3. What we cannot do

Reverse a payment unilaterally, refund automatically, disclose details
blocked by law, decide by AI, or delete the case history. The audit trail is
retained and tamper-evident — corrections are new entries, never rewrites.

## 4. Accessibility

Status text never relies on color alone (icon + text badges); all actions
are keyboard reachable; `aria-live` announces filing/decision results;
screens follow the same shell, contrast, and focus-visible rules as the rest
of the terminal (see `UX_AUDIT.md`, `FRONTEND_TEST_REPORT.md`).

# Dispute Handling Policy

Status: sandbox only. Implementation: `modal_backend/disputes.py`,
`modal_backend/dispute_api.py`, migration `007_breakglass_ai_disputes.sql`,
UI: Personal "Disputes" tab + Banking "Disputes" review (`DisputesPanel.tsx`,
`disputes.ts`, SDK methods). Tests: `modal_backend/test_disputes.py` (8/8),
frontend `test/disputes.test.ts` (3/3).

## 1. Scope & principles

Customers dispute unauthorized payments, incorrect records, disputed fees,
account restrictions, and contractual disagreements. Every case gets a unique
ID (`dsp-*`), links to the underlying transaction/restriction/agreement, a
visible status, and a reasoned outcome when legally permitted. Filing a
dispute creates NO automatic right to reversal and triggers NO automatic
refund: remediation that moves money executes only through cryptographic
approval bindings with explicit maker-checker approval.

## 2. Intake & abuse prevention

Required: customer identity, allowlisted category, description, at least one
link. Guards: 5 cases/customer/day, duplicate-open-case 409, 10 MB evidence
cap, MIME/extension allowlist, filename sanitization, sha256 receipt.
Evidence uploads store METADATA ONLY in sandbox; the scan verdict is a
`pending-human-review` stub — production MUST AV-scan bytes (ClamAV/AV
engine) before any reviewer opens the file.

## 3. Review & decision

States: submitted → under_review → decided → remediation → closed (escalated
branch available). Reviewer must be independent of the filer; the decider
must be independent of the original decision-maker; AI output can never be
the sole basis (named human reviewer + non-AI basis note required).
Reasoned decisions are disclosed unless a linked legal restriction imposes a
gag order (generic wording + audit instead).

## 4. Remediation & closure

`remediationPlan` proposes correction/restriction-narrowing/refund-proposal
paths; refund proposals route to approval bindings (quorum + step-up).
Closure requires a prior decision + reason + audit; silent closes and deletes
are impossible (no DELETE route; close-without-decision is 409).

## 5. Confidentiality & jurisdiction

Tenant isolation, data minimization (references over payloads), redacted
audit, gag-aware outcomes. Per-category SLAs (restriction: 7 days;
unauthorized payment: 15; others: 30) are configurable policies that require
qualified legal review before enforcement (`jurisdictions` gate); AML/CFT
confidentiality and sanctions obligations are preserved end to end.

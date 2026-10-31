# Programmable fiat payment contracts — architecture + limitations

> Deterministic conditional-payment engine for sandbox fiat. NOT escrow, NOT custody,
> NOT a guarantee. Every response carries the disclosure; the engine cannot hold funds.

## Architecture
```
terms (JSON, allowlisted) → validate_creation (pure, rejects AI bypass)
  → draft → activate (creator) → conditions_pending
  → evidence (authenticated sources only) + approvals
  → eligible_for_execution (deterministic evaluate_all, system)
  → execute (human executor + sandbox fiat provider) → completed
  cancel / dispute / expiry (role-checked) branch off at any pre-terminal state
```
- `modal_backend/programmable.py`: validators, pure evaluators per condition type,
  role-gated transitions (`can_transition`), hash-chained audit log (`prevHash` + `verify_chain`).
- `modal_backend/db.py` (`contract_agreements`): durable JSON documents; history is append-only.
- Execution path: eligibility (deterministic) AND explicit human `executor` authorization AND
  sandbox provider call (`get_fiat_provider().create/confirm`). Eligibility alone never pays.

## Condition types
- `timeCondition` (`notBefore`/`notAfter` vs server time).
- `deliveryConfirmation` (`deliveryRef` + `confirmedByAuthenticatedSource: true` evidence).
- `partyApproval` (named party in approvals list) / `approvalThreshold` (m-of-n).
- `externalEvent` (`source` + `eventId`, must arrive as `authenticated` with optional expiry).
- Anything else → `disallowed condition` (this is what stops AI-generated conditions).

## Limitations (by design)
1. Not a regulated escrow service; no reservation/holding/guarantee is ever claimed.
2. Settlement is never simulated: execution reports the provider's answer; `completed` means
   "provider confirmed in sandbox", not "money moved in the real world".
3. No custody / no money transmission: the backend moves no funds between accounts.
4. Time source is server clock; oracle evidence is trusted only when the submitter
   authenticated the source (enforced 422 otherwise, replay-safe via payment-scoped storage).
5. On-chain smart contracts are a separate future track (see `docs/real-money-roadmap.md`).

## Verification
`pytest modal_backend/test_programmable_contracts.py -q` (5 passed):
allowlist/bypass rejection, full lifecycle with roles + audit chain, all condition types,
dispute freeze, expiry block, evaluator units + tamper detection.
Frontend: Agreements tab (create → activate → approve/evidence → execute) + mocked E2E in
`apps/terminal/test/demo-flow.test.ts`.

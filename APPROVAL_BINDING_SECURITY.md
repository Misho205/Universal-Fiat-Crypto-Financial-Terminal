# Cryptographic Approval Binding — Security Design

Implementation: `modal_backend/approval_binding.py`, `modal_backend/approval_api.py`,
migration `006_approval_audit.sql`, enforcement in `modal_backend/api.py`
(`_binding_enforce`). Tests: `test_approval_binding.py` (11).

## 1. Canonical operation (version `ab-v1`)

Fixed field order, fixed types, JSON `sort_keys` + compact separators:

```
version | op_id | tenant | op_type | target_id | initiator |
counterparty | amount_minor | currency | contract_version |
terms_hash | expires_at | nonce
```

Covered op types: `fiat.cancel/refund`, `agreement.execute/amend/cancel/dispute`,
`restriction.create/lift`. Unknown types rejected (default-deny).

## 2. Digest & binding

`op_digest = SHA-256(canonical)`. Approvals reference ONLY the digest.
UNIQUE(tenant, op_digest): the same canonical op cannot be approved twice;
any parameter change yields a new digest (old approvals invalid by
construction — no "edit after approval"). Tenant/op-type are canonical, so
cross-tenant and cross-type replays find no binding.

## 3. Authorization

- Maker-checker: maker files the binding; a distinct checker approves
  (identity AND `credId = sha256(bearer)` — alt-account resistant; raw
  secrets never stored).
- Quorum from institutional policy (high-risk amounts → 2).
- Step-up on approve (confirm + reason + Idempotency-Key).
- Expiry (`ttlSec`, default 24h); approved-then-expired never executes.

## 4. Execution (TOCTOU-safe)

Immediately before the provider/state mutation, the handler recomputes the
expected parameters from CURRENT stored data and calls `_binding_enforce`:
find live bindings → field-compare (amount/currency/terms/counterparty) →
state=approved → fresh → quorum → **atomic conditional UPDATE to consumed**
(rowcount decides concurrent winners) → structured audit (fail-closed).
Idempotency keys are checked first, so safe retries return cached responses
without consuming anything.

Trade-off (documented): if the provider call fails AFTER consume, the
binding is spent and a retry needs fresh approval. Fail safe, not fail
convenient — deliberate.

## 5. AI / admin containment

No AI input exists in these modules (source-scan asserted); AI output is
never an approval. Admins follow the same quorum + step-up; no bypass path.
Unauthorized invocations: 401 without bearer, 403 non-admin approve,
422 unknown op type / missing step-up.

## 6. Test-case mapping (required cases)

| Case | Test |
|---|---|
| Amount modified after approval | `test_amount_recipient_currency_modified_after_approval` |
| Recipient modified after approval | same |
| Currency modified after approval | same |
| Expired approval | `test_expired_approval_refused` |
| Duplicate execution | `test_duplicate_execution_single_use_consume` |
| Cross-tenant replay | `test_cross_tenant_approval_replay_denied` |
| Self-approval | `test_self_approval_identity_and_alt_account_denied` |
| Concurrent approval + modification | `test_concurrent_approval_and_modification` + 8-thread consume race |
| Unauthorized API invocation | `test_unauthorized_api_invocation` |
| AI attempting to approve | `test_ai_cannot_approve_payment` |

## 7. Limitations (honest)

- The digest proves integrity/binding, NOT signer identity. Sandbox signer
  authentication is bearer-credential binding; production needs WebAuthn or
  managed asymmetric keys with server-side verification.
- Legacy intent-only unlock remains for compatibility (STRICT mode); all
  execution paths must migrate to bindings before real funds (R-03/R-04).
- Postgres replica concurrency is guarded by the same conditional UPDATE,
  but cross-replica load testing is pending (R-10).

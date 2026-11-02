# Agreement + Crypto Guardrails — sandbox/testnet

Implementation: `modal_backend/programmable.py`, `modal_backend/evm.py`,
`modal_backend/db.py`, routes in `modal_backend/api.py`.
Tests: `modal_backend/test_agreement_guardrails.py` (13 property/adversarial),
plus existing `test_programmable_contracts.py`, `test_evm_payments.py`.

## 1. Programmable fiat agreements (15 requirements mapped)

1. **No unilateral modification**: `terms_hash()` (SHA-256 over canonical
   JSON) binds approvals, evidence, and execution. `GET` returns
   `termsHash` + `termsValid`; `execute` refuses on mismatch (`TERMS_TAMPERED`).
2. **Approval binds exact terms/parties/amounts/currencies/conditions**: any
   1-byte change yields a different hash (property-tested, 50 seeded cases).
3. **Versioned contracts + explicit consent**: `POST .../amend` bumps
   `version`, clears evidence (approvals never transfer across versions),
   requires `expectedPrevHash` (optimistic concurrency — stale/replayed
   amendments rejected) + **dual consent** (creator AND a distinct approver,
   both consenting to the exact new hash). Eligibility freezes terms: amending
   an `eligible_for_execution` agreement is refused (cancel + recreate
   instead — explicit and auditable).
4. **Replay prevention**: idempotency keys with payload-conflict detection
   (same key + different payload → 409); same-key execute retries return the
   cached response; distinct-key retries after completion → 409.
5. **Idempotency**: `_idem_key(tenant:route:key|body-hash)` on create,
   execute, fiat, EVM, refund, cancel paths.
6. **Authorization per transition**: `can_transition()` role × state matrix is
   fuzz-tested (200 seeded combinations; terminal states never leave).
7. **Independent condition verification**: deterministic `evaluate_*` engine
   (no I/O, no AI); `verify_evidence_attestation()` requires an authenticated
   source record (`attestedBy` + `attestedAt` + signature/oracleRef) — bare
   caller assertions are rejected at the helper level and by the evidence
   endpoint's `authenticated` flags.
8. **AI never declares conditions/executes**: `pag_execute` source contains
   no AI imports (asserted in tests); `decision_from_ai()` is always
   `approved:false, autoEnforced:false, advisoryOnly:true`.
9. **No employee/admin bypass**: execution needs admin bearer AND human
   `executor` role AND eligibility AND (strict mode) approved intent; maker ≠
   checker enforced by credential binding.
10. **Dispute/cancel/expiration/recovery**: dispute freezes execution;
    cancel is terminal (admin); expiry is lazy-checked on read + enforced at
    execute (410); recovery = correction plan + new version (history
    append-only, never rewritten).
11. **Cryptographic integrity**: hash-chained history (`verify_chain`),
    terms hash, tenant-bound idempotency digests.
12. **Wallet-side signing**: the backend never signs; `submit` accepts only
    the public tx hash (+ optional sender address). `verify_submission_-
    attestation()` validates formats; there is no private-key/seed field
    anywhere in the API surface (asserted by source scan in tests).
13. **No private keys stored**: no key fields, no signing code; frontend signs
    via viem + EIP-1193 (see `apps/terminal/src/evm.ts`).
14. **Provider capabilities + authoritative status**: `assert_sandbox()`
    fail-closed; Stripe TEST prefix enforced; provider response is authoritative
    (frontend never marks success); receipts are inclusion proofs, and
    `businessSettled` stays `false` until a separate business step.
15. **No escrow/custody claims**: `validate_creation` rejects `custodyClaim`
    AND scans for forbidden phrases (escrow, custody, guaranteed settlement,
    principal-protected, funds-are-held wording). The disclosure *disclaims*
    escrow. Violations → 422.

## 2. Crypto testnet (Sepolia)

- `assert_testnet`: mainnet (1) refused (`MAINNET_REFUSED`); only 11155111.
- **Chain-bound request IDs**: `request_id_for_chain(tenant, chainId, ...)` —
  the same `(to, value)` on different chains can never collide
  (property-tested).
- **Cross-payment replay**: one tx hash binds at most one tracked request per
  tenant (`evm_by_tx_hash` check → 409 `REPLAY`); same-payment resubmit of the
  identical hash is allowed (safe retry); `replace` links `replaced_by`.
- Terminal states (`confirmed/failed/expired`) refuse resubmits.
- RPC failures degrade to stored state with a retry note — never to a faked
  success (`businessSettled: false`).

## 3. Adversarial coverage (each a failing-then-passing test)

Double execution (same + distinct keys, incl. in-flight race guard via
post-provider reload); unauthorized transitions/role bypass; 1-byte terms
tamper at execute; amendment replay/stale-hash/missing-consent; idempotency
conflict + tx-hash reuse; expired agreement execute; cross-tenant agreement +
EVM access; AI-execution attempt; key-hygiene source scan; escrow-claim
injection.

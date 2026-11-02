# Guardrail Test Report — adversarial + integrity coverage

Date: 2026-11-02. Scope: sandbox only. Command:
`API_SHARED_TOKEN=dev-shared-token API_ADMIN_TOKEN=dev-admin-token
pytest modal_backend/ -q` → **182 passed, 4 skipped** (skips: opt-in live
RPC/model, load-gated).

## 1. Inventory (new in this audit)

| File | Tests | What it proves |
|---|---|---|
| `test_security_audit.py` | 15 | S1–S15 scenarios: AI containment, self-approval, balance/API abuse, audit erase, cross-tenant, replay, condition bypass, escalation, expiry, unjustified + lawful restrictions, compromised AI, policy tamper |
| `test_approval_binding.py` | 11 | Digest determinism, amount/recipient/currency mutation, expiry, single-use, 8-thread consume race (exactly 1 winner), cross-tenant replay, alt-account self-approval, approve-vs-modify race, unauthorized invocation, AI approval attempt, end-to-end refund flow |
| `test_audit_integrity.py` | 9 | No API mutation surface, deletion detection, digest forgery, seq gaps, duplicates, outage fail-closed + buffering, cross-tenant denial, compromised-admin containment, verification report + redaction |
| Prior suites | 147 | Fiat/EVM/contracts/AI/rights/PDP/regression (unchanged behavior preserved) |

## 2. Defects found by these tests (all fixed or tracked)

- Expiry/amount ignored by STRICT gate → fixed + S11 regression test.
- Same-credential alt-account approval → fixed on binding path (credId).
- Migration comment-semicolon SQL syntax error → fixed (comment hygiene).
- Test-order `sqlite_sequence` leakage → hermetic reset in `db.reset_for_tests`.
- 8-thread consume race → exactly-once consume verified.

## 3. Execution log (representative)

- `test_security_audit.py`: 15 passed (isolated TestClient, fake tenants).
- `test_approval_binding.py`: 11 passed (incl. concurrency + tamper cases).
- `test_audit_integrity.py`: 9 passed (incl. forgery/deletion/outage).
- Live smoke (local uvicorn, killed after): restriction create 201,
  AI-only 422, gag-order notify=false, appeal overturn + correction,
  `/health` liveMode OFF.

## 4. Coverage boundaries (what tests do NOT cover)

Real money rails, live Stripe/BTCPay/RPC networks, Modal cloud deployment,
secret management, browser key custody, OS/network layers, human processes.
Property tests use seeded stdlib randomness (no hypothesis dependency).

## 5. No-guarantee statement

**Passing automated tests do not constitute a security guarantee.** They
verify specified behavior under specified (sandbox, isolated, non-adversarial
infrastructure) conditions. Residual risks are listed in THREAT_MODEL.md §6;
open work in REMEDIATION_PLAN.md. Production requires threat-led pentest,
independent code review, and the WORM/dual-control measures in
AUDIT_ARCHITECTURE.md before handling real funds or PII at scale.

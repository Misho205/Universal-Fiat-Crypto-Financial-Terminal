# Security Control Matrix — implemented vs required

Pinned versions: PDP `2026.11.02-v1` • bindings `ab-v1` • audit `ae-v1` •
break-glass `bg-v1` • AI control `aic-v1` • disputes `dsp-v1`.
Legend: ✅ implemented+tested • ⚠️ implemented with documented limitation •
❌ not implemented (with remediation ref).

## A. Authorization (all server-side; frontend never authorizes)

| Control | Required | Implemented | Test |
|---|---|---|---|
| Bearer auth on sensitive routes (401 without) | yes | ✅ `require_auth/require_admin` | integration t4 |
| Role separation operator/admin (+auditor/compliance/approver/owner in PDP/audit) | yes | ✅ | integration t4/t10 |
| Tenant isolation derived from server binding | yes | ✅ `require_tenant` + cross-tenant deny | integration t10 |
| Default-deny PDP, explainable decisions | yes | ✅ 23-action matrix, unknown→deny | `test_pdp.py` |
| Maker-checker + quorum + no-self-approval (identity AND credential) | yes | ✅ intents + `credId` bindings | binding tests |
| Step-up (confirm+reason+Idempotency-Key) | yes | ✅ approve/role/tenant/emergency/refund paths | institutional tests |
| Immutable approval scope + expiry | yes | ✅ digest-bound + STRICT expiry+amount recheck | S11, integration t5 |
| Atomic single-use consume (no double execution) | yes | ✅ conditional UPDATE, 8-thread race | binding tests |
| Revalidation immediately before execution | yes | ✅ `_binding_enforce` on 5 money/authority paths | integration t5 |
| Break-glass least privilege + independent approval | yes | ✅ allowlist gateway, dual approval, preauth read-only | breakglass tests |
| AI kill switch server-side + dual-control re-enable | yes | ✅ DB control, per-feature flags, verifier≠disabler | ai_control tests |
| Dispute independent review + no silent close/delete | yes | ✅ reviewer≠actor, decision required, no DELETE route | dispute tests |

## B. Audit (tamper-evident, fail-closed)

| Control | Required | Implemented | Test |
|---|---|---|---|
| Structured server-side events (actor/tenant/action/resource/outcome/policy/correlation/approval) | yes | ✅ `audit_events` | integrity tests |
| Append-only (no app mutation paths) | yes | ✅ source-scanned | integrity t1 |
| Hash chain + tamper detection | yes | ✅ seq-in-digest (+legacy chain) | integrity t3/t4 |
| Fail-closed writes on sensitive paths (unified 503) | yes | ✅ `must_audit_or_503` everywhere | integration outage test |
| Independent auditor reads | yes | ✅ `/api/audit/events|verify` (auditor+) | integration t4/t10 |
| Export + buffering/retry | yes | ✅ JSONL + outbox | integrity t6 |
| WORM immutable destination | production | ⚠️ evaluated, sandbox dir only (R-05) | NOT TESTED live |
| Trusted timestamps | production | ⚠️ monotonic server clock, no TSA (R-09) | NOT TESTED |

## C. Gaps / limitations (→ REMAINING_RISKS.md)

- ❌ Legacy intent-only unlock still available when STRICT=0 (R-03/R-04).
- ⚠️ PDP sandbox wiring passes permissive intent context (R-08).
- ⚠️ Signer identity is bearer-credential binding, not asymmetric/WebAuthn.
- ⚠️ Sandbox MFA attestation + stub AV verdict (production verification required).
- ⚠️ `ai.invoke_tool` unwired HTTP-wise (tested direct); wire or remove (R-07).
- ❌ No pentest, no Modal-replica concurrency test, no Postgres-path tests.

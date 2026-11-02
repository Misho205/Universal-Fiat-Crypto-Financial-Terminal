# Remaining Risks — explicit, owned, not hidden by green tests

Passing tests verify specified behavior under sandbox conditions. They do
NOT retire the risks below. Each risk has an owner-action and a gate it
blocks (sandbox demo / staging / production).

## Security risks

| ID | Risk | Blocks | Action |
|---|---|---|---|
| R-03 | Legacy intent-only unlock (STRICT=0 default) bypasses digest binding on all paths; binding enforcement is additive | Production | Migrate all execution paths to bindings; then default STRICT=1 |
| R-04 | Legacy self-approval check misses same-credential/different-label quorum counting | Production | Enforce `credId` on legacy approve or retire legacy path |
| R-05 | Single-admin DB access can rewrite chains (detection via exports only); no WORM; audit/admin planes share a process | Staging | WORM export target + separate audit administrator + dual control |
| R-08 | PDP sandbox wiring passes permissive intent context; real `needs_intent` deferred to handlers | Production | Flip to real intent context once all callers carry intents |
| R-07 | `ai.invoke_tool` has no HTTP route (dead code with a policy gate) | Staging | Wire behind `ai.execute` PDP or delete |
| R-11 (new) | `dispute/review` assignment is operator-performable (triage); only `decide` is role-gated | Accepted sandbox | Production: gate review-assignment to staff roles via JWT claims |
| R-12 (new) | `ai/analyze` tenant scope added this audit; historical tenant-less calls in old logs unattributed | Accepted | None (forward fix) |

## Operational risks

| ID | Risk | Blocks | Action |
|---|---|---|---|
| O-01 | Multi-replica consume race tested with threads only, on sqlite | Staging | Postgres `SELECT FOR UPDATE` + load/chaos test (R-10) |
| O-02 | Kill-switch propagation is "next check", not broadcast | Accepted sandbox | Documented; production runbook must include replica verification |
| O-03 | Circuit breaker is error-count based, not semantic | Accepted | Human-review gates remain the semantic control |
| O-04 | Audit export destination is a local dir in sandbox | Staging | WORM target + retention + restore drills |

## Legal / compliance risks

| ID | Risk | Blocks | Action |
|---|---|---|---|
| L-01 | Jurisdiction profiles are procedural parameters, not legal interpretation; BG/EU enforcement needs qualified counsel review per profile | Staging with real users | Legal review records + DPA + retention schedule |
| L-02 | Sandbox MFA attestation and AV-stub are not verification | Staging | WebAuthn/TOTP verification; ClamAV/AV pipeline |
| L-03 | Fiscal (NRA H-18), KYC/KYB, licensing, CASP — roadmap only | Production | `docs/real-money-roadmap.md` in order |
| L-04 | On-call/paging/SIEM integration absent; notifications are API-polled | Staging | SIEM forwarding + alerting runbook |

## Explicit non-guarantee

Nothing in this file, or in any passing suite, certifies production
readiness. See DEPLOYMENT_READINESS.md for the sandbox-vs-production gate.

# AI Emergency Response — Kill Switch & Isolation Framework

Status: sandbox only. Implementation: `modal_backend/ai_guardrails/control.py`
(distributed control), `policy.py` (kill-switch state), `tools.py`
(execution-time re-authorization), `modal_backend/api.py` (endpoints, feature
flags, circuit breaker). Tests: `modal_backend/test_ai_control.py` (8/8),
`test_ai_guardrails.py`, `test_security_audit.py` S14.
Report: `AI_KILL_SWITCH_TEST_REPORT.md`.

## 1. Controls

- **Global inference switch** (`inference_enabled`): `require_ai_enabled`
  returns 503 on every model-calling route (`/api/ai/*`, incl. previously
  unguarded `/api/ai/analyze` — audit fix). Payments, dashboards, reconcile
  keep serving.
- **Tool execution switch** (`tools_enabled`): `invoke_tool` re-checks at
  execution time (generation check) — queued/concurrent calls authorized
  before a disable are invalidated, closing the TOCTOU race.
- **Per-feature flags**: `assistant`, `fraud_signals`, `routing`,
  `contract_analysis`, `explainers` — independently revocable (fraud_signals
  and assistant wired as route dependencies).
- **Trusted control plane**: only admin bearer may change state; disable
  needs a reason; re-enable needs a reason + an INDEPENDENT verifier
  (different identity from the disabler). The model has no code path to
  control state; operators cannot override a disable (403).
- **Deterministic fallback**: disabled AI yields 503/advisory stubs — never
  fund movement, never blocked payments.

## 2. Distributed enforcement (no process-local reliance)

State lives in the `ai_control` table (single global row, versioned), read on
every guard evaluation — every Modal container/replica enforces the latest
state on its next check without redeploys or env pushes. The legacy runtime
flag + `AI_DISABLED` env remain as belt-and-suspenders local overrides.
Generation counter invalidates in-flight tool permissions on every disable.

## 3. Circuit breaker, rate limits, alerts

Consecutive provider failures trip auto-disable (`AI_CB_THRESHOLD`, default 5)
with an audited alert; success resets the counter (a trip needs explicit
re-enable). Rate limiting maps to 429 + alert. Injection blocks, tool denials,
and breaker trips are recorded in the independent audit system and visible to
security personnel.

## 4. What is NOT claimed

The breaker trips on consecutive errors, not on semantic compromise — a
subtly malicious model output is contained by the advisory-only envelope and
human-review gates, not by the switch. Replica-wide immediacy is "next
check", not synchronous broadcast. No SIEM paging in sandbox.

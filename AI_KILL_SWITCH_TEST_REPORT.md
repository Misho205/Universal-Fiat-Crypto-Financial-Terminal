# AI Kill-Switch Test Report

Date: 2026-11-02. Files: `modal_backend/test_ai_control.py` (8/8),
`test_ai_guardrails.py` (kill-switch section), `test_security_audit.py` S14.
Full backend suite: 207 passed / 4 skipped. Sandbox only.

## Results per required scenario

| # | Scenario | Result | What it proves |
|---|---|---|---|
| 1 | Compromised AI tool request | PASS | Forbidden tools denied by policy + at execution; denials audited |
| 2 | AI service outage | PASS | Circuit breaker trips after N consecutive failures; deterministic fallback; explicit re-enable required |
| 3 | Concurrent AI requests during shutdown | PASS | Hammering during toggle: only 200-before or 503-after; zero 200s after disable completes; in-flight tools invalidated via generation |
| 4 | Attempts to bypass disabled state | PASS | Direct `invoke_tool` re-check denies; feature flags cannot resurrect inference; previously unguarded `/ai/analyze` now guarded (fix) |
| 5 | Unauthorized re-enablement | PASS | Operator 403; missing reason 422; missing/same-identity verifier 403; independent verifier 200 |
| 6 | Continued availability of independent payment services | PASS | Fiat create/confirm + dashboard 200 while AI is 503 |

Plus: distributed control row propagates (status/version/generation
observable); disablement + re-enablement independently audited
(`ai.killswitch` in `audit_events`); no API keys leak via AI responses
(redaction + negative scan).

## Fixes applied during testing

- `/api/ai/analyze` lacked the kill-switch guard → guarded.
- `invoke_tool` skipped authorization → now evaluates policy + tools switch + generation at execution time.
- `require_ai_feature` added; wired to `fraud_signals` + `assistant`.
- Re-enable hardened: reason + independent verifier required.
- Circuit breaker wired into `_ai_or_429` (failure counting, trip alert, success reset).

## Limitations

"Next check" propagation (not synchronous broadcast); single-credential
sandbox independence is identity-level (production: second hardware
credential/OIDC); breaker is error-count based, not semantic.

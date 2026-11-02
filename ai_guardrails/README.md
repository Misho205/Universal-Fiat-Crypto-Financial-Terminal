# ai_guardrails/

Runtime enforcement for the AI advisory plane. Implementation lives in
`modal_backend/ai_guardrails/` (baked into the Modal image):

- `policy.py` — capabilities, forbidden actions, spending/rate limits,
  deterministic decision gates, emergency kill-switch.
- `tools.py` — allowlisted read-only tools, server-side permission checks.
- `redaction.py` — untrusted-input handling, injection/role-spoof detection,
  output schema validation, sensitive-data redaction.
- `audit.py` — tamper-evident, hash-chained security event log (no PII).

Institutional (human) guardrails live in `modal_backend/institutional.py`
with persistence in migration `004_guardrails.sql`:

- RBAC/ABAC, default-deny sensitive endpoints, segregation of duties,
  maker-checker intents, multi-party quorums, no self-approval,
  time-limited purpose-bound JIT elevation, step-up authentication,
  tenant isolation, tamper-evident audit, emergency access with review.

Policy documents (repo root):

- `AI_SECURITY_POLICY.md` — capabilities, prohibitions, enforcement layers.
- `AI_TOOL_PERMISSIONS.md` — allowlist matrix and decision gate contract.
- `AI_RED_TEAM_TESTS.md` — adversarial plan and execution record.

Tests: `modal_backend/test_ai_guardrails.py`,
`modal_backend/test_institutional_guardrails.py`.

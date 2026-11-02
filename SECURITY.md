# Security policy

> Non-advice; independent review required before any live activity.

## Reporting
Open a private issue/PR to the maintainers. Do not post suspected live keys in public channels.

## Guarantees in this repo (sandbox)
- No live credentials anywhere: `sk_live_*`, `*_LIVE` values, mainnet keys are refused by code and absent from source.
- Secrets travel only via environment / Modal Secrets (`hybridpay-test`); the browser bundle contains
  only `NEXT_PUBLIC_*` URLs and a sandbox bearer token (documented; prod uses session auth).
- No PAN/CVV/PIN/seed collection: provider-hosted collection only; no browser `localStorage` for payment data.
- Webhooks are HMAC-verified with timestamp tolerance + eventId dedupe; stale/forged events are rejected (tested).
- AI never moves funds: advisory-only envelopes + no provider imports (asserted by `test_ai_endpoints_cannot_move_money`).
- AI guardrails (`modal_backend/ai_guardrails/`): default-deny policy engine, allowlisted
  read-only tools, prompt-injection/role-spoof screening with fail-closed refusal, PII/secret
  redaction, output schema validation, per-tenant rate limits, hash-chained AI audit log,
  emergency kill-switch (`503` AI-only, payments unaffected). Attack coverage in
  `test_ai_guardrails.py`; policy in `AI_SECURITY_POLICY.md` / `AI_TOOL_PERMISSIONS.md`.
- Institutional guardrails (`modal_backend/institutional.py` + migration `004_guardrails.sql`):
  RBAC/ABAC default-deny, maker-checker intents, multi-party quorum for high-risk amounts,
  no self-approval (same credential = same person), step-up confirmation, JIT elevation with
  expiry, emergency access with justification + independent review, tenant-scoped tamper-evident
  audit (`GET /api/admin/audit`), strict mode (`INSTITUTIONAL_STRICT=1`) that fails closed
  direct money calls without an approved intent. Bypass coverage in
  `test_institutional_guardrails.py`.
- Readiness probe `GET /ready` exposes only aggregate status (no secrets) for bank monitoring.

## Verification you can run
```
grep -rn -E "sk_live_|sk_test_[A-Za-z0-9]{8,}" --include="*.py" --include="*.ts" --include="*.tsx" . | grep -v node_modules | grep -v dist | grep -v .next
grep -rn "localStorage\|sessionStorage" apps/terminal packages/sdk --include="*.tsx" --include="*.ts"
HYBRIDPAY_DB_MEMORY=1 API_SHARED_TOKEN=dev-shared-token pytest modal_backend/test_fiat_payments.py -q
```

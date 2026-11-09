# Remediation Changelog — audit branch `audit/eu-security-readiness-2026-11-09`

> Every entry: verified fix with regression test, or explicit deferral with
> rationale. No production systems touched; sandbox behavior preserved;
> no public API contracts broken. Root causes, files changed, residual risks below.

## Implemented

### H-01 — NestJS open CORS → explicit allow-list (HIGH)
- Root cause: `app.enableCors()` with no options allowed any origin on the
  Postgres-backed system-of-record API (`apps/api/src/main.ts:7`).
- Fix: allow-list from `CORS_ORIGINS` (default `http://localhost:3000,
  http://localhost:3001`), wildcard refused (fail closed to default),
  methods GET/POST, headers mirroring the Modal backend, `credentials:false`.
- Files: `apps/api/src/main.ts`, `apps/api/test/api.test.ts` (preflight
  allowed-origin + evil-origin regression test).
- Verified: `pnpm --filter @hybridpay/api test` → 8 passed (incl. new test).
- Residual: LOW — deploy must set `CORS_ORIGINS` to exact frontend origins.

### H-02 — No general API rate limiting → conservative per-instance limiter (HIGH)
- Root cause: only AI endpoints were throttled; all other routes unthrottled
  (OWASP API4:2023).
- Fix: fixed-window per-IP middleware in `modal_backend/api.py`
  (`RATE_LIMIT_PER_MIN`, default 6000/min — CI-friendly; `/health`+`/ready`
  exempt; 429 + `Retry-After: 60`).
- Files: `modal_backend/api.py`, `modal_backend/test_remediation_audit_fixes.py`.
- Verified: full `pytest modal_backend/` green (225 passed, 4 skipped);
  dedicated 429/Retry-After/exempt test.
- Residual: MEDIUM — per-instance memory is not a DDoS control; production
  MUST set a lower limit (300–600/min) + Modal concurrency + edge WAF.
  Documented in `ENTERPRISE_READINESS_ROADMAP.md`.

### M-05 — Non-canonical idempotency fallback hash → canonical JSON (MEDIUM)
- Root cause: `_idem_key` hashed `str(body)` — field-order/format fragile
  when no `Idempotency-Key` header is sent (`modal_backend/api.py:560`).
- Fix: `json.dumps(sort_keys=True, separators=(",",":"))` fallback; explicit
  header keys pass through verbatim (contract unchanged).
- Files: `modal_backend/api.py`, regression tests (order-independence +
  no-duplicate replay).
- Verified: 4/4 new tests pass; full suite green.
- Residual: LOW — in-flight fallback keys from older builds differ (sandbox-ephemeral only).

### M-06 — Silent tokenless dev mode → loud startup warning (MEDIUM)
- Root cause: no tokens configured ⇒ `dev-caller` + client-supplied tenant
  with no signal (`auth.py:41-43`); misdeployment risk.
- Fix: one-time `logger.warning` at backend startup naming the exact env vars
  to set. Hard refusal deliberately NOT implemented (would break documented
  local quickstart) — refusal is a roadmap gate.
- Files: `modal_backend/api.py`, subprocess regression test (warning present
  in tokenless fresh interpreter).
- Residual: LOW (warning, not enforcement).

### M-02 — postcss + multer transitive advisories → pnpm overrides (HIGH/MEDIUM)
- Root cause: `postcss@8.4.31` via next 15.5.28 (4 advisories, fixed ≥8.5.23);
  `multer@2.4.0` via @nestjs/platform-express (DoS, fixed ≥2.5.0; unreachable —
  no upload endpoints — but patched anyway).
- Fix: root `package.json` `pnpm.overrides` → `postcss@8.5.32`, `multer@2.5.0`.
- Verified: `pnpm audit` 10 → 5 vulns; terminal `next build` OK; api 8/8 tests pass.
- Residual: LOW — remaining 5 vulns are vitest-3 dev-only (see deferred M-03).

### M-04 — Webhook bearer requirement → signature-as-authentication (MEDIUM)
- Root cause: `stripe_webhook` demanded `require_auth`, but genuine Stripe
  deliveries carry no bearer token — webhook liveness failed whenever API
  tokens were configured.
- Fix: bearer made optional; HMAC-SHA256 signature + 300 s tolerance + raw-body
  + `stripe:{event.id}` dedupe unchanged and mandatory (fail closed 401/410).
  Valid bearer only labels the audit caller (`service-caller` vs
  `stripe-webhook`); invalid bearer never overrides a valid signature.
  Unauthenticated probing is additionally throttled by the H-02 limiter.
- Files: `modal_backend/api.py`, `test_remediation_audit_fixes.py`
  (`test_m04_...`: signature-only 200, replay deduped, wrong-bearer+valid-sig
  200, unsigned 401 with and without bearer).
- Verified: new test + all pre-existing webhook tests green (19 passed).
- Residual: LOW — rotate `STRIPE_WEBHOOK_SECRET_TEST` per environment; monitor
  401-rate on the endpoint for probing.

## Deferred (not implemented on this branch)

- **M-01 starlette/fastapi pins**: not exploitable here (no `request.url`
  authz, no file serving, no form parsing). Upgrade changes the Modal image;
  needs operator approval + image rebuild. Tracked in roadmap.
- **M-03 vitest 3.2.7 (tinypool/mocker)**: dev-only; fix requires vitest 4.x
  major migration across 7 packages (config-breakage risk). Accepted residual
  with mitigation (CI-local execution, no production artifact); roadmap.
- **M-04 webhook bearer-auth**: implemented above (was deferred pending approval).
- **pytest 8.3.4 advisory**: dev-only local; bundle with Modal image upgrade.

## Reverted / no-op
- `pnpm update postcss` alone did not move the transitive pin (next's range);
  override was required. No other dependency changes.

# Security Findings — HybridPay (static analysis + local tests, 2026-11-09)

> Prototype audit. No production systems touched. Each finding was verified
> against code on branch `audit/eu-security-readiness-2026-11-09`; prior
> reports treated as claims until re-verified. Ratings combine exploitability
> in the *current sandbox prototype* with enterprise-readiness impact.
> **No CRITICAL findings verified.**

Test basis: `pytest modal_backend/` → **218 passed, 4 skipped** (command in
`TEST_EVIDENCE.md`); `pip-audit` on `requirements.txt`; `pnpm audit`;
targeted grep/read verification of auth, CORS, SQL, XSS, SSRF, secrets.

## HIGH

### H-01 — NestJS API enables unrestricted CORS
- Location: `apps/api/src/main.ts:7` — `app.enableCors()` with no origin allowlist.
- Impact: the Postgres system-of-record API accepts cross-origin requests from
  any site (incl. credentialed modes depending on defaults). Sandbox/local-only
  exposure today; blocks any shared/bank deployment.
- Status: **fix in Phase 4** (allowlisted origins + env override, mirroring `modal_backend`).

### H-02 — No general API rate limiting / abuse protection (Modal backend + NestJS)
- Verified: only AI endpoints are rate-limited (`AI_RATE_LIMIT_PER_MIN=20`,
  `meta_client.py:205-210`); no middleware (slowapi/limiter) anywhere
  (`grep slowapi|limiter` → no hits outside AI usage copy).
- Impact: unauthenticated 401-probing, idempotency-key enumeration, and
  compute-heavy endpoints (contract validation, EVM polling) are unthrottled.
  Sandbox impact low; enterprise HIGH (OWASP API4:2023 Unrestricted Resource Consumption).
- Status: **fix in Phase 4** (conservative per-instance limiter, generous
  default, `/health`+`/ready` exempt, 429+Retry-After, full suite must stay green).

## MEDIUM

### M-01 — Transitive starlette 0.41.3 advisories (Host-header, Range DoS, form-DoS)
- Source: `pip-audit -r modal_backend/requirements.txt` → 14 advisories incl.
  PYSEC-2026-161 (Host→`request.url` auth bypass), -1942 (Range DoS), -249 (urlencoded form-DoS).
- Verified NOT exploitable here: no `request.url`-based authz, no
  `StaticFiles`/`FileResponse`, no `request.form()` (JSON + raw body only).
- Action: defense-in-depth upgrade of `fastapi`/`starlette` pins (Modal image
  pins authoritative — `requirements.txt:1-3`, `app.py:22`); **roadmap, not Phase 4**
  (image change + deploy implications need operator approval).

### M-02 — Transitive postcss 8.4.31 advisories (build-time, via next 15.5.28)
- Source: `pnpm audit` → GHSA-6g55-p6wh-862q, -r28c-9q8g-f849, -qx2v-qp2m-jg93,
  -fxqj-rqcc-2cmp (sourceMappingURL / XSS, fixed ≥8.5.23). Note:
  `apps/terminal/package.json` already declares `postcss: ^8.5.32` direct.
- Verified: build-time only; no attacker-controlled CSS in pipeline.
- Status: **fix in Phase 4** (`pnpm update postcss` / override + build verify).

### M-03 — Dev-only tinypool / @vitest/mocker advisories (vitest 3.2.7)
- Source: `pnpm audit` → 2 critical (tinypool RCE gadgets, GHSA-5gmw-xhrv-c9v3,
  GHSA-85c8-ppgw-ccpr) + 1 moderate (mocker code injection, GHSA-qxg6-89mg-rqv8).
- Verified: devDependency only (`vitest` in 7 packages, `test: vitest run`);
  no production runtime path.
- Status: **fix in Phase 4 if green** (vitest 3.x latest; major 4.x only if tests pass, else pin + roadmap).

### M-04 — Stripe webhook endpoint requires bearer auth → signature-as-authentication (MEDIUM, FIXED)
- Location: `api.py` (`stripe_webhook`).
- Was: `require_auth` blocked genuine Stripe deliveries (no bearer) when tokens
  configured. Signature HMAC + tolerance + dedupe were already correct.
- Fix: bearer optional; HMAC signature mandatory and unchanged (fail closed
  401/410); valid bearer only selects the audit caller label, invalid bearer
  never overrides a valid signature; unauthenticated probing additionally
  covered by the H-02 rate limiter.
- Verified: `test_m04_webhook_accepts_signature_only_rejects_unsigned`
  (signature-only 200, replay deduped, wrong-bearer+valid-sig 200,
  unsigned 401 ± bearer); pre-existing webhook tests unchanged and green.

### M-05 — `_idem_key` fallback hash uses non-canonical `str(body)`
- Location: `api.py:560-562`.
- Verified: explicit `Idempotency-Key` paths unaffected; only the no-header
  fallback hashes `str(model_dump())` (field-order/format fragile across SDK versions).
- Status: **fix in Phase 4** (canonical `json.dumps(sort_keys=True)` fallback; 409 semantics unchanged).

### M-06 — Tokenless `dev-caller` bypass + header-tenant trust (deployment hygiene)
- Location: `auth.py:41-43, 90-93` — no tokens configured ⇒ all requests
  `dev-caller` with client-supplied tenant.
- Verified: by design for bare local dev; dangerous only if misdeployed with
  shared network + no tokens.
- Status: **fix in Phase 4** (loud startup warning + documented deploy gate;
  hard refusal would break the documented quickstart, so refusal is roadmap-gated).

## LOW / INFO

- **L-01** pytest 8.3.4 PYSEC-2026-1845 (local `/tmp` DoS; dev-only). Roadmap (pytest 9.x with Modal image).
- **L-02** EVM `evm_by_provider_ref` tenant-scoped; cross-tenant same-hash replay
  not detected (hashes globally unique in practice). Accepted, documented.
- **L-03** Frontend: `NEXT_PUBLIC_API_TOKEN` bake-in (dev bearer in bundle),
  `TxTable isAdmin=false` hardcode, `StatusTimeline` linearization, pagination
  `total` trust. UX/integrity notes; no fund-movement path.
- **L-04** Outbound SSRF: only env-operator URLs (`SEPOLIA_RPC_URL`,
  `META_MODEL_BASE_URL`); no user-controlled fetch targets. Accepted.
- **L-05** multer 2.4.0 DoS advisory: unreachable — no upload endpoints
  (`grep FileInterceptor|UploadedFile` → none). No action except routine update.

## Re-verified prior concerns (no longer issues in current code)

- Modal CORS preflight: explicit allowlist + GET/POST-only routes ⇒ covered.
- AUTHORIZED/DECLINED inconsistency: single `simulator-results.ts` mapper; resolved.
- Local simulation fallback: explicit `mode=local` only; SDK throws 503 otherwise.
- Secrets: `.env` gitignored + untracked; no hardcoded live secrets; bearer best-practices (compare_digest, memory-only browser token, no cookies ⇒ CSRF N/A).
- SQL: fully parameterized; approval binding atomic conditional UPDATE.
- XSS/redirects: no `dangerouslySetInnerHTML`, no open redirects, no `localStorage` tokens.

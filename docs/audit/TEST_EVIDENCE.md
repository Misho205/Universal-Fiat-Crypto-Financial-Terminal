# Test Evidence — audit branch (commands, results, limits)

> No fabricated results. Every line below is the actual output of the command
> shown, run 2026-11-09 on branch `audit/eu-security-readiness-2026-11-09`.
> Failures and limits are recorded, not hidden.

## 1. Backend suite (FastAPI sandbox)
- Command: `API_SHARED_TOKEN=dev-shared-token API_ADMIN_TOKEN=dev-admin-token python3 -m pytest modal_backend/ -q -p no:cacheprovider`
- Final result: **222 passed, 4 skipped** (16.01 s). Intermediate run during
  remediation: 221 passed + 1 failed (M-06 assertion looked in stderr; warning
  is emitted on stdout — test corrected, full suite re-run green).
- Skips (4, pre-existing): optional live-integration tests requiring
  `RUN_META_INTEGRATION=1` / `RUN_SEPOLIA_RPC_TEST=1` + real keys/RPC —
  correctly skipped in sandbox.
- Includes new `test_remediation_audit_fixes.py` (4 tests: H-02 429/Retry-After/
  health-exempt, M-05 order-independence + no-duplicate replay, M-06
  tokenless-warning subprocess).

## 2. NestJS API (`@hybridpay/api`)
- Command: `pnpm --filter @hybridpay/api test` → **2 files, 8 tests passed**
  (incl. new H-01 CORS preflight test: allowed origin echoed, evil origin refused).
- Command: `pnpm --filter @hybridpay/api build` (`tsc -p tsconfig.json`) → clean.
- Live NestJS sandbox regression: built `dist`, started
  `PORT_API=3001 node apps/api/dist/main.js`, ran
  `API_BASE=http://localhost:3001 node tests/e2e/mock-flow.mjs` →
  **"E2E mock flow OK"** (instruction AUTHORIZED, order ord-1). Server stopped
  after. CORS fix active during this run.

## 3. Terminal (`@hybridpay/terminal`)
- Command: `pnpm --filter @hybridpay/terminal build` (`next build`) → success
  (static prerender, First Load JS 103 kB shared) with postcss 8.5.32 override.
- Command: `pnpm --filter @hybridpay/terminal test` → **7 files, 43 tests passed**.

## 4. Static security scans
- `python3 -m pip_audit -r modal_backend/requirements.txt` → 16 vulns in
  2 packages (pytest 8.3.4 ×2 incl. dup, starlette 0.41.3 ×14 incl. dups).
  Exploitability triaged in `SECURITY_FINDINGS.md` (M-01/L-01: not reachable —
  no `request.url` authz, no file serving, no `request.form()`).
- `pnpm audit` before fixes: **10 vulns** (2 critical, 3 high, 5 moderate).
  After `pnpm.overrides` (postcss 8.5.32, multer 2.5.0): **5 vulns**, all
  vitest-3.2.7 dev-only (tinypool ×2 critical, path-traversal ×2 + mocker ×1
  moderate). Vitest 4.x migration deferred (M-03, major-change risk).

## 5. SBOM
- Python: `cyclonedx-py requirements modal_backend/requirements.txt --of JSON`
  → `docs/audit/sbom-python.json` (8 direct components). Transitive deps
  (starlette etc.) resolved at image build — PARTIAL, noted.
- Node: `pnpm-lock.yaml` is the SBOM source of record (no CycloneDX emitted;
  PARTIAL). Full CycloneDX/SPDX generation queued for CI (roadmap).

## 6. NOT TESTED / limitations
- Load/DoS behavior of the new rate limiter beyond unit test (no `test_load.py`
  re-run against new middleware; Modal multi-instance semantics unverified).
- Real Stripe TEST charge flow (no TEST keys in this environment; mock only).
- Sepolia RPC receipt verification (opt-in test skipped — no RPC URL).
- Full `turbo run build/test` across all 9 packages (scoped builds/tests run:
  api, terminal; worker/packages unchanged by this audit).
- SAST tooling beyond grep/read review (no semgrep/codeql in env).
- `.env` contents never inspected (rule 4); only git-tracking status verified.

# CORS Audit — Universal Hybrid Payment Terminal

Date: 2026-11-04, live-tested against the deployed backend. No wildcard
origins anywhere. No secrets printed or exposed by this audit.

## 1. Server configuration (exact)

- `modal_backend/api.py:202-208`:
  `CORSMiddleware(allow_origins=config.ALLOWED_ORIGINS, allow_credentials=False,
  allow_methods=["GET","POST"], allow_headers=["Authorization","Content-Type","X-Tenant-Id","Idempotency-Key"])`.
- `modal_backend/config.py:21-22`: `ALLOWED_ORIGINS` parsed from env
  `ALLOWED_ORIGINS` as comma-separated, stripped, empties dropped; default
  `"http://localhost:3000,http://localhost:3001"` (local dev only).
- Deployed frontend origin (from `docs/test-report.md`, `DEMO_READINESS.md`,
  baked bundle): `https://michail-tsvetanov--hybridpay-terminal-serve.us-east.modal.run`.

## 2. Live preflight results (2026-11-04)

Request: `OPTIONS /api/payments/fiat/simulate` with
`Origin: <frontend>`, `Access-Control-Request-Method: POST`,
`Access-Control-Request-Headers: authorization,content-type,x-tenant-id,idempotency-key`.

| Origin | Result |
|---|---|
| deployed frontend origin | **HTTP 200**, `access-control-allow-origin: https://michail-tsvetanov--hybridpay-terminal-serve.us-east.modal.run`, `allow-methods: GET, POST`, `allow-headers: …Authorization…Content-Type…Idempotency-Key…X-Tenant-Id` ✅ |
| `https://evil.example` | **HTTP 400, no `allow-origin` header** — correctly rejected, no wildcard ✅ |

Conclusion: the deployed Secret's `ALLOWED_ORIGINS` **already contains the
frontend origin**. Browsers can call the backend directly; `Authorization`
and `Content-Type` (JSON) preflights pass.

## 3. Does the browser request require CORS?

Yes for the SDK path: absolute backend origin ≠ frontend origin → every
`POST /api/…` with `Authorization`+JSON triggers a preflight, which passes
(§2). The same-origin `/api/*` proxy (`modal_site_server.py`) would avoid
CORS but is NOT used by the browser (SDK base is the absolute origin).
If a browser still reports failure, it is NOT CORS from the server side —
check local VPN/ad-blocker or a cold-starting backend (`min_containers=0`;
the simulator now shows a live health indicator for this).

## 4. Changes required

**None.** Explicit allowlist confirmed working; wildcard use explicitly
rejected for this sensitive API. Do NOT add `*`, do NOT set
`allow_credentials=True`. If the frontend origin ever changes (re-deploy
under a new URL), add the exact new `https://…` origin to `hybridpay-test` →
`ALLOWED_ORIGINS` via dashboard Edit (never delete/recreate the Secret).

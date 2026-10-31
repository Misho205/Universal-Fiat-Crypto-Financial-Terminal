# LIVE mode — guardrails (code exists, money movement stays blocked without approval)

> BG резюме: LIVE режимът е имплементиран като код, но е заключен зад 3 порти. По подразбиране всичко е пясъчник и НЕ може да мръднат реални пари.

## How it works
- `LIVE_MODE` env (default `false`). Frontend mirrors it via `NEXT_PUBLIC_LIVE_MODE` for the banner only (never authoritative).
- `config.live_mode_status()`: `OFF` (default) → `BLOCKED` (`LIVE_MODE=true` but no valid `LIVE_APPROVAL_FILE`) → `ON-APPROVED` (both set).
- `GET /health` exposes the status; terminal shows `LIVE MODE: OFF/BLOCKED` banner and refuses live submits in `OFF`/`BLOCKED` builds.
- `assert_sandbox()` raises on every money path when status is `BLOCKED`. Approved-live execution lives in dedicated executors (not shipped in demo) + requires `*_LIVE` credentials (absent).

## To request live (deliberately hard)
1. Independent security review + operating model + provider permissions (Stripe live, CASP license for crypto-to-fiat).
2. Signed approval file at `LIVE_APPROVAL_FILE` (e.g. `/run/secrets/live-approval.json`), mounted via Modal Secret, never committed.
3. `STRIPE_SECRET_KEY_LIVE` / `BTCPAY_API_KEY_LIVE` in a *separate* `hybridpay-live` Modal Secret (never the `-test` one).
4. Set `LIVE_MODE=true` + redeploy + verify `/health` → `ON-APPROVED` + run the full `docs/modal-deploy-checklist.md` against live-readiness gates.

Without ALL of the above, every live call fails closed with `LIVE_MODE requested without valid LIVE_APPROVAL_FILE`.

# Deployment & rollback (local pilot)

## Up
1. `cp .env.example .env` (fill TEST keys only; keep LIVE_* empty — startup refuses LIVE_MODE=true).
2. `docker compose -f infra/docker-compose.yml up -d postgres redis temporal opa otel`
3. `pnpm install && pnpm test` (unit + api in-memory + property tests must pass).
4. Apply SQL: `psql $DATABASE_URL -f migrations/001_init.sql` (generated from schema.prisma; Prisma migrate in M2).
5. `pnpm --filter @hybridpay/api dev` + `pnpm --filter @hybridpay/worker dev` + `pnpm --filter @hybridpay/terminal dev`.
6. E2E: start api on :3001 then `API_BASE=http://localhost:3001 node tests/e2e/mock-flow.mjs`.

## Rollback
- Code: `git revert` + redeploy previous image; migrations are additive-only (001_init creates tables; never drop in pilot).
- Failed instruction: reconcile run lists UNKNOWN; query original before retry; never switch provider mid-flight.
- Restore: `pg_restore` from nightly dump; after restore run `POST /v1/reconcile/runs` BEFORE restarting worker payouts; verify journal balance per asset.

## Live gate (blocked)
Live release requires: verified provider permissions + operating model + independent security review + operational approval. `LIVE_MODE=true` is rejected unless `LIVE_APPROVAL_FILE` points to a signed approval (not present in MVP).

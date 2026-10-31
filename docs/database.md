# Database — durable layer for the Modal backend

> Never store: card numbers/CVV, wallet seeds/keys, provider live secrets, passwords.
> Only refs, states, minor-unit amounts, tenant ids. Secrets live in env/Modal Secrets.

## Backends
| Backend | When | Path / URL | Notes |
|---|---|---|---|
| SQLite file | local dev, default | `./data/hybridpay.db` (gitignored, auto-created) | zero-config |
| SQLite on Modal Volume | Modal default | `/mnt/data/hybridpay.db` (auto-used when `/mnt/data` exists) | survives redeploys/restarts; NOT the ephemeral container FS |
| SQLite memory | tests | `HYBRIDPAY_DB_MEMORY=1` | isolated per process |
| PostgreSQL | production | `DATABASE_URL=postgresql://user:pass@host:5432/db` | external managed DB (Neon/Supabase/RDS); replaces SQLite entirely |

Backend is selected per process: `DATABASE_URL=postgresql...` → Postgres (via `psycopg2-binary`),
else SQLite. Same tables, same migrations, tenant-scoped queries everywhere.

## Environment
```
# local (defaults work, nothing required)
HYBRIDPAY_DB_PATH=            # override sqlite file location; default ./data/hybridpay.db
DATABASE_URL=                 # empty = SQLite; set postgresql://... for production
API_SHARED_TOKEN=dev-shared-token    # operator role
API_ADMIN_TOKEN=               # admin role (cancel/refund/dispute/execute + dispute)
```
Modal Secret `hybridpay-test` must additionally contain:
`API_ADMIN_TOKEN=<random>`, `DATABASE_URL=<prod url or empty>`,
`HYBRIDPAY_DB_PATH=/mnt/data/hybridpay.db` (or rely on the `/mnt/data` auto-default),
plus the existing `API_SHARED_TOKEN`, provider TEST keys, `MODEL_API_KEY`, `ALLOWED_ORIGINS`.

## Migrations
Versioned SQL in `modal_backend/migrations/` (`001_core`, `002_evm_pag`, `003_indexes`),
tracked in `schema_migrations`, applied idempotently on backend boot (`db.migrate()`).
Fresh database:
```
API_SHARED_TOKEN=x python -c "from modal_backend.db import migrate; print(migrate())"
# -> ['001_core.sql', '002_evm_pag.sql', '003_indexes.sql']
```
Postgres production: the same files apply via `psql $DATABASE_URL -f` in filename order
(the NestJS `migrations/001_init.sql` remains the system of record for `apps/api`).

## Indexes & validation
- Per-tenant list paths: `(tenant)`, `(tenant, state)` on transactions/evm/agreements;
  provider lookups: `provider_ref`, `tx_hash`; idempotency key PK.
- Fail-fast validation in `db.*_upsert` (id/tenant required; EVM chain restricted to
  Sepolia 11155111) — identical on SQLite and Postgres (verified by `test_migrations.py`).

## Operational notes
- Modal: attach the `hybridpay-data` Volume at `/mnt/data` (`modal_backend/app.py`);
  verify with `modal volume list`. The SQLite file persists across deploys.
- Backups: Volume snapshots (Modal) or `pg_dump` for Postgres; restore drill per
  `docs/deployment.md` (reconcile BEFORE restarting workers).
- Never point `HYBRIDPAY_DB_PATH` at `/tmp` on Modal (ephemeral) and never commit `*.db`.

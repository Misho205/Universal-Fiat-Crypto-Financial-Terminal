-- 001_core: fiat sandbox payments + idempotency (portable SQLite/PostgreSQL)
CREATE TABLE IF NOT EXISTS transactions(
    id TEXT PRIMARY KEY, tenant TEXT NOT NULL, state TEXT NOT NULL,
    amount_minor TEXT NOT NULL, currency TEXT NOT NULL DEFAULT 'EUR',
    provider TEXT NOT NULL, provider_ref TEXT NOT NULL DEFAULT '',
    idempotency_key TEXT NOT NULL DEFAULT '', payload_json TEXT NOT NULL DEFAULT '{}',
    created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS idempotency(
    key TEXT PRIMARY KEY, tenant TEXT NOT NULL,
    payload_hash TEXT NOT NULL, response_json TEXT NOT NULL, created_at INTEGER NOT NULL);

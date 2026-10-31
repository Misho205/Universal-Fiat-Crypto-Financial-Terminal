-- 002_evm_pag: EVM Sepolia tracking + programmable agreements (portable SQLite/PostgreSQL)
CREATE TABLE IF NOT EXISTS evm_payments(
    id TEXT PRIMARY KEY, tenant TEXT NOT NULL, chain_id INTEGER NOT NULL,
    to_address TEXT NOT NULL, value_wei TEXT NOT NULL, state TEXT NOT NULL,
    tx_hash TEXT NOT NULL DEFAULT '', replaced_by TEXT NOT NULL DEFAULT '',
    confirmations INTEGER NOT NULL DEFAULT 0, expires_at INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS contract_agreements(
    id TEXT PRIMARY KEY, tenant TEXT NOT NULL, state TEXT NOT NULL,
    document_json TEXT NOT NULL, updated_at INTEGER NOT NULL);

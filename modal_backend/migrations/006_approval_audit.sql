-- 006_approval_audit: cryptographic approval bindings and structured audit events.
-- Portable SQLite and PostgreSQL. All tenant-scoped.
--
-- approval_bindings: one row per sensitive operation digest. The op_digest is
-- UNIQUE per tenant so the same canonical operation cannot be approved twice
-- and any change to a security-critical parameter yields a different digest
-- (previous approvals are invalidated by construction). Single-use with ONE
-- conditional UPDATE for consume so concurrent executors cannot both win.
-- audit_events: structured append-only event log (improved chain with seq in
-- the digest and no field truncation before hashing). No UPDATE or DELETE paths
-- exist in the backend. Independent storage and retention is handled by the
-- export adapter (see AUDIT_ARCHITECTURE.md). Hash chaining detects tampering
-- but is NOT by itself immutability - documented limitation.
-- audit_outbox: durable buffer for export to independently controlled storage.
-- Rows are deleted only after the export destination acknowledges receipt.
CREATE TABLE IF NOT EXISTS approval_bindings(
    id TEXT PRIMARY KEY, tenant TEXT NOT NULL, op_digest TEXT NOT NULL,
    op_type TEXT NOT NULL DEFAULT '', target_id TEXT NOT NULL DEFAULT '',
    maker TEXT NOT NULL DEFAULT '', maker_key TEXT NOT NULL DEFAULT '',
    cred_id TEXT NOT NULL DEFAULT '',
    reason TEXT NOT NULL DEFAULT '', state TEXT NOT NULL DEFAULT 'pending',
    approvals_json TEXT NOT NULL DEFAULT '[]', quorum INTEGER NOT NULL DEFAULT 1,
    expires_at INTEGER NOT NULL DEFAULT 0, consumed_at INTEGER NOT NULL DEFAULT 0,
    op_doc_json TEXT NOT NULL DEFAULT '{}',
    created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL,
    UNIQUE(tenant, op_digest));
CREATE TABLE IF NOT EXISTS audit_events(
    seq INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT NOT NULL,
    tenant TEXT NOT NULL DEFAULT '', ts INTEGER NOT NULL,
    actor TEXT NOT NULL DEFAULT '', action TEXT NOT NULL DEFAULT '',
    resource TEXT NOT NULL DEFAULT '', outcome TEXT NOT NULL DEFAULT '',
    policy TEXT NOT NULL DEFAULT '', correlation_id TEXT NOT NULL DEFAULT '',
    approval_ref TEXT NOT NULL DEFAULT '', detail TEXT NOT NULL DEFAULT '',
    prev_hash TEXT NOT NULL DEFAULT '', hash TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS audit_outbox(
    seq INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT NOT NULL,
    payload_json TEXT NOT NULL DEFAULT '{}', attempts INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL);
CREATE INDEX IF NOT EXISTS idx_bindings_tenant_state ON approval_bindings(tenant, state);
CREATE INDEX IF NOT EXISTS idx_bindings_digest ON approval_bindings(tenant, op_digest);
CREATE INDEX IF NOT EXISTS idx_audit_tenant_seq ON audit_events(tenant, seq);
CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_events(tenant, action);

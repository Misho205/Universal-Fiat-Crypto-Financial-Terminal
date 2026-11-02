-- 004_guardrails: institutional controls (approvals, JIT grants, emergency, audit)
-- Portable SQLite and PostgreSQL. All tenant-scoped. Audit is append-only by convention
-- (no UPDATE or DELETE paths exist in the backend) and chain hashes detect tampering.
CREATE TABLE IF NOT EXISTS approval_intents(
    id TEXT PRIMARY KEY, tenant TEXT NOT NULL, action TEXT NOT NULL,
    target_id TEXT NOT NULL DEFAULT '', amount_minor TEXT NOT NULL DEFAULT '0',
    maker TEXT NOT NULL, maker_key TEXT NOT NULL DEFAULT '',
    reason TEXT NOT NULL DEFAULT '', state TEXT NOT NULL DEFAULT 'pending',
    approvals_json TEXT NOT NULL DEFAULT '[]', quorum INTEGER NOT NULL DEFAULT 1,
    expires_at INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS elevation_grants(
    id TEXT PRIMARY KEY, tenant TEXT NOT NULL, actor TEXT NOT NULL,
    scopes TEXT NOT NULL DEFAULT '', purpose TEXT NOT NULL DEFAULT '',
    granted_by TEXT NOT NULL DEFAULT '', expires_at INTEGER NOT NULL DEFAULT 0,
    state TEXT NOT NULL DEFAULT 'active', created_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS emergency_access(
    id TEXT PRIMARY KEY, tenant TEXT NOT NULL, actor TEXT NOT NULL,
    justification TEXT NOT NULL DEFAULT '', granted_by TEXT NOT NULL DEFAULT '',
    expires_at INTEGER NOT NULL DEFAULT 0, reviewed INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS security_audit(
    seq INTEGER PRIMARY KEY AUTOINCREMENT, tenant TEXT NOT NULL DEFAULT '',
    event TEXT NOT NULL, actor TEXT NOT NULL DEFAULT '',
    detail TEXT NOT NULL DEFAULT '', prev_hash TEXT NOT NULL DEFAULT '',
    hash TEXT NOT NULL DEFAULT '', created_at INTEGER NOT NULL);
CREATE INDEX IF NOT EXISTS idx_intents_tenant_state ON approval_intents(tenant, state);
CREATE INDEX IF NOT EXISTS idx_grants_tenant_actor ON elevation_grants(tenant, actor);
CREATE INDEX IF NOT EXISTS idx_audit_tenant ON security_audit(tenant);

-- 005_rights_pdp: Financial Rights restrictions/appeals + PDP decision audit.
-- Portable SQLite and PostgreSQL. All tenant-scoped. Audit is append-only by
-- convention (no UPDATE/DELETE paths for decisions) and hashes detect tampering.
CREATE TABLE IF NOT EXISTS rights_restrictions(
    id TEXT PRIMARY KEY, tenant TEXT NOT NULL, subject TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT '', ground TEXT NOT NULL DEFAULT '',
    reason_code TEXT NOT NULL DEFAULT '', restriction_type TEXT NOT NULL DEFAULT '',
    authorizer TEXT NOT NULL DEFAULT '', authorizer_role TEXT NOT NULL DEFAULT '',
    evidence_json TEXT NOT NULL DEFAULT '[]', jurisdiction TEXT NOT NULL DEFAULT 'EU_GENERIC',
    state TEXT NOT NULL DEFAULT 'active',
    expires_at INTEGER NOT NULL DEFAULT 0, review_at INTEGER NOT NULL DEFAULT 0,
    document_json TEXT NOT NULL DEFAULT '{}',
    created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS rights_appeals(
    id TEXT PRIMARY KEY, tenant TEXT NOT NULL, restriction_id TEXT NOT NULL DEFAULT '',
    appellant TEXT NOT NULL DEFAULT '', state TEXT NOT NULL DEFAULT 'submitted',
    reviewer TEXT NOT NULL DEFAULT '', decision TEXT NOT NULL DEFAULT '',
    document_json TEXT NOT NULL DEFAULT '{}',
    created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS pdp_decisions(
    seq INTEGER PRIMARY KEY AUTOINCREMENT, tenant TEXT NOT NULL DEFAULT '',
    action TEXT NOT NULL DEFAULT '', allow INTEGER NOT NULL DEFAULT 0,
    reason TEXT NOT NULL DEFAULT '', policy_version TEXT NOT NULL DEFAULT '',
    created_at INTEGER NOT NULL);
CREATE INDEX IF NOT EXISTS idx_rights_tenant_state ON rights_restrictions(tenant, state);
CREATE INDEX IF NOT EXISTS idx_rights_subject ON rights_restrictions(tenant, subject);
CREATE INDEX IF NOT EXISTS idx_appeals_restriction ON rights_appeals(tenant, restriction_id);
CREATE INDEX IF NOT EXISTS idx_pdp_tenant_action ON pdp_decisions(tenant, action);

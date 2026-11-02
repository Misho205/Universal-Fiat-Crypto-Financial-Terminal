-- 007_breakglass_ai_disputes: break-glass sessions, distributed AI control,
-- customer dispute cases and evidence metadata.
-- Portable SQLite and PostgreSQL. All tenant-scoped.
--
-- breakglass_sessions: narrowly scoped emergency sessions. token_hash stores
-- only a digest of the opaque session token, never the token. Scopes are
-- immutable after creation. No balance, transfer, signing, role, tenant, or
-- audit privileges exist in this model by construction.
-- ai_control: single global row (id = global) for the distributed AI security
-- control plane. Replaces reliance on a process-local flag alone.
-- dispute_cases: customer dispute records with linked refs and SLA deadlines.
-- dispute_evidence: metadata ONLY (filename, mime, size, sha256, verdict).
-- File bytes are never stored server-side in the sandbox.
CREATE TABLE IF NOT EXISTS breakglass_sessions(
    id TEXT PRIMARY KEY, tenant TEXT NOT NULL, incident_ref TEXT NOT NULL DEFAULT '',
    justification TEXT NOT NULL DEFAULT '', requestor TEXT NOT NULL DEFAULT '',
    requestor_cred TEXT NOT NULL DEFAULT '', mfa_method TEXT NOT NULL DEFAULT '',
    mfa_ref TEXT NOT NULL DEFAULT '',
    scopes TEXT NOT NULL DEFAULT '', state TEXT NOT NULL DEFAULT 'pending_approval',
    approvals_json TEXT NOT NULL DEFAULT '[]', preauthorized INTEGER NOT NULL DEFAULT 0,
    token_hash TEXT NOT NULL DEFAULT '', expires_at INTEGER NOT NULL DEFAULT 0,
    review_at INTEGER NOT NULL DEFAULT 0, revoked_at INTEGER NOT NULL DEFAULT 0,
    document_json TEXT NOT NULL DEFAULT '{}',
    created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS ai_control(
    id TEXT PRIMARY KEY, inference_enabled INTEGER NOT NULL DEFAULT 1,
    tools_enabled INTEGER NOT NULL DEFAULT 1, features_json TEXT NOT NULL DEFAULT '{}',
    failures INTEGER NOT NULL DEFAULT 0, version INTEGER NOT NULL DEFAULT 1,
    updated_by TEXT NOT NULL DEFAULT '', disabler_cred TEXT NOT NULL DEFAULT '',
    reason TEXT NOT NULL DEFAULT '', updated_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS dispute_cases(
    id TEXT PRIMARY KEY, tenant TEXT NOT NULL, customer TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT '', state TEXT NOT NULL DEFAULT 'submitted',
    transaction_id TEXT NOT NULL DEFAULT '', restriction_id TEXT NOT NULL DEFAULT '',
    agreement_id TEXT NOT NULL DEFAULT '', reviewer TEXT NOT NULL DEFAULT '',
    original_actor TEXT NOT NULL DEFAULT '', decision TEXT NOT NULL DEFAULT '',
    sla_due INTEGER NOT NULL DEFAULT 0, jurisdiction TEXT NOT NULL DEFAULT 'EU_GENERIC',
    document_json TEXT NOT NULL DEFAULT '{}',
    created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS dispute_evidence(
    id TEXT PRIMARY KEY, tenant TEXT NOT NULL, case_id TEXT NOT NULL DEFAULT '',
    filename TEXT NOT NULL DEFAULT '', mime TEXT NOT NULL DEFAULT '',
    size_bytes INTEGER NOT NULL DEFAULT 0, sha256 TEXT NOT NULL DEFAULT '',
    verdict TEXT NOT NULL DEFAULT 'pending', submitted_by TEXT NOT NULL DEFAULT '',
    created_at INTEGER NOT NULL);
CREATE INDEX IF NOT EXISTS idx_breakglass_tenant_state ON breakglass_sessions(tenant, state);
CREATE INDEX IF NOT EXISTS idx_disputes_tenant_state ON dispute_cases(tenant, state);
CREATE INDEX IF NOT EXISTS idx_disputes_customer ON dispute_cases(tenant, customer);
CREATE INDEX IF NOT EXISTS idx_evidence_case ON dispute_evidence(tenant, case_id);

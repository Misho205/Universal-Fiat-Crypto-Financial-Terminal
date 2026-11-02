"""Migration tests: versioned SQL applies cleanly to a fresh database,
is idempotent on rerun, creates all tables + indexes, and tracks versions.

Runs against a temp SQLite file (never touches ./data or Postgres).
"""
import os
import sqlite3

from modal_backend import db


def _fresh(tmp_path, monkeypatch):
    f = tmp_path / "mig.db"
    monkeypatch.delenv("HYBRIDPAY_DB_MEMORY", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("HYBRIDPAY_DB_PATH", str(f))
    db._sqlite_conn = None
    return f


def test_fresh_apply_and_idempotent_rerun(tmp_path, monkeypatch):
    f = _fresh(tmp_path, monkeypatch)
    first = db.migrate()
    assert first == ["001_core.sql", "002_evm_pag.sql", "003_indexes.sql",
                     "004_guardrails.sql", "005_rights_pdp.sql",
                     "006_approval_audit.sql",
                     "007_breakglass_ai_disputes.sql"], first
    assert f.exists()
    assert db.migrate() == []  # rerun applies nothing
    conn = sqlite3.connect(str(f))
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    for t in ("transactions", "idempotency", "evm_payments", "contract_agreements",
              "approval_intents", "elevation_grants", "emergency_access",
              "security_audit", "schema_migrations",
              "rights_restrictions", "rights_appeals", "pdp_decisions",
              "approval_bindings", "audit_events", "audit_outbox",
              "breakglass_sessions", "ai_control",
              "dispute_cases", "dispute_evidence"):
        assert t in tables, t
    indexes = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index'").fetchall()}
    for ix in ("idx_tx_tenant_state", "idx_evm_tenant_state", "idx_pag_tenant_state",
                "idx_tx_provider_ref", "idx_evm_provider_tx",
                "idx_intents_tenant_state", "idx_grants_tenant_actor", "idx_audit_tenant",
                "idx_rights_tenant_state", "idx_rights_subject",
                "idx_appeals_restriction", "idx_pdp_tenant_action",
                "idx_bindings_tenant_state", "idx_bindings_digest",
                "idx_audit_tenant_seq", "idx_audit_action",
                "idx_breakglass_tenant_state",
                "idx_disputes_tenant_state", "idx_disputes_customer",
                "idx_evidence_case"):
        assert ix in indexes, ix
    conn.close()
    db._sqlite_conn = None
    monkeypatch.delenv("HYBRIDPAY_DB_PATH", raising=False)


def test_validation_rejects_bad_rows(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    db.migrate()
    import pytest
    # fail-fast validation at the DB facade (works the same on SQLite + Postgres)
    with pytest.raises(ValueError, match="id is required"):
        db.tx_upsert({"id": None, "tenant": "t", "state": "pending"})
    with pytest.raises(ValueError, match="tenant is required"):
        db.tx_upsert({"id": "x", "tenant": "", "state": "pending"})
    with pytest.raises(ValueError, match="Sepolia"):
        db.evm_upsert({"id": "e1", "tenant": "t", "chain_id": 1, "to": "0x",
                       "value_wei": "1", "state": "requested"})
    with pytest.raises(ValueError, match="tenant"):
        db.pag_put({"id": "p1", "tenant": "", "state": "draft"})
    db._sqlite_conn = None
    monkeypatch.delenv("HYBRIDPAY_DB_PATH", raising=False)
    assert os.environ.get("HYBRIDPAY_DB_PATH") is None

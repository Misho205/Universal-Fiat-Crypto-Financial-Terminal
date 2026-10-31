"""Durable store: SQLite (local/dev/tests) or PostgreSQL (production/Modal).

Persistence rule: NEVER rely on the container filesystem on Modal.
- Modal: attach the `hybridpay-data` Volume at /mnt/data AND/OR set DATABASE_URL
  to an external Postgres (Neon/Supabase/RDS). SQLite file then lives on the
  Volume (/mnt/data/hybridpay.db), not the ephemeral container disk.
- Local: ./data/hybridpay.db (directory auto-created).
- Tests: HYBRIDPAY_DB_MEMORY=1 forces shared in-memory SQLite.
- Production Postgres: DATABASE_URL=postgresql://... (psycopg2). Same tables,
  same versioned migrations, tenant-scoped queries, no secrets/PAN stored.

Schema is versioned in modal_backend/migrations/*.sql, tracked in
schema_migrations. migrate() is idempotent — safe to run on every boot.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
import time
from typing import Any

_lock = threading.Lock()
_sqlite_conn: sqlite3.Connection | None = None

_MIGRATIONS_DIR = os.path.join(os.path.dirname(__file__), "migrations")


def backend_kind() -> str:
    """'postgres' when DATABASE_URL is set, else 'sqlite'."""
    if os.environ.get("HYBRIDPAY_DB_MEMORY") == "1":
        return "sqlite"
    url = os.environ.get("DATABASE_URL", "")
    if url.startswith("postgres"):
        return "postgres"
    return "sqlite"


def db_path() -> str:
    if os.environ.get("HYBRIDPAY_DB_MEMORY") == "1":
        return ":memory:"
    explicit = os.environ.get("HYBRIDPAY_DB_PATH", "")
    if explicit:
        return explicit
    if os.path.isdir("/mnt/data"):  # Modal Volume mount point
        return "/mnt/data/hybridpay.db"
    return "./data/hybridpay.db"


def _migration_files() -> list[str]:
    files = sorted(f for f in os.listdir(_MIGRATIONS_DIR) if f.endswith(".sql"))
    return [os.path.join(_MIGRATIONS_DIR, f) for f in files]


def _split_statements(sql: str) -> list[str]:
    return [s.strip() for s in sql.split(";") if s.strip()]


def _sqlite() -> sqlite3.Connection:
    global _sqlite_conn
    with _lock:
        if _sqlite_conn is not None:
            return _sqlite_conn
        path = db_path()
        if path != ":memory:":
            directory = os.path.dirname(path) or "."
            os.makedirs(directory, exist_ok=True)
        _sqlite_conn = sqlite3.connect(path, check_same_thread=False)
        _sqlite_conn.row_factory = sqlite3.Row
        return _sqlite_conn


def _pg():
    """Short-lived Postgres connection (serverless-friendly: no pool to exhaust)."""
    try:
        import psycopg2
        import psycopg2.extras
    except ImportError as exc:
        raise RuntimeError("DATABASE_URL is set but psycopg2 is not installed") from exc
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    return conn


def _pg_rows(cur) -> list[dict[str, Any]]:
    import psycopg2.extras
    return [dict(r) for r in cur.fetchall()]


def migrate() -> list[str]:
    """Apply pending versioned migrations. Returns applied filenames. Idempotent."""
    applied: list[str] = []
    if backend_kind() == "postgres":
        conn = _pg()
        try:
            with conn.cursor() as cur:
                cur.execute("CREATE TABLE IF NOT EXISTS schema_migrations(filename TEXT PRIMARY KEY, applied_at INTEGER)")
                done = {r[0] for r in _fetchall_pg(cur, "SELECT filename FROM schema_migrations")}
                for path in _migration_files():
                    name = os.path.basename(path)
                    if name in done:
                        continue
                    sql = open(path, encoding="utf-8").read().replace("?", "%s")
                    for stmt in _split_statements(sql):
                        cur.execute(stmt)
                    cur.execute("INSERT INTO schema_migrations(filename, applied_at) VALUES (%s, %s)",
                                (name, int(time.time())))
                    applied.append(name)
            conn.commit()
        finally:
            conn.close()
        return applied
    conn = _sqlite()
    with _lock:
        conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations(filename TEXT PRIMARY KEY, applied_at INTEGER)")
        done = {r[0] for r in conn.execute("SELECT filename FROM schema_migrations").fetchall()}
        for path in _migration_files():
            name = os.path.basename(path)
            if name in done:
                continue
            for stmt in _split_statements(open(path, encoding="utf-8").read()):
                conn.execute(stmt)
            conn.execute("INSERT INTO schema_migrations(filename, applied_at) VALUES (?, ?)",
                         (name, int(time.time())))
            applied.append(name)
        conn.commit()
    return applied


def _fetchall_pg(cur, query: str, params: tuple = ()) -> list:
    cur.execute(query, params)
    return cur.fetchall()


def _q(sqlite_sql: str) -> str:
    """Translate ? placeholders for the active backend."""
    if backend_kind() == "postgres":
        return sqlite_sql.replace("?", "%s")
    return sqlite_sql


def _exec_write(sqlite_sql: str, params: tuple = ()) -> None:
    if backend_kind() == "postgres":
        conn = _pg()
        try:
            with conn.cursor() as cur:
                cur.execute(sqlite_sql.replace("?", "%s"), params)
            conn.commit()
        finally:
            conn.close()
        return
    conn = _sqlite()
    with _lock:
        conn.execute(sqlite_sql, params)
        conn.commit()


def _fetch_one(sqlite_sql: str, params: tuple = ()) -> dict[str, Any] | None:
    if backend_kind() == "postgres":
        conn = _pg()
        try:
            import psycopg2.extras
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sqlite_sql.replace("?", "%s"), params)
                row = cur.fetchone()
                return dict(row) if row else None
        finally:
            conn.close()
    conn = _sqlite()
    with _lock:
        row = conn.execute(sqlite_sql, params).fetchone()
    return dict(row) if row else None


def _fetch_all(sqlite_sql: str, params: tuple = ()) -> list[dict[str, Any]]:
    if backend_kind() == "postgres":
        conn = _pg()
        try:
            import psycopg2.extras
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sqlite_sql.replace("?", "%s"), params)
                return [dict(r) for r in cur.fetchall()]
        finally:
            conn.close()
    conn = _sqlite()
    with _lock:
        rows = conn.execute(sqlite_sql, params).fetchall()
    return [dict(r) for r in rows]


def tx_by_provider_ref(provider_ref: str) -> list[dict[str, Any]]:
    rows = _fetch_all("SELECT id, tenant FROM transactions WHERE provider_ref=?", (provider_ref,))
    return [{"id": r["id"], "tenant": r["tenant"]} for r in rows]


def _connect():  # legacy accessor (SQLite path only; prefer tx_get/tx_by_provider_ref).
    return _sqlite()


def reset_for_tests() -> None:
    """Drop all rows (tests only). Keeps schema. Resets sqlite singleton for path changes."""
    global _sqlite_conn
    if backend_kind() == "sqlite":
        with _lock:
            if _sqlite_conn is not None:
                try:
                    _sqlite_conn.close()
                except Exception:
                    pass
                _sqlite_conn = None
        conn = _sqlite()
        with _lock:
            for table in ("transactions", "idempotency", "evm_payments",
                          "contract_agreements", "schema_migrations"):
                try:
                    conn.execute(f"DELETE FROM {table}")
                except Exception:
                    pass
            conn.commit()
        migrate()
        return
    # postgres test database: clear rows only
    for table in ("transactions", "idempotency", "evm_payments", "contract_agreements"):
        _exec_write(f"DELETE FROM {table}")


# Ensure schema exists on import (idempotent; cheap after first boot).
try:
    migrate()
except Exception:
    pass  # explicit migrate() calls in tests/startup surface real errors


def tx_upsert(rec: dict[str, Any]) -> None:
    if not rec.get("id") or not isinstance(rec.get("id"), str):
        raise ValueError("tx_upsert: id is required (TEXT PRIMARY KEY)")
    if not rec.get("tenant") or not isinstance(rec.get("tenant"), str):
        raise ValueError("tx_upsert: tenant is required (tenant-scoped queries)")
    now = int(time.time())
    _exec_write(
        """INSERT INTO transactions(id,tenant,state,amount_minor,currency,provider,provider_ref,
             idempotency_key,payload_json,created_at,updated_at)
           VALUES(?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(id) DO UPDATE SET state=excluded.state, provider_ref=excluded.provider_ref,
             updated_at=excluded.updated_at""",
        (rec["id"], rec["tenant"], rec["state"], rec.get("amountMinor", rec.get("amount_minor", "0")),
         rec.get("currency", "EUR"), rec.get("provider", "mock"),
         rec.get("providerRef", rec.get("provider_ref", "")),
         rec.get("idempotencyKey", rec.get("idempotency_key", "")),
         json.dumps(rec.get("payload", {})), rec.get("createdAt", now), now),
    )


def tx_get(tx_id: str, tenant: str) -> dict[str, Any] | None:
    row = _fetch_one("SELECT * FROM transactions WHERE id=? AND tenant=?", (tx_id, tenant))
    if not row:
        return None
    return {"id": row["id"], "tenant": row["tenant"], "state": row["state"],
            "amountMinor": row["amount_minor"], "currency": row["currency"],
            "provider": row["provider"], "providerRef": row["provider_ref"],
            "idempotencyKey": row["idempotency_key"], "payload": json.loads(row["payload_json"] or "{}")}


def tx_list(tenant: str, limit: int = 50) -> list[dict[str, Any]]:
    rows = _fetch_all("SELECT * FROM transactions WHERE tenant=? ORDER BY created_at DESC LIMIT ?",
                      (tenant, limit))
    return [{"id": r["id"], "state": r["state"], "amountMinor": r["amount_minor"],
             "currency": r["currency"], "provider": r["provider"],
             "providerRef": r["provider_ref"]} for r in rows]


def idem_get(key: str) -> dict[str, Any] | None:
    row = _fetch_one("SELECT * FROM idempotency WHERE key=?", (key,))
    if not row:
        return None
    return {"tenant": row["tenant"], "payload_hash": row["payload_hash"],
            "response": json.loads(row["response_json"])}


def idem_put(key: str, tenant: str, payload: dict[str, Any], response: dict[str, Any]) -> None:
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    _exec_write(
        """INSERT INTO idempotency(key,tenant,payload_hash,response_json,created_at)
           VALUES(?,?,?,?,?) ON CONFLICT(key) DO NOTHING""",
        (key, tenant, digest, json.dumps(response), int(time.time())),
    )


# ---------- EVM Sepolia tracked payments ----------

def evm_upsert(rec: dict[str, Any]) -> None:
    if not rec.get("id") or not rec.get("tenant"):
        raise ValueError("evm_upsert: id and tenant are required")
    if rec.get("chain_id") != 11155111:
        raise ValueError("evm_upsert: only Sepolia chain_id 11155111 is stored")
    now = int(time.time())
    _exec_write(
        """INSERT INTO evm_payments(id,tenant,chain_id,to_address,value_wei,state,
             tx_hash,replaced_by,confirmations,expires_at,created_at,updated_at)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(id) DO UPDATE SET state=excluded.state, tx_hash=excluded.tx_hash,
             replaced_by=excluded.replaced_by, confirmations=excluded.confirmations,
             updated_at=excluded.updated_at""",
        (rec["id"], rec["tenant"], rec["chain_id"], rec["to"], rec["value_wei"],
         rec["state"], rec.get("tx_hash", ""), rec.get("replaced_by", ""),
         rec.get("confirmations", 0), rec.get("expires_at", 0),
         rec.get("created_at", now), now),
    )


def evm_get(pid: str, tenant: str) -> dict[str, Any] | None:
    row = _fetch_one("SELECT * FROM evm_payments WHERE id=? AND tenant=?", (pid, tenant))
    if not row:
        return None
    return {"id": row["id"], "tenant": row["tenant"], "chain_id": row["chain_id"],
            "to": row["to_address"], "value_wei": row["value_wei"], "state": row["state"],
            "tx_hash": row["tx_hash"], "replaced_by": row["replaced_by"],
            "confirmations": row["confirmations"], "expires_at": row["expires_at"]}


def evm_list(tenant: str, limit: int = 50) -> list[dict[str, Any]]:
    rows = _fetch_all("SELECT * FROM evm_payments WHERE tenant=? ORDER BY created_at DESC LIMIT ?",
                      (tenant, limit))
    return [{"id": r["id"], "chain_id": r["chain_id"], "to": r["to_address"],
             "value_wei": r["value_wei"], "state": r["state"], "tx_hash": r["tx_hash"],
             "confirmations": r["confirmations"]} for r in rows]


# ---------- programmable agreements ----------

def pag_put(doc: dict[str, Any]) -> None:
    if not doc.get("id") or not doc.get("tenant"):
        raise ValueError("pag_put: id and tenant are required")
    _exec_write(
        """INSERT INTO contract_agreements(id,tenant,state,document_json,updated_at)
           VALUES(?,?,?, ?,?) ON CONFLICT(id) DO UPDATE SET state=excluded.state,
           document_json=excluded.document_json, updated_at=excluded.updated_at""",
        (doc["id"], doc["tenant"], doc["state"], json.dumps(doc), int(time.time())),
    )


def pag_get(ag_id: str, tenant: str) -> dict[str, Any] | None:
    row = _fetch_one("SELECT * FROM contract_agreements WHERE id=? AND tenant=?", (ag_id, tenant))
    if not row:
        return None
    return json.loads(row["document_json"])


def pag_list(tenant: str, limit: int = 50) -> list[dict[str, Any]]:
    rows = _fetch_all("SELECT document_json FROM contract_agreements WHERE tenant=? LIMIT ?",
                      (tenant, limit))
    out = []
    for r in rows:
        d = json.loads(r["document_json"])
        out.append({"id": d["id"], "state": d["state"], "version": d.get("version", 1),
                    "updatedAt": d.get("updatedAt", "")})
    return out

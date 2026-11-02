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
                          "contract_agreements", "approval_intents",
                          "elevation_grants", "emergency_access",
                          "security_audit", "schema_migrations"):
                try:
                    conn.execute(f"DELETE FROM {table}")
                except Exception:
                    pass
            conn.commit()
        migrate()
        return
    # postgres test database: clear rows only
    for table in ("transactions", "idempotency", "evm_payments", "contract_agreements",
                  "approval_intents", "elevation_grants", "emergency_access",
                  "security_audit"):
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


def tx_list(tenant: str, limit: int = 50, offset: int = 0,
           state: str = "") -> list[dict[str, Any]]:
    lim = max(1, min(limit, 200))
    off = max(0, offset)
    if state:
        rows = _fetch_all("SELECT * FROM transactions WHERE tenant=? AND state=? "
                          "ORDER BY created_at DESC LIMIT ? OFFSET ?",
                          (tenant, state, lim, off))
    else:
        rows = _fetch_all("SELECT * FROM transactions WHERE tenant=? "
                          "ORDER BY created_at DESC LIMIT ? OFFSET ?",
                          (tenant, lim, off))
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


def evm_list(tenant: str, limit: int = 50, offset: int = 0,
             state: str = "") -> list[dict[str, Any]]:
    lim = max(1, min(limit, 200))
    off = max(0, offset)
    if state:
        rows = _fetch_all("SELECT * FROM evm_payments WHERE tenant=? AND state=? "
                          "ORDER BY created_at DESC LIMIT ? OFFSET ?",
                          (tenant, state, lim, off))
    else:
        rows = _fetch_all("SELECT * FROM evm_payments WHERE tenant=? "
                          "ORDER BY created_at DESC LIMIT ? OFFSET ?",
                          (tenant, lim, off))
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


def pag_list(tenant: str, limit: int = 50, offset: int = 0,
             state: str = "") -> list[dict[str, Any]]:
    lim = max(1, min(limit, 200))
    off = max(0, offset)
    if state:
        rows = _fetch_all("SELECT document_json FROM contract_agreements "
                          "WHERE tenant=? AND state=? LIMIT ? OFFSET ?",
                          (tenant, state, lim, off))
    else:
        rows = _fetch_all("SELECT document_json FROM contract_agreements WHERE tenant=? LIMIT ? OFFSET ?",
                          (tenant, lim, off))
    out = []
    for r in rows:
        d = json.loads(r["document_json"])
        out.append({"id": d["id"], "state": d["state"], "version": d.get("version", 1),
                    "updatedAt": d.get("updatedAt", "")})
    return out


# ---------- institutional guardrails (approvals, JIT grants, emergency, audit) ----------

def intent_put(doc: dict[str, Any]) -> None:
    if not doc.get("id") or not doc.get("tenant") or not doc.get("action"):
        raise ValueError("intent_put: id, tenant and action are required")
    now = int(time.time())
    _exec_write(
        """INSERT INTO approval_intents(id,tenant,action,target_id,amount_minor,maker,
             maker_key,reason,state,approvals_json,quorum,expires_at,created_at,updated_at)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(id) DO UPDATE SET state=excluded.state,
             approvals_json=excluded.approvals_json, updated_at=excluded.updated_at""",
        (doc["id"], doc["tenant"], doc["action"], doc.get("targetId", ""),
         str(doc.get("amountMinor", "0")), doc.get("maker", ""), doc.get("makerKey", ""),
         str(doc.get("reason", ""))[:500], doc.get("state", "pending"),
         json.dumps(doc.get("approvals", [])), int(doc.get("quorum", 1)),
         int(doc.get("expiresAt", 0)), int(doc.get("createdAt", now)), now),
    )


def intent_get(intent_id: str, tenant: str) -> dict[str, Any] | None:
    row = _fetch_one("SELECT * FROM approval_intents WHERE id=? AND tenant=?", (intent_id, tenant))
    if not row:
        return None
    return {"id": row["id"], "tenant": row["tenant"], "action": row["action"],
            "targetId": row["target_id"], "amountMinor": row["amount_minor"],
            "maker": row["maker"], "makerKey": row["maker_key"], "reason": row["reason"],
            "state": row["state"], "approvals": json.loads(row["approvals_json"] or "[]"),
            "quorum": row["quorum"], "expiresAt": row["expires_at"]}


def intent_list(tenant: str, limit: int = 50, state: str = "") -> list[dict[str, Any]]:
    lim = max(1, min(limit, 200))
    if state:
        rows = _fetch_all("SELECT * FROM approval_intents WHERE tenant=? AND state=? "
                          "ORDER BY created_at DESC LIMIT ?", (tenant, state, lim))
    else:
        rows = _fetch_all("SELECT * FROM approval_intents WHERE tenant=? "
                          "ORDER BY created_at DESC LIMIT ?", (tenant, lim))
    return [{"id": r["id"], "action": r["action"], "targetId": r["target_id"],
             "state": r["state"], "maker": r["maker"], "quorum": r["quorum"],
             "approvals": json.loads(r["approvals_json"] or "[]")} for r in rows]


def grant_put(doc: dict[str, Any]) -> None:
    if not doc.get("id") or not doc.get("tenant") or not doc.get("actor"):
        raise ValueError("grant_put: id, tenant and actor are required")
    _exec_write(
        """INSERT INTO elevation_grants(id,tenant,actor,scopes,purpose,granted_by,
             expires_at,state,created_at) VALUES(?,?,?,?,?,?,?,?,?)
           ON CONFLICT(id) DO UPDATE SET state=excluded.state""",
        (doc["id"], doc["tenant"], doc["actor"], ",".join(doc.get("scopes", [])),
         str(doc.get("purpose", ""))[:500], doc.get("grantedBy", ""),
         int(doc.get("expiresAt", 0)), doc.get("state", "active"), int(time.time())),
    )


def active_grants(tenant: str, actor: str, now: int | None = None) -> list[dict[str, Any]]:
    ts = now if now is not None else int(time.time())
    rows = _fetch_all("SELECT * FROM elevation_grants WHERE tenant=? AND actor=? AND state='active'",
                      (tenant, actor))
    out = []
    for r in rows:
        if ts < int(r["expires_at"]):
            out.append({"id": r["id"], "scopes": r["scopes"].split(",") if r["scopes"] else [],
                        "purpose": r["purpose"], "expiresAt": r["expires_at"]})
        else:
            _exec_write("UPDATE elevation_grants SET state='expired' WHERE id=?", (r["id"],))
    return out


def emergency_put(doc: dict[str, Any]) -> None:
    if not doc.get("id") or not doc.get("tenant") or not doc.get("actor"):
        raise ValueError("emergency_put: id, tenant and actor are required")
    if not str(doc.get("justification", "")).strip():
        raise ValueError("emergency_put: justification is required")
    _exec_write(
        """INSERT INTO emergency_access(id,tenant,actor,justification,granted_by,
             expires_at,reviewed,created_at) VALUES(?,?,?,?,?,?,?,?)""",
        (doc["id"], doc["tenant"], doc["actor"], str(doc["justification"])[:1000],
         doc.get("grantedBy", ""), int(doc.get("expiresAt", 0)), 0, int(time.time())),
    )


def emergency_list(tenant: str, limit: int = 50) -> list[dict[str, Any]]:
    rows = _fetch_all("SELECT * FROM emergency_access WHERE tenant=? ORDER BY created_at DESC LIMIT ?",
                      (tenant, max(1, min(limit, 200))))
    return [{"id": r["id"], "actor": r["actor"], "justification": r["justification"],
             "grantedBy": r["granted_by"], "expiresAt": r["expires_at"],
             "reviewed": bool(r["reviewed"])} for r in rows]


def emergency_mark_reviewed(emergency_id: str, tenant: str, reviewer: str) -> bool:
    row = _fetch_one("SELECT * FROM emergency_access WHERE id=? AND tenant=?", (emergency_id, tenant))
    if not row or row["actor"] == reviewer:
        return False  # reviewer must be independent of the emergency actor
    _exec_write("UPDATE emergency_access SET reviewed=1 WHERE id=?", (emergency_id,))
    return True


def audit_append(tenant: str, event: str, actor: str, detail: str) -> dict[str, Any]:
    # Per-tenant chain: prev links the last event OF THE SAME TENANT, so one
    # tenant's audit trail verifies independently (tenant isolation).
    last = _fetch_one("SELECT hash FROM security_audit WHERE tenant=? ORDER BY seq DESC LIMIT 1",
                      (tenant,))
    prev = last["hash"] if last else "GENESIS"
    ts = int(time.time())
    digest = hashlib.sha256(f"{prev}|{tenant}|{event}|{actor}|{detail}|{ts}".encode()).hexdigest()
    conn_kind = backend_kind()
    if conn_kind == "postgres":
        conn = _pg()
        try:
            with conn.cursor() as cur:
                cur.execute("INSERT INTO security_audit(tenant,event,actor,detail,prev_hash,hash,created_at)"
                            " VALUES (%s,%s,%s,%s,%s,%s,%s)", (tenant, event[:120], actor[:120],
                            detail[:1000], prev, digest, ts))
            conn.commit()
        finally:
            conn.close()
    else:
        _exec_write("INSERT INTO security_audit(tenant,event,actor,detail,prev_hash,hash,created_at)"
                    " VALUES (?,?,?,?,?,?,?)",
                    (tenant, event[:120], actor[:120], detail[:1000], prev, digest, ts))
    return {"hash": digest, "prevHash": prev, "ts": ts}


def audit_list(tenant: str, limit: int = 100) -> list[dict[str, Any]]:
    rows = _fetch_all("SELECT seq,tenant,event,actor,detail,prev_hash,hash,created_at FROM security_audit "
                      "WHERE tenant=? ORDER BY seq DESC LIMIT ?", (tenant, max(1, min(limit, 200))))
    return [{"seq": r["seq"], "event": r["event"], "actor": r["actor"], "detail": r["detail"],
             "prevHash": r["prev_hash"], "hash": r["hash"], "ts": r["created_at"]} for r in rows]


def audit_verify(tenant: str) -> bool:
    rows = _fetch_all("SELECT seq,tenant,event,actor,detail,prev_hash,hash,created_at FROM security_audit "
                      "WHERE tenant=? ORDER BY seq ASC LIMIT 2000", (tenant,))
    prev = "GENESIS"
    for r in rows:
        if r["prev_hash"] != prev:
            return False
        expect = hashlib.sha256(
            f"{r['prev_hash']}|{r['tenant']}|{r['event']}|{r['actor']}|{r['detail']}|{r['created_at']}"
            .encode()).hexdigest()
        if expect != r["hash"]:
            return False
        prev = r["hash"]
    return True

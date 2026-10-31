"""Durable transaction + idempotency store (SQLite file by default).

Modal containers are ephemeral: this module persists OUTSIDE the container when
HYBRIDPAY_DB_PATH points at a mounted volume / local ./data dir. Production uses
external PostgreSQL via apps/api (system of record); this SQLite layer is the
durable store for the Modal sandbox backend (hackathon + local dev).

- Default: ./data/hybridpay.db (created on first write; directory auto-created).
- Tests: HYBRIDPAY_DB_MEMORY=1 forces shared in-memory DB (isolated per process).
- Never stores PAN/CVV/secrets — only provider refs, states, minor-unit amounts.
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
_conn: sqlite3.Connection | None = None


def db_path() -> str:
    if os.environ.get("HYBRIDPAY_DB_MEMORY") == "1":
        return ":memory:"
    return os.environ.get("HYBRIDPAY_DB_PATH", "./data/hybridpay.db")


def _connect() -> sqlite3.Connection:
    global _conn
    with _lock:
        if _conn is not None:
            return _conn
        path = db_path()
        if path != ":memory:":
            directory = os.path.dirname(path) or "."
            os.makedirs(directory, exist_ok=True)
        _conn = sqlite3.connect(path, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.execute(
            """CREATE TABLE IF NOT EXISTS transactions(
                id TEXT PRIMARY KEY, tenant TEXT NOT NULL, state TEXT NOT NULL,
                amount_minor TEXT NOT NULL, currency TEXT NOT NULL DEFAULT 'EUR',
                provider TEXT NOT NULL, provider_ref TEXT NOT NULL DEFAULT '',
                idempotency_key TEXT NOT NULL DEFAULT '', payload_json TEXT NOT NULL DEFAULT '{}',
                created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL)"""
        )
        _conn.execute(
            """CREATE TABLE IF NOT EXISTS idempotency(
                key TEXT PRIMARY KEY, tenant TEXT NOT NULL,
                payload_hash TEXT NOT NULL, response_json TEXT NOT NULL, created_at INTEGER NOT NULL)"""
        )
        _conn.execute("CREATE INDEX IF NOT EXISTS idx_tx_tenant ON transactions(tenant)")
        _conn.execute(
            """CREATE TABLE IF NOT EXISTS evm_payments(
                id TEXT PRIMARY KEY, tenant TEXT NOT NULL, chain_id INTEGER NOT NULL,
                to_address TEXT NOT NULL, value_wei TEXT NOT NULL, state TEXT NOT NULL,
                tx_hash TEXT NOT NULL DEFAULT '', replaced_by TEXT NOT NULL DEFAULT '',
                confirmations INTEGER NOT NULL DEFAULT 0, expires_at INTEGER NOT NULL DEFAULT 0,
                created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL)"""
        )
        _conn.execute("CREATE INDEX IF NOT EXISTS idx_evm_tenant ON evm_payments(tenant)")
        _conn.execute(
            """CREATE TABLE IF NOT EXISTS contract_agreements(
                id TEXT PRIMARY KEY, tenant TEXT NOT NULL, state TEXT NOT NULL,
                document_json TEXT NOT NULL, updated_at INTEGER NOT NULL)"""
        )
        _conn.execute("CREATE INDEX IF NOT EXISTS idx_pag_tenant ON contract_agreements(tenant)")
        _conn.commit()
        return _conn


def reset_for_tests() -> None:
    """Drop all rows (tests only). Keeps schema."""
    c = _connect()
    with _lock:
        c.execute("DELETE FROM transactions")
        c.execute("DELETE FROM idempotency")
        c.execute("DELETE FROM evm_payments")
        c.execute("DELETE FROM contract_agreements")
        c.commit()


def tx_upsert(rec: dict[str, Any]) -> None:
    c = _connect()
    now = int(time.time())
    with _lock:
        c.execute(
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
        c.commit()


def tx_get(tx_id: str, tenant: str) -> dict[str, Any] | None:
    c = _connect()
    with _lock:
        row = c.execute("SELECT * FROM transactions WHERE id=? AND tenant=?", (tx_id, tenant)).fetchone()
    if not row:
        return None
    return {"id": row["id"], "tenant": row["tenant"], "state": row["state"],
            "amountMinor": row["amount_minor"], "currency": row["currency"],
            "provider": row["provider"], "providerRef": row["provider_ref"],
            "idempotencyKey": row["idempotency_key"], "payload": json.loads(row["payload_json"] or "{}")}


def tx_list(tenant: str, limit: int = 50) -> list[dict[str, Any]]:
    c = _connect()
    with _lock:
        rows = c.execute("SELECT * FROM transactions WHERE tenant=? ORDER BY created_at DESC LIMIT ?",
                         (tenant, limit)).fetchall()
    return [{"id": r["id"], "state": r["state"], "amountMinor": r["amount_minor"],
             "currency": r["currency"], "provider": r["provider"],
             "providerRef": r["provider_ref"]} for r in rows]


def idem_get(key: str) -> dict[str, Any] | None:
    c = _connect()
    with _lock:
        row = c.execute("SELECT * FROM idempotency WHERE key=?", (key,)).fetchone()
    if not row:
        return None
    return {"tenant": row["tenant"], "payload_hash": row["payload_hash"],
            "response": json.loads(row["response_json"])}


def idem_put(key: str, tenant: str, payload: dict[str, Any], response: dict[str, Any]) -> None:
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    c = _connect()
    with _lock:
        c.execute(
            """INSERT INTO idempotency(key,tenant,payload_hash,response_json,created_at)
               VALUES(?,?,?,?,?) ON CONFLICT(key) DO NOTHING""",
            (key, tenant, digest, json.dumps(response), int(time.time())),
        )
        c.commit()


# ---------- EVM Sepolia tracked payments ----------

def evm_upsert(rec: dict[str, Any]) -> None:
    now = int(time.time())
    c = _connect()
    with _lock:
        c.execute(
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
        c.commit()


def evm_get(pid: str, tenant: str) -> dict[str, Any] | None:
    c = _connect()
    with _lock:
        row = c.execute("SELECT * FROM evm_payments WHERE id=? AND tenant=?", (pid, tenant)).fetchone()
    if not row:
        return None
    return {"id": row["id"], "tenant": row["tenant"], "chain_id": row["chain_id"],
            "to": row["to_address"], "value_wei": row["value_wei"], "state": row["state"],
            "tx_hash": row["tx_hash"], "replaced_by": row["replaced_by"],
            "confirmations": row["confirmations"], "expires_at": row["expires_at"]}


def evm_list(tenant: str, limit: int = 50) -> list[dict[str, Any]]:
    c = _connect()
    with _lock:
        rows = c.execute("SELECT * FROM evm_payments WHERE tenant=? ORDER BY created_at DESC LIMIT ?",
                         (tenant, limit)).fetchall()
    return [{"id": r["id"], "chain_id": r["chain_id"], "to": r["to_address"],
             "value_wei": r["value_wei"], "state": r["state"], "tx_hash": r["tx_hash"],
             "confirmations": r["confirmations"]} for r in rows]


# ---------- programmable agreements ----------

def pag_put(doc: dict[str, Any]) -> None:
    c = _connect()
    with _lock:
        c.execute(
            """INSERT INTO contract_agreements(id,tenant,state,document_json,updated_at)
               VALUES(?,?,?, ?,?) ON CONFLICT(id) DO UPDATE SET state=excluded.state,
               document_json=excluded.document_json, updated_at=excluded.updated_at""",
            (doc["id"], doc["tenant"], doc["state"], json.dumps(doc), int(time.time())),
        )
        c.commit()


def pag_get(ag_id: str, tenant: str) -> dict[str, Any] | None:
    c = _connect()
    with _lock:
        row = c.execute("SELECT * FROM contract_agreements WHERE id=? AND tenant=?",
                        (ag_id, tenant)).fetchone()
    if not row:
        return None
    return json.loads(row["document_json"])


def pag_list(tenant: str, limit: int = 50) -> list[dict[str, Any]]:
    c = _connect()
    with _lock:
        rows = c.execute("SELECT document_json FROM contract_agreements WHERE tenant=? LIMIT ?",
                         (tenant, limit)).fetchall()
    out = []
    for r in rows:
        d = json.loads(r["document_json"])
        out.append({"id": d["id"], "state": d["state"], "version": d.get("version", 1),
                    "updatedAt": d.get("updatedAt", "")})
    return out

"""Durable store helpers for Financial Rights restrictions/appeals + PDP audit.

Tables live in migration 005_rights_pdp.sql. All queries are tenant-scoped.
Restriction/appeal documents are stored as JSON (single source of truth) with
indexed columns for queries. PDP decisions are append-only.
"""
from __future__ import annotations

import json
import time
from typing import Any

from . import db as _db


def _now() -> int:
    return int(time.time())


# ---------- restrictions ----------

def restriction_put(doc: dict[str, Any]) -> None:
    if not doc.get("id") or not doc.get("tenant"):
        raise ValueError("restriction_put: id and tenant are required")
    now = _now()
    _db._exec_write(
        """INSERT INTO rights_restrictions(id,tenant,subject,category,ground,reason_code,
             restriction_type,authorizer,authorizer_role,evidence_json,jurisdiction,
             state,expires_at,review_at,document_json,created_at,updated_at)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?, ?,?)
           ON CONFLICT(id) DO UPDATE SET state=excluded.state,
             document_json=excluded.document_json, updated_at=excluded.updated_at,
             expires_at=excluded.expires_at, review_at=excluded.review_at""",
        (doc["id"], doc["tenant"], doc.get("subject", ""), doc.get("category", ""),
         doc.get("ground", ""), doc.get("reasonCode", ""), doc.get("restrictionType", ""),
         doc.get("authorizer", ""), doc.get("authorizerRole", ""),
         json.dumps(doc.get("evidence", [])), doc.get("jurisdiction", "EU_GENERIC"),
         doc.get("state", "active"), int(doc.get("expiresAt", 0)),
         int(doc.get("reviewAt", 0)), json.dumps(doc), int(doc.get("createdAt", now)), now),
    )


def restriction_get(rid: str, tenant: str) -> dict[str, Any] | None:
    row = _db._fetch_one(
        "SELECT document_json FROM rights_restrictions WHERE id=? AND tenant=?",
        (rid, tenant),
    )
    return json.loads(row["document_json"]) if row else None


def restriction_list(
    tenant: str, limit: int = 50, state: str = "", subject: str = ""
) -> list[dict[str, Any]]:
    lim = max(1, min(limit, 200))
    if state:
        rows = _db._fetch_all(
            "SELECT document_json FROM rights_restrictions WHERE tenant=? AND state=? "
            "ORDER BY created_at DESC LIMIT ?",
            (tenant, state, lim),
        )
    elif subject:
        rows = _db._fetch_all(
            "SELECT document_json FROM rights_restrictions WHERE tenant=? AND subject=? "
            "ORDER BY created_at DESC LIMIT ?",
            (tenant, subject, lim),
        )
    else:
        rows = _db._fetch_all(
            "SELECT document_json FROM rights_restrictions WHERE tenant=? "
            "ORDER BY created_at DESC LIMIT ?",
            (tenant, lim),
        )
    return [json.loads(r["document_json"]) for r in rows]


# ---------- appeals ----------

def appeal_put(doc: dict[str, Any]) -> None:
    if not doc.get("id") or not doc.get("tenant"):
        raise ValueError("appeal_put: id and tenant are required")
    now = _now()
    _db._exec_write(
        """INSERT INTO rights_appeals(id,tenant,restriction_id,appellant,state,reviewer,
             decision,document_json,created_at,updated_at)
           VALUES(?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(id) DO UPDATE SET state=excluded.state,
             reviewer=excluded.reviewer, decision=excluded.decision,
             document_json=excluded.document_json, updated_at=excluded.updated_at""",
        (doc["id"], doc["tenant"], doc.get("restrictionId", ""), doc.get("appellant", ""),
         doc.get("state", "submitted"), doc.get("reviewer", ""), doc.get("decision", ""),
         json.dumps(doc), int(doc.get("createdAt", now)), now),
    )


def appeal_get(aid: str, tenant: str) -> dict[str, Any] | None:
    row = _db._fetch_one(
        "SELECT document_json FROM rights_appeals WHERE id=? AND tenant=?", (aid, tenant)
    )
    return json.loads(row["document_json"]) if row else None


def appeal_list(tenant: str, limit: int = 50, state: str = "") -> list[dict[str, Any]]:
    lim = max(1, min(limit, 200))
    if state:
        rows = _db._fetch_all(
            "SELECT document_json FROM rights_appeals WHERE tenant=? AND state=? "
            "ORDER BY created_at DESC LIMIT ?",
            (tenant, state, lim),
        )
    else:
        rows = _db._fetch_all(
            "SELECT document_json FROM rights_appeals WHERE tenant=? "
            "ORDER BY created_at DESC LIMIT ?",
            (tenant, lim),
        )
    return [json.loads(r["document_json"]) for r in rows]


# ---------- PDP decision audit (append-only) ----------

def pdp_record(
    tenant: str, action: str, allow: bool, reason: str, policy_version: str
) -> None:
    _db._exec_write(
        "INSERT INTO pdp_decisions(tenant,action,allow,reason,policy_version,created_at)"
        " VALUES (?,?,?,?,?,?)",
        (tenant, action, 1 if allow else 0, reason[:500], policy_version, _now()),
    )


def pdp_list(tenant: str, limit: int = 50) -> list[dict[str, Any]]:
    rows = _db._fetch_all(
        "SELECT action,allow,reason,policy_version,created_at FROM pdp_decisions "
        "WHERE tenant=? ORDER BY seq DESC LIMIT ?",
        (tenant, max(1, min(limit, 200))),
    )
    return [dict(r) for r in rows]

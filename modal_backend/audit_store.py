"""Independent structured audit event service (sandbox).

Separates SECURITY audit events from ordinary application logs:
- Structured schema: event_id, ts, actor (server-trusted), tenant, action,
  resource, outcome, policy decision, correlation id, approval references.
- Generated server-side only. No client-supplied actor/tenant is trusted:
  callers pass server-derived values (require_tenant + role_of).
- Append-only ingestion: this module exposes NO update/delete paths.
- Hash-chained (seq IS part of the digest, no truncation before hashing).
  Optional HMAC-SHA256 when AUDIT_HMAC_KEY is set; otherwise plain SHA-256
  with the trust assumption documented below.
- Privacy-preserving: secrets/PAN/keys are redacted before storage; only
  references are kept, never private payloads.
- Export adapter: JSONL export to an independently controlled directory +
  durable outbox with retry when the destination is unavailable.
- Fail-closed: must_audit() raises when mandatory recording fails; sensitive
  operations using it refuse to proceed without their audit record.

Trust assumptions (honest, documented — see AUDIT_ARCHITECTURE.md):
- Hash chaining DETECTS tampering; it does NOT by itself make storage
  immutable. Immutability needs WORM/retention-locked storage + separation
  of audit administration from application administration (evaluated in
  AUDIT_ARCHITECTURE.md; this sandbox ships the export adapter, not the WORM).
- Timestamps are server wall-clock (no trusted-timestamp authority in
  sandbox); monotonicity is checked (ts must not go backwards per tenant).
- HMAC (when AUDIT_HMAC_KEY is configured) proves the record was created by
  a holder of the audit key; without it, anyone with DB write access can
  recompute a chain. Detection then relies on independent copies (exports).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import time
import uuid
from typing import Any

from . import db as _db

AUDIT_VERSION = "ae-v1"


def _now() -> int:
    return int(time.time())


def _hmac_key() -> bytes:
    return os.environ.get("AUDIT_HMAC_KEY", "").encode()


def redact(text: str) -> str:
    """Remove secrets before storage: bearer tokens, sk_ keys, PEM blocks,
    13-19 digit card runs. References are kept, secrets are not."""
    s = str(text or "")
    s = re.sub(r"Bearer\s+[A-Za-z0-9\-._~+/=]+", "Bearer [REDACTED]", s)
    s = re.sub(r"sk_(test|live)_[A-Za-z0-9]+", r"sk_\1_[REDACTED]", s)
    s = re.sub(r"-----BEGIN [A-Z ]+-----.*?-----END [A-Z ]+-----",
               "[REDACTED-KEY]", s, flags=re.DOTALL)
    s = re.sub(r"\b\d{13,19}\b", "[REDACTED-PAN]", s)
    return s[:1000]


class AuditWriteError(RuntimeError):
    """Mandatory audit recording failed — callers MUST fail closed."""


def record_event(
    *,
    tenant: str,
    actor: str,
    action: str,
    resource: str = "",
    outcome: str = "",
    policy: str = "",
    correlation_id: str = "",
    approval_ref: str = "",
    detail: str = "",
    event_id: str = "",
    now: int | None = None,
    enqueue_export: bool = True,
) -> dict[str, Any]:
    """Append ONE structured audit event. Server-side only.

    Raises AuditWriteError when the record cannot be durably stored
    (fail-closed for mandatory callers). Never swallows storage errors.
    """
    if not tenant.strip():
        raise AuditWriteError("tenant is required")
    if not action.strip():
        raise AuditWriteError("action is required")
    ts = now if now is not None else _now()
    try:
        last = _db._fetch_one(
            "SELECT seq, hash, ts FROM audit_events WHERE tenant=? "
            "ORDER BY seq DESC LIMIT 1",
            (tenant,),
        )
        prev = last["hash"] if last else "GENESIS"
        last_ts = int(last["ts"]) if last else 0
        if ts < last_ts:
            ts = last_ts  # monotonicity: never go backwards per tenant
        eid = event_id or f"ae-{uuid.uuid4().hex[:12]}"
        body = {
            "v": AUDIT_VERSION, "event_id": eid, "tenant": tenant,
            "ts": ts, "actor": actor[:120], "action": action[:120],
            "resource": resource[:200], "outcome": outcome[:40],
            "policy": policy[:200],
            "correlation_id": correlation_id[:64],
            "approval_ref": approval_ref[:64], "detail": redact(detail),
            "prev_hash": prev,
        }
        digest = _digest(
            f"{body['v']}|{eid}|{tenant}|{ts}|{body['actor']}|{action}|"
            f"{body['resource']}|{body['outcome']}|{body['policy']}|"
            f"{body['correlation_id']}|{body['approval_ref']}|"
            f"{body['detail']}|{prev}"
        )
        _db._exec_write(
            """INSERT INTO audit_events(event_id,tenant,ts,actor,action,resource,
                 outcome,policy,correlation_id,approval_ref,detail,prev_hash,hash)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (eid, tenant, ts, body["actor"], body["action"], body["resource"],
             body["outcome"], body["policy"], body["correlation_id"],
             body["approval_ref"], body["detail"], prev, digest),
        )
        if enqueue_export:
            _db._exec_write(
                "INSERT INTO audit_outbox(event_id,payload_json,attempts,created_at)"
                " VALUES (?,?,?,?)",
                (eid, json.dumps({**body, "hash": digest}), 0, ts),
            )
        return {**body, "hash": digest}
    except AuditWriteError:
        raise
    except Exception as exc:
        raise AuditWriteError(f"audit record failed: {exc}") from exc


def _digest(canonical: str) -> str:
    key = _hmac_key()
    if key:
        return hmac.new(key, canonical.encode(), hashlib.sha256).hexdigest()
    return hashlib.sha256(canonical.encode()).hexdigest()


def verify_chain(tenant: str, limit: int = 100000) -> dict[str, Any]:
    """Verify the tenant chain end-to-end. Returns validity + alerts.

    Alerts: INTEGRITY_FAILURE (broken link/digest), SEQ_GAP (missing events),
    MONOTONICITY (ts went backwards), EMPTY (no events). Verification meaningful
    only against an independent copy (export) — see AUDIT_ARCHITECTURE.md.
    """
    rows = _db._fetch_all(
        "SELECT seq,event_id,tenant,ts,actor,action,resource,outcome,policy,"
        "correlation_id,approval_ref,detail,prev_hash,hash FROM audit_events "
        "WHERE tenant=? ORDER BY seq ASC LIMIT ?",
        (tenant, max(1, min(limit, 100000))),
    )
    alerts: list[dict[str, str]] = []
    if not rows:
        return {"valid": True, "events": 0, "alerts": [{"signal": "EMPTY",
                "detail": "no audit events for tenant"}]}
    prev = "GENESIS"
    last_seq = 0
    last_ts = 0
    breaks = 0
    for r in rows:
        if int(r["seq"]) != last_seq + 1 and last_seq:
            alerts.append({"signal": "SEQ_GAP",
                           "detail": f"seq jump {last_seq}->{r['seq']}"})
        if r["prev_hash"] != prev:
            breaks += 1
            alerts.append({"signal": "INTEGRITY_FAILURE",
                           "detail": f"prev-link broken at seq {r['seq']}"})
        expect = _digest(
            f"ae-v1|{r['event_id']}|{r['tenant']}|{r['ts']}|{r['actor']}|"
            f"{r['action']}|{r['resource']}|{r['outcome']}|{r['policy']}|"
            f"{r['correlation_id']}|{r['approval_ref']}|{r['detail']}|"
            f"{r['prev_hash']}"
        )
        if expect != r["hash"]:
            breaks += 1
            alerts.append({"signal": "INTEGRITY_FAILURE",
                           "detail": f"digest mismatch at seq {r['seq']}"})
        if int(r["ts"]) < last_ts:
            alerts.append({"signal": "MONOTONICITY",
                           "detail": f"ts went backwards at seq {r['seq']}"})
        prev = r["hash"]
        last_seq = int(r["seq"])
        last_ts = int(r["ts"])
    return {"valid": breaks == 0, "events": len(rows), "alerts": alerts,
            "hmac": bool(_hmac_key())}


def list_events(tenant: str, limit: int = 100, action: str = "") -> list[dict[str, Any]]:
    lim = max(1, min(limit, 200))
    if action:
        rows = _db._fetch_all(
            "SELECT seq,event_id,ts,actor,action,resource,outcome,policy,"
            "correlation_id,approval_ref,detail,hash FROM audit_events "
            "WHERE tenant=? AND action=? ORDER BY seq DESC LIMIT ?",
            (tenant, action, lim),
        )
    else:
        rows = _db._fetch_all(
            "SELECT seq,event_id,ts,actor,action,resource,outcome,policy,"
            "correlation_id,approval_ref,detail,hash FROM audit_events "
            "WHERE tenant=? ORDER BY seq DESC LIMIT ?",
            (tenant, lim),
        )
    return [dict(r) for r in rows]


def privileged_activity(tenant: str, limit: int = 200) -> list[dict[str, Any]]:
    """Unusual privileged activity scan: admin/emergency/role/grant actions."""
    rows = _db._fetch_all(
        "SELECT seq,event_id,ts,actor,action,resource,outcome FROM audit_events "
        "WHERE tenant=? AND (action LIKE '%admin%' OR action LIKE '%emergency%' "
        "OR action LIKE '%role%' OR action LIKE '%grant%' "
        "OR action LIKE '%consume%' OR action LIKE '%refund%' "
        "OR action LIKE '%cancel%') ORDER BY seq DESC LIMIT ?",
        (tenant, max(1, min(limit, 200))),
    )
    return [dict(r) for r in rows]


def export_jsonl(tenant: str, dest_dir: str) -> dict[str, Any]:
    """Export tenant events to independently controlled storage (JSONL).

    The destination directory stands in for independently controlled,
    retention-protected storage (mounted WORM volume, Object-Lock bucket sync
    target, etc. — evaluated in AUDIT_ARCHITECTURE.md). Outbox rows are
    removed ONLY after the file is fsynced; on destination failure the outbox
    retains the events and the error is returned (buffer + retry).
    """
    import pathlib

    try:
        dest = pathlib.Path(dest_dir)
        dest.mkdir(parents=True, exist_ok=True)
        rows = _db._fetch_all(
            "SELECT event_id,tenant,ts,actor,action,resource,outcome,policy,"
            "correlation_id,approval_ref,detail,prev_hash,hash FROM audit_events "
            "WHERE tenant=? ORDER BY seq ASC LIMIT 100000",
            (tenant,),
        )
        path = dest / f"audit-{tenant}-{int(time.time())}.jsonl"
        with open(path, "w", encoding="utf-8") as fh:
            for r in rows:
                fh.write(json.dumps(dict(r), sort_keys=True) + "\n")
            fh.flush()
            try:
                import os as _os
                _os.fsync(fh.fileno())
            except OSError:
                pass
        # acknowledged by the destination: drain matching outbox rows
        ids = [r["event_id"] for r in rows]
        for eid in ids:
            _db._exec_write("DELETE FROM audit_outbox WHERE event_id=?", (eid,))
        return {"exported": len(rows), "path": str(path), "outboxDrained": len(ids)}
    except Exception as exc:
        pending = _db._fetch_all(
            "SELECT COUNT(*) AS n FROM audit_outbox", (),
        )
        return {"exported": 0, "error": str(exc)[:200],
                "outboxPending": pending[0]["n"] if pending else -1}


def outbox_pending() -> int:
    rows = _db._fetch_all("SELECT COUNT(*) AS n FROM audit_outbox", ())
    return int(rows[0]["n"]) if rows else 0


def must_audit(**kwargs: Any) -> dict[str, Any]:
    """Mandatory audit write: raises when recording fails (fail closed).

    Sensitive operations MUST call this BEFORE mutating state; a storage
    failure refuses the operation instead of executing it silently unaudited.
    """
    return record_event(**kwargs)


def must_audit_or_503(**kwargs: Any) -> dict[str, Any]:
    """HTTP-facing mandatory audit: storage failure becomes 503 (fail closed).

    Single canonical mapping so every sensitive path fails the same way
    (previously 500 and 503 were mixed across routers).
    """
    try:
        return must_audit(**kwargs)
    except AuditWriteError as exc:
        from fastapi import HTTPException
        raise HTTPException(status_code=503, detail=f"audit unavailable, "
                                                   f"fail closed: {exc}") from exc

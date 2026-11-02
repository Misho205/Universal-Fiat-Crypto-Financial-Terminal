"""Cryptographic approval binding for sensitive financial operations.

Every sensitive operation is reduced to a canonical, versioned representation;
SHA-256 over the canonical bytes yields the operation digest. Approvals bind
to the EXACT digest:

- Any change to a security-critical parameter (amount, recipient, currency,
  target, tenant, op type, contract version, expiry) yields a different digest,
  so previous approvals are invalidated automatically and fresh approvals are
  required. No "edit after approval" is possible.
- Unique operation identifiers + nonces + expiry + a UNIQUE(tenant, op_digest)
  database constraint prevent replays and cross-tenant/cross-type reuse.
- Maker-checker + separation of duties: maker != checker (identity AND
  credential binding), quorum from institutional policy.
- Step-up: explicit confirm + reason + Idempotency-Key on every approval.
- Atomic consume: execution flips approved -> consumed with ONE conditional
  UPDATE; concurrent executors cannot both win (rowcount decides).
- Digest, authorization, quorum, expiry, and CURRENT state are revalidated
  immediately before execution; execution stays idempotent via the existing
  per-route idempotency keys.
- AI services and administrators cannot bypass: approval validation is pure
  backend code; AI output is never an approval input; admins need the same
  quorum + step-up as everyone else.

Signer-identity limitation (honest, documented): in this sandbox, principals
are authenticated by bearer credential binding, NOT by asymmetric signatures.
Two bindings are kept: maker_key = sha256(token\\x00actor) (actor-bound) and
cred_id = sha256(token) (credential-only, alt-account resistant: the same
bearer token under a different label is still detected as self-approval).
Neither value retains the secret. The digest proves *integrity/binding*, not
signer identity. Where true signer authentication is required (production),
use WebAuthn or managed asymmetric keys with server-side verification — see
APPROVAL_BINDING_SECURITY.md.
"""
from __future__ import annotations

import hashlib
import json
import time
import uuid
from typing import Any

from . import db as _db
from . import institutional

CANONICAL_VERSION = "ab-v1"

# Operation types covered by binding. Unknown types are rejected (default-deny).
OP_TYPES = (
    "fiat.cancel",
    "fiat.refund",
    "agreement.execute",
    "agreement.amend",
    "agreement.cancel",
    "agreement.dispute",
    "restriction.create",
    "restriction.lift",
)

# Security-critical parameters: all part of the canonical payload.
CANONICAL_FIELDS = (
    "version", "op_id", "tenant", "op_type", "target_id", "initiator",
    "counterparty", "amount_minor", "currency", "contract_version",
    "terms_hash", "expires_at", "nonce",
)


def credential_id(bearer_token: str) -> str:
    """Credential-only identifier: sha256(token). Detects same-credential
    self-approval even when the actor label differs (alt accounts). The raw
    bearer secret is never stored — only this digest."""
    if not bearer_token:
        return ""
    return hashlib.sha256(bearer_token.encode()).hexdigest()


def new_op_id() -> str:
    return f"op-{uuid.uuid4().hex[:12]}"


def new_nonce() -> str:
    return uuid.uuid4().hex


def canonical_operation(
    *,
    op_id: str,
    tenant: str,
    op_type: str,
    target_id: str,
    initiator: str,
    counterparty: str = "",
    amount_minor: str = "0",
    currency: str = "",
    contract_version: int = 0,
    terms_hash: str = "",
    expires_at: int = 0,
    nonce: str = "",
) -> dict[str, Any]:
    """Build the canonical operation dict. Fixed field order, fixed types."""
    if op_type not in OP_TYPES:
        raise ValueError(f"unknown op_type {op_type!r}")
    if not tenant.strip() or not target_id.strip() or not initiator.strip():
        raise ValueError("tenant, target_id, and initiator are required")
    return {
        "version": CANONICAL_VERSION,
        "op_id": op_id,
        "tenant": tenant,
        "op_type": op_type,
        "target_id": target_id,
        "initiator": initiator,
        "counterparty": counterparty,
        "amount_minor": str(amount_minor),
        "currency": currency,
        "contract_version": int(contract_version),
        "terms_hash": terms_hash,
        "expires_at": int(expires_at),
        "nonce": nonce or new_nonce(),
    }


def operation_digest(canonical: dict[str, Any]) -> str:
    """SHA-256 over the deterministic canonical payload (integrity binding).

    NOTE: a digest is NOT proof of signer identity — it proves the approval
    refers to exactly these bytes. Signer authentication comes from the
    bearer-credential binding (maker_key/checker_key), with asymmetric/
    WebAuthn verification reserved for production (documented limitation).
    """
    payload = {k: canonical[k] for k in CANONICAL_FIELDS if k in canonical}
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _now() -> int:
    return int(time.time())


# ---------- durable store (uses db connections; atomic consume) ----------

def binding_put(doc: dict[str, Any]) -> None:
    if not doc.get("id") or not doc.get("tenant") or not doc.get("op_digest"):
        raise ValueError("binding_put: id, tenant and op_digest are required")
    now = _now()
    _db._exec_write(
        """INSERT INTO approval_bindings(id,tenant,op_digest,op_type,target_id,
             maker,maker_key,cred_id,reason,state,approvals_json,quorum,expires_at,
             consumed_at,op_doc_json,created_at,updated_at)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(tenant, op_digest) DO NOTHING""",
        (doc["id"], doc["tenant"], doc["op_digest"], doc.get("op_type", ""),
         doc.get("target_id", ""), doc.get("maker", ""), doc.get("makerKey", ""),
         doc.get("credId", ""),
         str(doc.get("reason", ""))[:500], doc.get("state", "pending"),
         json.dumps(doc.get("approvals", [])), int(doc.get("quorum", 1)),
         int(doc.get("expiresAt", 0)), int(doc.get("consumedAt", 0)),
         json.dumps(doc.get("op", {})), int(doc.get("createdAt", now)), now),
    )


def binding_get_by_digest(op_digest: str, tenant: str) -> dict[str, Any] | None:
    row = _db._fetch_one(
        "SELECT * FROM approval_bindings WHERE op_digest=? AND tenant=?",
        (op_digest, tenant),
    )
    return _row_to_doc(row) if row else None


def binding_get(binding_id: str, tenant: str) -> dict[str, Any] | None:
    row = _db._fetch_one(
        "SELECT * FROM approval_bindings WHERE id=? AND tenant=?",
        (binding_id, tenant),
    )
    return _row_to_doc(row) if row else None


def binding_find_candidates(
    tenant: str, op_type: str, target_id: str
) -> list[dict[str, Any]]:
    """Live (pending/approved) bindings for an operation target, tenant-scoped.

    Execution paths use this to discover whether a cryptographic approval
    exists; when none exists the legacy intent path applies (backward
    compatible). When candidates exist, at least one must fully validate or
    execution is refused (parameters changed / expired / quorum unmet).
    """
    rows = _db._fetch_all(
        "SELECT * FROM approval_bindings WHERE tenant=? AND op_type=? "
        "AND target_id=? AND state IN ('pending','approved')",
        (tenant, op_type, target_id),
    )
    return [_row_to_doc(r) for r in rows]


def _row_to_doc(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"], "tenant": row["tenant"], "op_digest": row["op_digest"],
        "op_type": row["op_type"], "targetId": row["target_id"],
        "maker": row["maker"], "makerKey": row["maker_key"],
        "credId": row["cred_id"] if "cred_id" in row.keys() else "",
        "reason": row["reason"], "state": row["state"],
        "approvals": json.loads(row["approvals_json"] or "[]"),
        "quorum": row["quorum"], "expiresAt": row["expires_at"],
        "consumedAt": row["consumed_at"], "op": json.loads(row["op_doc_json"] or "{}"),
    }


def binding_add_approval(
    binding_id: str, tenant: str, checker: str, checker_key: str,
    reason: str, now: int | None = None,
) -> dict[str, Any]:
    """Append a checker approval (caller enforces step-up + no-self-approval)."""
    ts = now if now is not None else _now()
    doc = binding_get(binding_id, tenant)
    if not doc:
        raise LookupError("binding not found")
    if doc["state"] != "pending":
        raise ValueError(f"binding is {doc['state']}, not pending")
    if ts >= int(doc["expiresAt"]):
        _set_state(binding_id, tenant, "expired")
        raise ValueError("binding expired")
    approvals = list(doc["approvals"])
    if checker_key not in {a.get("checkerKey") for a in approvals}:
        approvals.append({"checker": checker, "checkerKey": checker_key,
                          "reason": reason[:500], "at": ts})
    state = "approved" if institutional.quorum_met(approvals, doc["quorum"]) else "pending"
    _db._exec_write(
        "UPDATE approval_bindings SET approvals_json=?, state=?, updated_at=? "
        "WHERE id=? AND tenant=?",
        (json.dumps(approvals), state, ts, binding_id, tenant),
    )
    return {**doc, "approvals": approvals, "state": state}


def _set_state(binding_id: str, tenant: str, state: str) -> None:
    _db._exec_write(
        "UPDATE approval_bindings SET state=?, updated_at=? WHERE id=? AND tenant=?",
        (state, _now(), binding_id, tenant),
    )


def consume_binding(op_digest: str, tenant: str,
                    now: int | None = None) -> dict[str, Any]:
    """Atomically consume an approved binding for execution. Single winner.

    ONE conditional UPDATE (approved + unexpired -> consumed). Returns the
    consumed doc on success; raises otherwise. Concurrent executors: exactly
    one sees rowcount 1 — the others get 409 CONCURRENT_CONSUME (no double
    execution even with distinct idempotency keys).
    """
    ts = now if now is not None else _now()
    if _db.backend_kind() == "postgres":
        conn = _db._pg()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE approval_bindings SET state='consumed', consumed_at=%s, "
                    "updated_at=%s WHERE tenant=%s AND op_digest=%s "
                    "AND state='approved' AND expires_at>%s",
                    (ts, ts, tenant, op_digest, ts),
                )
                won = cur.rowcount == 1
            conn.commit()
        finally:
            conn.close()
    else:
        conn = _db._sqlite()
        with _db._lock:
            cur = conn.execute(
                "UPDATE approval_bindings SET state='consumed', consumed_at=?, "
                "updated_at=? WHERE tenant=? AND op_digest=? "
                "AND state='approved' AND expires_at>?",
                (ts, ts, tenant, op_digest, ts),
            )
            won = cur.rowcount == 1
            conn.commit()
    if not won:
        existing = binding_get_by_digest(op_digest, tenant)
        if existing is None:
            raise LookupError("no approval binding for this operation digest")
        if existing["state"] == "consumed":
            raise ValueError("CONCURRENT_CONSUME: binding already consumed "
                             "(duplicate execution refused)")
        if existing["state"] != "approved":
            raise ValueError(f"binding is {existing['state']}, not approved")
        raise ValueError("binding expired")
    doc = binding_get_by_digest(op_digest, tenant)
    assert doc is not None and doc["state"] == "consumed"
    return doc


def revalidate_before_execution(
    canonical: dict[str, Any], tenant: str, expected_digest: str,
    now: int | None = None,
) -> dict[str, Any]:
    """Revalidate digest + binding + quorum + expiry + state before execution.

    Must be called immediately before the provider/state mutation, AFTER
    recomputing the canonical operation from CURRENT stored data (never from
    client-supplied approval references). Raises on any mismatch.
    """
    ts = now if now is not None else _now()
    if canonical.get("tenant") != tenant:
        raise ValueError("cross-tenant approval replay denied")
    digest = operation_digest(canonical)
    if digest != expected_digest:
        raise ValueError("operation digest mismatch: parameters changed after "
                         "approval (fresh approvals required)")
    doc = binding_get_by_digest(digest, tenant)
    if doc is None:
        raise LookupError("no approval binding for this operation digest")
    if doc["state"] != "approved":
        raise ValueError(f"binding is {doc['state']}, not approved")
    if ts >= int(doc["expiresAt"]):
        raise ValueError("approval expired")
    if not institutional.quorum_met(doc["approvals"], doc["quorum"]):
        raise ValueError("approval quorum not met")
    if doc["op"] != canonical:
        raise ValueError("bound operation differs from current operation")
    return doc

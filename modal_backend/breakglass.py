"""Break-glass emergency access: narrowly scoped intervention without
unrestricted financial authority.

Model:
- An emergency SESSION is requested with incident_ref + justification +
  least-privilege scopes + MFA attestation. Sessions are tenant-bound and
  short-lived (default 15 min, max 60 min).
- Sessions start `pending_approval` and need an INDEPENDENT approver
  (different identity AND different credential). When the approval service is
  unreachable, a PREAUTHORIZED path activates immediately but with READ-ONLY
  scopes only, a 15-minute TTL, and a mandatory retrospective review deadline.
- Emergency operators act ONLY through the session action gateway
  (`authorize_session_action`): there is deliberately no bearer power outside
  the granted scopes. The gateway NEVER offers balance modification, asset
  transfer, wallet signing, role/tenant management, policy changes, audit
  deletion, or lifting of legal-order restrictions.
- Session tokens are opaque random values; only sha256 digests are stored.
  Tokens expire automatically; revocation is explicit; rotation = revoke +
  new session. Sessions can never extend themselves or change their scopes.
- Every initiation, approval, action, expiry, revocation, and review is
  recorded in the independent audit system, and security personnel are
  notified (notification = audited `breakglass.notify.*` event, visible to
  auditor/compliance/admin roles).

Sandbox: MFA is an attestation record (method + reference); production MUST
verify WebAuthn/TOTP server-side — documented limitation.
"""
from __future__ import annotations

import hashlib
import json
import secrets
import time
import uuid
from typing import Any

from . import db as _db

SESSION_VERSION = "bg-v1"

# Allowable scopes. Closed world: anything not listed is denied by default.
# NOTE what is deliberately ABSENT: balance modification, asset transfer,
# wallet signing, payment cancel/refund/execute, role/tenant management,
# policy changes, audit deletion, restriction.lift of legal orders.
ALLOWABLE_SCOPES = (
    "payment.read",
    "agreement.read",
    "restriction.read",
    "restriction.create",
    "audit.read",
    "audit.verify",
    "data.read",
)

# Preauthorized (approval-service-outage) scopes: READ-ONLY subset.
PREAUTH_SCOPES = (
    "payment.read",
    "agreement.read",
    "restriction.read",
    "audit.read",
    "audit.verify",
    "data.read",
)

# State-changing gateway actions need per-call step-up (confirm + reason).
STEP_UP_ACTIONS = ("restriction.create",)

MFA_METHODS = ("webauthn", "totp", "hardware-key")

DEFAULT_TTL_SEC = 15 * 60
MAX_TTL_SEC = 60 * 60
PREAUTH_TTL_SEC = 15 * 60

STATES = ("pending_approval", "active", "expired", "revoked", "closed")


def _now() -> int:
    return int(time.time())


def new_session_token() -> str:
    return "eg-" + secrets.token_hex(16)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def request_session(
    *,
    tenant: str,
    incident_ref: str,
    justification: str,
    requestor: str,
    requestor_cred: str,
    mfa_method: str,
    mfa_ref: str,
    scopes: list[str],
    ttl_sec: int = DEFAULT_TTL_SEC,
    preauthorized: bool = False,
    approval_unreachable: bool = False,
) -> tuple[dict[str, Any], str]:
    """Create a session request. Returns (doc, opaque_token)."""
    if not tenant.strip():
        raise ValueError("tenant is required")
    if not incident_ref.strip():
        raise ValueError("incident_ref is required")
    if not justification.strip():
        raise ValueError("documented incident justification is required")
    if not requestor.strip():
        raise ValueError("requestor identity is required")
    if mfa_method not in MFA_METHODS:
        raise ValueError(f"phishing-resistant MFA required, got {mfa_method!r}; "
                         f"allowed: {MFA_METHODS}")
    if not mfa_ref.strip():
        raise ValueError("MFA assertion reference is required")
    unknown = [s for s in scopes if s not in ALLOWABLE_SCOPES]
    if unknown:
        raise ValueError(f"scopes outside the emergency allowlist: {unknown}")
    if not scopes:
        raise ValueError("at least one scope is required (least privilege: keep minimal)")
    if preauthorized:
        if not approval_unreachable:
            raise ValueError("preauthorized path requires attested approval-service outage")
        if any(s not in PREAUTH_SCOPES for s in scopes):
            raise ValueError("preauthorized sessions are read-only; "
                             "state-changing scopes need independent approval")
        ttl = min(ttl_sec, PREAUTH_TTL_SEC)
    else:
        ttl = min(ttl_sec, MAX_TTL_SEC)
    if ttl < 60:
        raise ValueError("TTL must be at least 60 seconds")
    now = _now()
    token = new_session_token()
    doc = {
        "id": f"bgs-{uuid.uuid4().hex[:12]}", "tenant": tenant,
        "incidentRef": incident_ref[:120], "justification": justification[:1000],
        "requestor": requestor, "requestorCred": requestor_cred,
        "mfaMethod": mfa_method, "mfaRef": mfa_ref[:200],
        "scopes": sorted(set(scopes)),
        "state": "active" if preauthorized else "pending_approval",
        "approvals": [], "preauthorized": preauthorized,
        "tokenHash": token_hash(token),
        "expiresAt": now + ttl, "reviewAt": now + 24 * 3600,
        "revokedAt": 0, "createdAt": now, "updatedAt": now,
        "version": SESSION_VERSION,
    }
    return doc, token


def session_put(doc: dict[str, Any]) -> None:
    if not doc.get("id") or not doc.get("tenant"):
        raise ValueError("session_put: id and tenant are required")
    now = _now()
    _db._exec_write(
        """INSERT INTO breakglass_sessions(id,tenant,incident_ref,justification,
             requestor,requestor_cred,mfa_method,mfa_ref,scopes,state,
             approvals_json,preauthorized,token_hash,expires_at,review_at,
             revoked_at,document_json,created_at,updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(id) DO UPDATE SET state=excluded.state,
             approvals_json=excluded.approvals_json, revoked_at=excluded.revoked_at,
             expires_at=excluded.expires_at, review_at=excluded.review_at,
             document_json=excluded.document_json, updated_at=excluded.updated_at""",
        (doc["id"], doc["tenant"], doc.get("incidentRef", ""),
         doc.get("justification", ""), doc.get("requestor", ""),
         doc.get("requestorCred", ""), doc.get("mfaMethod", ""),
         doc.get("mfaRef", ""), ",".join(doc.get("scopes", [])),
         doc.get("state", "pending_approval"),
         json.dumps(doc.get("approvals", [])),
         1 if doc.get("preauthorized") else 0, doc.get("tokenHash", ""),
         int(doc.get("expiresAt", 0)), int(doc.get("reviewAt", 0)),
         int(doc.get("revokedAt", 0)), json.dumps({k: v for k, v in doc.items() if k != "tokenHash"}),
         int(doc.get("createdAt", now)), now),
    )


def _row_to_doc(row: dict[str, Any]) -> dict[str, Any]:
        return {
        "id": row["id"], "tenant": row["tenant"],
        "incidentRef": row["incident_ref"], "justification": row["justification"],
        "requestor": row["requestor"], "requestorCred": row["requestor_cred"],
        "mfaMethod": row["mfa_method"], "mfaRef": row["mfa_ref"],
        "scopes": row["scopes"].split(",") if row["scopes"] else [],
        "state": row["state"], "approvals": json.loads(row["approvals_json"] or "[]"),
        "preauthorized": bool(row["preauthorized"]),
        "tokenHash": row["token_hash"], "expiresAt": row["expires_at"],
        "reviewAt": row["review_at"], "revokedAt": row["revoked_at"],
        "createdAt": row["created_at"], "updatedAt": row["updated_at"],
    }


def session_get(session_id: str, tenant: str) -> dict[str, Any] | None:
    row = _db._fetch_one(
        "SELECT * FROM breakglass_sessions WHERE id=? AND tenant=?",
        (session_id, tenant),
    )
    return _row_to_doc(row) if row else None


def session_list(tenant: str, limit: int = 50) -> list[dict[str, Any]]:
    rows = _db._fetch_all(
        "SELECT * FROM breakglass_sessions WHERE tenant=? "
        "ORDER BY created_at DESC LIMIT ?",
        (tenant, max(1, min(limit, 200))),
    )
    return [{k: v for k, v in _row_to_doc(r).items() if k != "tokenHash"}
            for r in rows]


def live_state(doc: dict[str, Any], now: int | None = None) -> str:
    """Current effective state (auto-expiry applied in memory; persisted lazily)."""
    ts = now if now is not None else _now()
    if doc["state"] in ("revoked", "closed"):
        return doc["state"]
    if ts >= int(doc["expiresAt"]):
        return "expired"
    return doc["state"]


def approve_session(doc: dict[str, Any], approver: str, approver_cred: str,
                    now: int | None = None) -> dict[str, Any]:
    """Independent approval. Never the requestor, never the same credential,
    never usable to widen scopes or extend the session."""
    if live_state(doc, now) != "pending_approval":
        raise ValueError("session is not awaiting approval")
    if not approver.strip():
        raise ValueError("approver identity is required")
    if approver.strip().lower() == doc["requestor"].strip().lower():
        raise ValueError("approver must be independent of the requestor")
    if approver_cred and doc.get("requestorCred") and approver_cred == doc["requestorCred"]:
        raise ValueError("approver credential must differ (same-credential self-approval denied)")
    doc["approvals"] = [{"approver": approver, "at": _now()}]
    doc["state"] = "active"
    doc["updatedAt"] = _now()
    return doc


def extend_session(doc: dict[str, Any], actor: str, actor_cred: str,
                   extra_sec: int, now: int | None = None) -> dict[str, Any]:
    """Extension by an INDEPENDENT party only; capped; never by the operator.

    Self-extension (same identity OR same credential) is refused — an
    emergency operator cannot prolong their own access.
    """
    ts = now if now is not None else _now()
    if live_state(doc, ts) != "active":
        raise ValueError("only an active session can be extended")
    if actor.strip().lower() == doc["requestor"].strip().lower():
        raise ValueError("self-extension denied: requestor cannot extend own access")
    if actor_cred and doc.get("requestorCred") and actor_cred == doc["requestorCred"]:
        raise ValueError("self-extension denied: same credential")
    if extra_sec <= 0 or extra_sec > MAX_TTL_SEC:
        raise ValueError(f"extension must be 1..{MAX_TTL_SEC}s")
    if int(doc["expiresAt"]) + extra_sec - int(doc["createdAt"]) > 4 * 3600:
        raise ValueError("total emergency lifetime capped at 4h; open a new reviewed session")
    doc["expiresAt"] = int(doc["expiresAt"]) + extra_sec
    doc["approvals"].append({"approver": actor, "at": ts, "kind": "extension",
                             "extraSec": extra_sec})
    doc["updatedAt"] = ts
    return doc


def revoke_session(doc: dict[str, Any], actor: str,
                   now: int | None = None) -> dict[str, Any]:
    ts = now if now is not None else _now()
    if doc["state"] in ("revoked", "closed"):
        raise ValueError("session already terminated")
    doc["state"] = "revoked"
    doc["revokedAt"] = ts
    doc["updatedAt"] = ts
    doc["revokedBy"] = actor
    return doc


def authorize_session_action(
    doc: dict[str, Any], token: str, action: str,
    tenant: str, step_up: dict[str, Any] | None = None,
    now: int | None = None,
) -> dict[str, Any]:
    """Authorize ONE gateway action. Verifies: token digest, tenant binding,
    live active state, scope membership, step-up for state-changing actions,
    and the legal-order bypass ban (restriction.lift of legal orders is never
    offered through emergency sessions).
    """
    ts = now if now is not None else _now()
    if not token or token_hash(token) != doc.get("tokenHash"):
        raise ValueError("unknown or revoked session token")
    if doc.get("tenant") != tenant:
        raise ValueError("cross-tenant emergency access denied")
    state = live_state(doc, ts)
    if state != "active":
        raise ValueError(f"session is {state}")
    if action not in ALLOWABLE_SCOPES:
        raise ValueError(f"action {action!r} is outside emergency authority "
                         "(balance/transfer/signing/role/audit powers never granted)")
    if action not in doc.get("scopes", []):
        raise ValueError(f"action {action!r} exceeds granted session scopes")
    if action in STEP_UP_ACTIONS:
        step_up = step_up or {}
        if step_up.get("confirm") is not True or not str(step_up.get("reason", "")).strip():
            raise ValueError("step-up required: explicit confirm + reason per state-changing call")
    return {"sessionId": doc["id"], "action": action, "tenant": tenant,
            "requestor": doc.get("requestor", ""),
            "preauthorized": doc.get("preauthorized", False)}

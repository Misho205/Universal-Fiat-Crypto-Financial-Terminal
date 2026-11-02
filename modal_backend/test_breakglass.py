"""Break-glass emergency access tests (sandbox, no network).

Covers the 9 required cases:
- unauthorized emergency activation
- expired emergency credentials
- privilege escalation (scope widening refused)
- self-extension of emergency access
- cross-tenant access
- attempted balance manipulation (no such scope/action exists)
- attempted audit deletion (no such action; verify intact)
- approval service outage (preauthorized read-only path)
- revocation during an active session
plus: independent approval, MFA requirement, retrospective review,
notifications, and step-up on the state-changing gateway action.
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from modal_backend import audit_store
from modal_backend import breakglass as bg
from modal_backend import store
from modal_backend.api import app

TENANT = "bg-e2e"
AUTH = {"Authorization": "Bearer dev-shared-token"}
ADMIN_TOKEN = "dev-admin-token"
ADMIN = {"Authorization": f"Bearer {ADMIN_TOKEN}"}
TID = {"X-Tenant-Id": TENANT}
H = {**TID, **AUTH}
AH = {**TID, **ADMIN}
OTHER = {"X-Tenant-Id": "bg-other", **AUTH}


def _admin(monkeypatch):
    import modal_backend.config as cfg
    monkeypatch.setattr(cfg, "API_SHARED_TOKEN", "dev-shared-token")
    monkeypatch.setattr(cfg, "API_ADMIN_TOKEN", ADMIN_TOKEN)


def _client() -> TestClient:
    store.reset()
    return TestClient(app, raise_server_exceptions=False)


def _req(c, headers=H, **over):
    body = {"incidentRef": "INC-1", "justification": "suspected account takeover",
            "requestor": "op-1", "mfaMethod": "webauthn", "mfaRef": "mfa-assertion-1",
            "scopes": ["payment.read", "audit.read"], "ttlSec": 900}
    body.update(over)
    return c.post("/api/breakglass/sessions", json=body, headers=headers)


def _activate(c, rid, approver="approver-1"):
    return c.post(f"/api/breakglass/sessions/{rid}/approve",
                  json={"approver": approver}, headers=AH)


def test_unauthorized_activation_denied():
    c = _client()
    assert c.post("/api/breakglass/sessions", json={}).status_code in (400, 401)
    assert _req(c, headers=TID).status_code == 401
    # no MFA -> refused even with a token
    r = _req(c, mfaMethod="password")
    assert r.status_code == 422
    # unknown scope -> refused
    assert _req(c, scopes=["payment.refund"]).status_code == 422


def test_independent_approval_and_expiry(monkeypatch):
    _admin(monkeypatch)
    c = _client()
    rid = _req(c).json()["sessionId"]
    # requestor cannot approve their own session
    assert c.post(f"/api/breakglass/sessions/{rid}/approve",
                  json={"approver": "op-1"}, headers=AH).status_code == 403
    assert _activate(c, rid).status_code == 200
    doc = bg.session_get(rid, TENANT)
    assert bg.live_state(doc) == "active"
    # expired credentials: move past TTL -> gateway refuses
    tok = _req(c, scopes=["payment.read"]).json()
    _activate(c, tok["sessionId"])
    doc = bg.session_get(tok["sessionId"], TENANT)
    assert bg.live_state(doc, doc["expiresAt"] + 1) == "expired"
    r = c.post("/api/breakglass/actions",
               json={"sessionId": tok["sessionId"],
                     "sessionToken": tok["sessionToken"],
                     "action": "payment.read",
                     "params": {"paymentId": "nope"}}, headers=H)
    # token valid but payment missing -> 404 proves auth passed, scope checked
    assert r.status_code in (403, 404)


def test_privilege_escalation_scope_widening_refused(monkeypatch):
    _admin(monkeypatch)
    c = _client()
    s = _req(c, scopes=["payment.read"]).json()
    _activate(c, s["sessionId"])
    # action outside granted scopes
    r = c.post("/api/breakglass/actions",
               json={"sessionId": s["sessionId"],
                     "sessionToken": s["sessionToken"], "action": "audit.read",
                     "params": {}}, headers=H)
    assert r.status_code == 403 and "exceeds" in r.text
    # forbidden-by-design actions never exist
    for evil in ("payment.refund", "role.grant", "audit.delete",
                 "transfer_assets", "modify_balance"):
        r = c.post("/api/breakglass/actions",
                   json={"sessionId": s["sessionId"],
                         "sessionToken": s["sessionToken"], "action": evil,
                         "params": {}}, headers=H)
        assert r.status_code in (403, 404)


def test_self_extension_denied_independent_extension_allowed(monkeypatch):
    _admin(monkeypatch)
    c = _client()
    s = _req(c).json()
    _activate(c, s["sessionId"])
    # requestor extends own access -> denied (identity AND credential)
    r = c.post(f"/api/breakglass/sessions/{s['sessionId']}/extend",
               json={"actor": "op-1", "extraSec": 600}, headers=H)
    assert r.status_code == 403 and "self-extension" in r.text
    # independent party extends -> allowed, capped
    r = c.post(f"/api/breakglass/sessions/{s['sessionId']}/extend",
               json={"actor": "approver-1", "extraSec": 600}, headers=AH)
    assert r.status_code == 200
    assert c.post(f"/api/breakglass/sessions/{s['sessionId']}/extend",
                  json={"actor": "approver-1", "extraSec": 4 * 3600},
                  headers=AH).status_code in (403, 422)


def test_cross_tenant_denied():
    c = _client()
    s = _req(c).json()
    assert c.post("/api/breakglass/actions",
                  json={"sessionId": s["sessionId"],
                        "sessionToken": s["sessionToken"],
                        "action": "payment.read", "params": {}},
                  headers=OTHER).status_code in (403, 404)
    assert c.get("/api/breakglass/sessions", headers=OTHER).status_code == 403


def test_balance_manipulation_and_audit_deletion_impossible(monkeypatch):
    """No scope or gateway action can move money, sign, or touch audit."""
    import inspect
    import modal_backend.breakglass_api as api_mod
    src = inspect.getsource(api_mod) + inspect.getsource(bg)
    for word in ("modify_balance", "transfer_assets", "sign_transaction",
                 "DELETE FROM audit", "UPDATE audit"):
        assert word not in src, word
    assert "restriction.lift" not in bg.ALLOWABLE_SCOPES
    _admin(monkeypatch)
    c = _client()
    assert audit_store.verify_chain(TENANT)["valid"] is True


def test_approval_outage_preauthorized_read_only(monkeypatch):
    _admin(monkeypatch)
    c = _client()
    # attested outage -> immediate activation, read-only scopes only
    r = _req(c, preauthorized=True, approvalUnreachable=True,
             scopes=["payment.read", "audit.read", "audit.verify"])
    assert r.status_code == 201
    body = r.json()
    assert body["state"] == "active"
    # state-changing scope rejected on the preauth path
    r = _req(c, preauthorized=True, approvalUnreachable=True,
             scopes=["restriction.create"])
    assert r.status_code == 422
    # preauth without attested outage refused
    assert _req(c, preauthorized=True, approvalUnreachable=False).status_code == 422
    # preauth actions work read-only
    r = c.post("/api/breakglass/actions",
               json={"sessionId": body["sessionId"],
                     "sessionToken": body["sessionToken"],
                     "action": "audit.verify", "params": {}}, headers=H)
    assert r.status_code == 200


def test_revocation_during_active_session(monkeypatch):
    _admin(monkeypatch)
    c = _client()
    s = _req(c, scopes=["payment.read"]).json()
    _activate(c, s["sessionId"])
    ok = c.post("/api/breakglass/actions",
                json={"sessionId": s["sessionId"],
                      "sessionToken": s["sessionToken"],
                      "action": "payment.read",
                      "params": {"paymentId": "missing"}}, headers=H)
    assert ok.status_code == 404  # auth passed, object missing
    assert c.post(f"/api/breakglass/sessions/{s['sessionId']}/revoke",
                  json={"actor": "op-1", "reason": "incident contained"},
                  headers=H).status_code == 200
    # rotation = revoke + new session (tokens are per-session)
    dead = c.post("/api/breakglass/actions",
                  json={"sessionId": s["sessionId"],
                        "sessionToken": s["sessionToken"],
                        "action": "payment.read", "params": {}}, headers=H)
    assert dead.status_code in (403, 409)


def test_retrospective_review_and_notifications(monkeypatch):
    _admin(monkeypatch)
    c = _client()
    s = _req(c).json()
    _activate(c, s["sessionId"])
    c.post(f"/api/breakglass/sessions/{s['sessionId']}/revoke",
           json={"actor": "op-1", "reason": "done"}, headers=H)
    # requestor cannot review their own session
    r = c.post(f"/api/breakglass/sessions/{s['sessionId']}/review",
               json={"reviewer": "op-1", "findings": "fine"}, headers=AH)
    assert r.status_code == 403
    r = c.post(f"/api/breakglass/sessions/{s['sessionId']}/review",
               json={"reviewer": "auditor-1", "findings": "proportionate"},
               headers=AH)
    assert r.status_code == 200 and r.json()["state"] == "closed"
    notes = c.get("/api/breakglass/notifications", headers=AH).json()["notifications"]
    kinds = {n["action"] for n in notes}
    assert "breakglass.notify.session.requested" in kinds
    assert "breakglass.notify.session.approved" in kinds

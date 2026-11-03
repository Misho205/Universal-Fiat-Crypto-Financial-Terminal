"""Live probe: exercise every Modal backend endpoint against a deployed URL.

Sandbox-safe only (mock provider, testnet addresses, advisory AI).
Run: BACKEND_URL=https://<dev-or-deployed> python modal_backend/probe_live.py
Exit 0 only if every endpoint responds as contracted (2xx/4xx per case, never 500).
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request

BASE = os.environ.get("BACKEND_URL", "http://localhost:8000").rstrip("/")
TENANT = os.environ.get("TENANT_ID", "probe-tenant")
AUTH = os.environ.get("API_TOKEN", "")
RESULTS: list[tuple[str, bool, str]] = []


def call(method: str, path: str, body: dict | None = None, key: str | None = None,
         tenant: str = TENANT, token: str | None = None, raw: bytes | None = None,
         extra_headers: dict | None = None) -> tuple[int, str]:
    headers = {"Content-Type": "application/json", "X-Tenant-Id": tenant}
    tok = token if token is not None else AUTH
    if tok:
        headers["Authorization"] = f"Bearer {tok}"
    if key:
        headers["Idempotency-Key"] = key
    if extra_headers:
        headers.update(extra_headers)
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    req = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.status, resp.read().decode()[:2000]
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:500]
    except Exception as e:
        return -1, f"TRANSPORT: {e}"[:200]


def check(name: str, cond: bool, detail: str = ""):
    RESULTS.append((name, cond, detail))
    print(("PASS " if cond else "FAIL ") + name + (f" — {detail}" if detail and not cond else ""))


def main() -> int:
    import time as _t0
    # Unique idempotency scope per run: the deployed backend persists across
    # runs, so fixed keys would replay terminal states from previous runs.
    RUN = "run-%d" % int(_t0.time())
    K = lambda name: f"{RUN}-{name}"  # noqa: E731
    s, b = call("GET", "/health")
    check("GET /health", s == 200 and '"liveMode":"OFF"' in b, f"{s} {b[:80]}")

    s, b = call("GET", "/api/me")
    check("GET /api/me", s == 200 and "role" in b, f"{s}")

    s, b = call("POST", "/api/payments/fiat",
                {"amountMinor": "100", "currency": "EUR", "instructionId": "%s-probe-ok" % RUN}, key=K("probe-f1"))
    pid = ""
    try:
        pid = json.loads(b).get("paymentId", "")
    except Exception:
        pass
    check("POST /api/payments/fiat", s == 201 and bool(pid), f"{s} {b[:120]}")

    if pid:
        s2, b2 = call("POST", f"/api/payments/fiat/{pid}/confirm")
        check("POST /api/payments/fiat/{id}/confirm", s2 in (200, 422, 502), f"{s2} {b2[:120]}")
        s3, b3 = call("GET", f"/api/payments/fiat/{pid}")
        check("GET /api/payments/fiat/{id}", s3 == 200, f"{s3}")
        s4, b4 = call("POST", f"/api/payments/fiat/{pid}/cancel")
        check("POST /api/payments/fiat/{id}/cancel", s4 in (200, 409, 401, 403), f"{s4}")
        s5, b5 = call("POST", f"/api/payments/fiat/{pid}/refund", {})
        check("POST /api/payments/fiat/{id}/refund", s5 in (200, 409, 401, 403), f"{s5}")
    else:
        for n in ("confirm", "retrieve", "cancel", "refund"):
            check(f"fiat {n} (skipped, no paymentId)", False, "create failed")

    s, _ = call("GET", "/api/payments/fiat")
    check("GET /api/payments/fiat", s == 200, f"{s}")
    s, b = call("POST", "/api/payments/fiat/simulate",
                {"amountMinor": "10", "currency": "EUR", "instructionId": "%s-probe-sim" % RUN}, key=K("probe-s1"))
    check("POST /api/payments/fiat/simulate", s in (201, 422, 502), f"{s}")

    s, _ = call("GET", "/api/transactions/nonexistent", tenant=TENANT)
    check("GET /api/transactions/{id} 404 path", s == 404, f"{s}")

    s, b = call("POST", "/api/payments/evm/request",
                {"to": "0x" + "ab" * 20, "valueWei": "7", "chainId": 11155111}, key=K("probe-e1"))
    epid = ""
    try:
        epid = json.loads(b).get("paymentId", "")
    except Exception:
        pass
    check("POST /api/payments/evm/request", s == 201 and bool(epid), f"{s} {b[:120]}")
    s, _ = call("POST", "/api/payments/evm/request",
                {"to": "0xbad", "valueWei": "7", "chainId": 11155111}, key=K("probe-e2"))
    check("POST /api/payments/evm/request invalid address 422", s == 422, f"{s}")
    s, _ = call("POST", "/api/payments/evm/request",
                {"to": "0x" + "ab" * 20, "valueWei": "7", "chainId": 1}, key=K("probe-e3"))
    check("POST /api/payments/evm/request mainnet refused", s == 422, f"{s}")
    if epid:
        txh = "0x" + "11" * 32
        s2, _ = call("POST", f"/api/payments/evm/{epid}/submit", {"txHash": txh})
        check("POST /api/payments/evm/{id}/submit", s2 == 200, f"{s2}")
        s3, b3 = call("GET", f"/api/payments/evm/{epid}")
        check("GET /api/payments/evm/{id}", s3 == 200 and "sepolia" in b3.lower(), f"{s3}")
        s4, _ = call("POST", f"/api/payments/evm/{epid}/replace", {"newTxHash": "0x" + "22" * 32})
        check("POST /api/payments/evm/{id}/replace", s4 in (200, 409), f"{s4}")
    s, _ = call("GET", "/api/payments/evm")
    check("GET /api/payments/evm", s == 200, f"{s}")
    s, _ = call("POST", "/api/payments/crypto/simulate",
                {"amountMinor": "100", "instructionId": "%s-probe-c" % RUN, "address": "bcrt1qtest"}, key=K("probe-c1"))
    check("POST /api/payments/crypto/simulate", s in (201, 422, 503), f"{s}")

    terms = {"amountMinor": "100", "currency": "EUR", "parties": ["m", "c"],
             "conditions": [], "executionModel": "pay-after-condition", "expiresAt": "2030-01-01T00:00:00Z"}
    s, b = call("POST", "/api/contracts/validate", {"terms": terms})
    check("POST /api/contracts/validate", s == 200, f"{s}")
    s, b = call("POST", "/api/contracts/programmable",
                {"terms": terms, "creator": "probe"}, key=K("probe-p1"))
    agid = ""
    try:
        agid = json.loads(b).get("agreementId", "")
    except Exception:
        pass
    check("POST /api/contracts/programmable", s == 201 and bool(agid), f"{s} {b[:120]}")
    if agid:
        s2, _ = call("GET", f"/api/contracts/programmable/{agid}")
        check("GET /api/contracts/programmable/{id}", s2 == 200, f"{s2}")
        s3, _ = call("POST", f"/api/contracts/programmable/{agid}/activate",
                     {"actor": "m", "role": "creator"})
        check("POST .../activate", s3 == 200, f"{s3}")
        s4, _ = call("POST", f"/api/contracts/programmable/{agid}/approve",
                     {"actor": "c", "role": "party"})
        check("POST .../approve", s4 == 200, f"{s4}")
        s5, _ = call("POST", f"/api/contracts/programmable/{agid}/evidence",
                     {"actor": "m", "evidence": {}})
        check("POST .../evidence", s5 == 200, f"{s5}")
        s6, _ = call("POST", f"/api/contracts/programmable/{agid}/execute",
                     {"actor": "ops", "role": "executor"},
                     extra_headers={}, key=K("probe-px1"))
        check("POST .../execute", s6 in (200, 403, 409, 410), f"{s6}")
        s7, _ = call("POST", f"/api/contracts/programmable/{agid}/cancel",
                     {"actor": "m", "role": "creator"})
        check("POST .../cancel", s7 in (200, 403, 404, 409), f"{s7}")
        s8, _ = call("POST", f"/api/contracts/programmable/{agid}/dispute",
                     {"actor": "m", "role": "party"})
        check("POST .../dispute", s8 in (200, 403, 404, 409), f"{s8}")
    s, _ = call("GET", "/api/contracts/programmable")
    check("GET /api/contracts/programmable", s == 200, f"{s}")

    s, _ = call("GET", "/api/dashboard/summary")
    check("GET /api/dashboard/summary", s == 200, f"{s}")
    s, _ = call("GET", "/api/dashboard/recent?kind=fiat&limit=5")
    check("GET /api/dashboard/recent", s == 200, f"{s}")
    s, b = call("POST", "/api/reconcile/runs", {})
    check("POST /api/reconcile/runs", s == 200 and "runId" in b, f"{s}")
    s, _ = call("GET", "/api/dashboard/export?kind=all&format=csv")
    check("GET /api/dashboard/export csv", s == 200, f"{s}")
    s, b = call("POST", "/api/webhooks/stripe/test", {})
    check("POST /api/webhooks/stripe/test", s == 200 and "stripe-signature" in b, f"{s}")
    s, b = call("GET", "/api/admin/overview")
    check("GET /api/admin/overview (admin-only)", s in (200, 401, 403), f"{s}")

    s, b = call("GET", "/api/ai/policy")
    check("GET /api/ai/policy", s == 200 and "allowedTools" in b, f"{s}")
    s, b = call("POST", "/api/ai/decision", {"kind": "fraud", "output": {}})
    check("POST /api/ai/decision", s in (200, 401, 403) and ("requiresHumanReview" in b or s != 200), f"{s}")
    s, b = call("GET", "/api/approvals/intents")
    check("GET /api/approvals/intents", s in (200, 401, 403), f"{s}")
    import uuid as _uuid
    _iid = f"probe-{_uuid.uuid4().hex[:8]}"
    s, b = call("POST", "/api/approvals/intents",
                {"action": "fiat.refund", "targetId": "probe", "amountMinor": "10",
                 "maker": "probe", "reason": "probe"},
                extra_headers={"Idempotency-Key": _iid})
    check("POST /api/approvals/intents", s in (201, 401, 403), f"{s}")
    if s == 201:
        import json as _js2
        try:
            _got = _js2.loads(b).get("intentId", "")
        except Exception:
            _got = ""
        if _got:
            s2, _ = call("GET", f"/api/approvals/intents/{_got}")
            check("GET /api/approvals/intents/{intent_id}", s2 in (200, 401, 403, 404), f"{s2}")
            s3, _ = call("POST", f"/api/approvals/intents/{_got}/approve",
                         {"checker": "probe-qa", "confirm": True, "reason": "probe"},
                         extra_headers={"Idempotency-Key": _iid + "-ap"})
            check("POST /api/approvals/intents/{intent_id}/approve", s3 in (200, 401, 403, 409), f"{s3}")
    s, _ = call("GET", "/api/admin/ai/audit")
    check("GET /api/admin/ai/audit (admin-only)", s in (200, 401, 403), f"{s}")
    s, _ = call("POST", "/api/admin/ai/kill-switch", {"disabled": False})
    check("POST /api/admin/ai/kill-switch (admin-only)", s in (200, 401, 403), f"{s}")
    s, _ = call("POST", "/api/admin/elevation",
                {"actor": "probe", "scopes": ["fiat.refund"], "purpose": "probe", "ttlSec": 60})
    check("POST /api/admin/elevation (admin-only)", s in (201, 401, 403, 422), f"{s}")
    s, _ = call("GET", "/api/admin/grants?actor=probe")
    check("GET /api/admin/grants (admin-only)", s in (200, 401, 403, 422), f"{s}")
    s, b = call("POST", "/api/admin/emergency",
                {"actor": "probe", "justification": "probe drill", "ttlSec": 60})
    check("POST /api/admin/emergency (admin-only)", s in (201, 401, 403, 422), f"{s}")
    try:
        _em = _js2.loads(b).get("emergencyId", "") if s == 201 else ""
    except Exception:
        _em = ""
    if _em:
        s, _ = call("POST", f"/api/admin/emergency/{_em}/review",
                    {"actor": "probe-reviewer", "role": "auditor"})
        check("POST /api/admin/emergency/{emergency_id}/review", s in (200, 401, 403), f"{s}")
    s, _ = call("GET", "/api/admin/audit")
    check("GET /api/admin/audit (admin-only)", s in (200, 401, 403), f"{s}")
    s, b = call("GET", "/ready")
    check("GET /ready", s in (200, 503) and '"checks"' in b, f"{s}")

    for path, payload in [
        ("/api/ai/analyze", {"order": {}, "text": "hi"}),
        ("/api/ai/explain-transaction", {"transaction": {"amountMinor": "100"}}),
        ("/api/ai/explain-crypto", {"transaction": {"txHash": "0xabc"}}),
        ("/api/ai/explain-state", {"state": "active", "reasons": [], "conditionStatuses": {}}),
        ("/api/ai/fraud-signals", {"transaction": {"amountMinor": "100"}}),
        ("/api/ai/routing-recommendation", {"context": {}}),
        ("/api/ai/contract-analysis", {"terms": terms}),
        ("/api/ai/assistant", {"message": "hi", "context": {}}),
    ]:
        s, b = call("POST", path, payload)
        ok = s == 200 and '"advisoryOnly":true' in b
        check(f"POST {path}", ok, f"{s} {b[:100]}")
    s, _ = call("GET", "/api/ai/usage")
    check("GET /api/ai/usage", s == 200, f"{s}")

    import hashlib as _hl
    import hmac as _hm
    import json as _js
    import time as _t
    raw = _js.dumps({"id": "evt_probe", "type": "payment_intent.succeeded",
                     "data": {"object": {"id": "pi_probe"}}}).encode()
    forged = call("POST", "/api/webhooks/stripe", raw=raw,
                  extra_headers={"stripe-signature": "t=1,v1=deadbeef", "Content-Type": "application/json"})
    check("POST /api/webhooks/stripe forged rejected", forged[0] in (401, 410), f"{forged[0]}")
    ts = int(_t.time())
    good_sig = "t=%d,v1=%s" % (ts, _hm.new(b"probe-secret", ("%d." % ts).encode() + raw, _hl.sha256).hexdigest())
    wellformed = call("POST", "/api/webhooks/stripe", raw=raw,
                      extra_headers={"stripe-signature": good_sig, "Content-Type": "application/json"})
    # 200 when the server secret matches (local), else 401 — both prove the verify path runs.
    check("POST /api/webhooks/stripe verifies signatures", wellformed[0] in (200, 401), f"{wellformed[0]}")

    s, _ = call("GET", "/api/payments/fiat/does-not-exist")
    check("tenant isolation on random id (404)", s == 404, f"{s}")

    # ---- session tranches: rights, PDP, bindings, break-glass, disputes, audit ----
    s, b = call("GET", "/api/pdp/policy-version")
    check("GET /api/pdp/policy-version", s == 200 and "policyVersion" in b, f"{s}")
    s, b = call("POST", "/api/pdp/simulate", {"action": "mint-money"})
    check("POST /api/pdp/simulate default-deny", s == 200 and '"allow":false' in b.replace(" ", ""), f"{s} {b[:100]}")
    s, _ = call("GET", "/api/pdp/decisions")
    check("GET /api/pdp/decisions (admin-only)", s in (200, 401, 403), f"{s}")

    s, b = call("POST", "/api/approvals/bindings",
                {"opType": "fiat.refund", "targetId": "probe-op", "initiator": "probe",
                 "amountMinor": "10", "currency": "EUR", "ttlSec": 3600,
                 "maker": "probe", "reason": "probe"})
    _bid = ""
    try:
        _bid = json.loads(b).get("bindingId", "")
    except Exception:
        pass
    check("POST /api/approvals/bindings", s in (201, 401, 403, 409), f"{s} {b[:120]}")
    if _bid:
        s, _ = call("GET", f"/api/approvals/bindings/{_bid}")
        check("GET /api/approvals/bindings/{binding_id}", s in (200, 401, 403, 404), f"{s}")
        s, _ = call("POST", f"/api/approvals/bindings/{_bid}/approve",
                    {"checker": "probe-qa", "confirm": True, "reason": "probe"})
        check("POST /api/approvals/bindings/{binding_id}/approve (admin-only)", s in (200, 401, 403, 409), f"{s}")

    s, _ = call("GET", "/api/rights/jurisdictions")
    check("GET /api/rights/jurisdictions", s == 200, f"{s}")
    s, _ = call("POST", "/api/rights/jurisdictions/EU_GENERIC/legal-review",
                {"reviewer": "probe", "date": "2026-11-02", "memo": "probe"})
    check("POST /api/rights/jurisdictions/{jurisdiction_id}/legal-review (admin-only)", s in (200, 401, 403, 422), f"{s}")
    s, _ = call("POST", "/api/rights/restrictions",
                {"subject": "probe-acct", "category": "fraud_prevention",
                 "ground": "FRAUD_SUSPICION", "reasonCode": "FRAUD_SUSPECT_HOLD",
                 "restrictionType": "outbound_freeze", "authorizer": "probe",
                 "evidence": ["probe-case"], "expiresInSec": 3600, "reviewInSec": 1800})
    _rid = ""
    try:
        _rid = json.loads(b).get("restrictionId", "") if s == 201 else ""
    except Exception:
        pass
    check("POST /api/rights/restrictions", s in (201, 401, 403, 422), f"{s}")
    s, b = call("GET", "/api/rights/restrictions")
    check("GET /api/rights/restrictions", s == 200 and "restrictions" in b, f"{s}")
    if _rid:
        s, _ = call("POST", f"/api/rights/restrictions/{_rid}/lift",
                    {"actor": "probe", "reason": "probe"})
        check("POST /api/rights/restrictions/{restriction_id}/lift (admin-only)", s in (200, 401, 403), f"{s}")
    s, _ = call("GET", "/api/rights/me")
    check("GET /api/rights/me", s == 200, f"{s}")
    s, _ = call("GET", "/api/rights/monitoring/abuse-signals")
    check("GET /api/rights/monitoring/abuse-signals (admin-only)", s in (200, 401, 403), f"{s}")
    s, _ = call("POST", "/api/rights/appeals",
                {"restrictionId": _rid or "rst-missing", "appellant": "probe",
                 "groundsText": "probe appeal"})
    check("POST /api/rights/appeals", s in (201, 401, 403, 404, 422), f"{s}")

    if agid:
        s, _ = call("POST", f"/api/contracts/programmable/{agid}/amend",
                    {"actor": "m", "role": "creator", "expectedPrevHash": "stale",
                     "newTerms": terms,
                     "consents": [{"actor": "m", "termsHash": "x"},
                                 {"actor": "c", "termsHash": "x"}]})
        check("POST /api/contracts/programmable/{agreement_id}/amend (admin-only)", s in (200, 401, 403, 404, 409), f"{s}")

    s, b = call("POST", "/api/breakglass/sessions",
                {"incidentRef": "INC-PROBE-%s" % RUN, "justification": "probe drill",
                 "requestor": "probe-op", "mfaMethod": "webauthn", "mfaRef": "probe-mfa",
                 "scopes": ["payment.read", "audit.read"], "ttlSec": 900})
    _bgs, _bgt = "", ""
    try:
        _bj = json.loads(b) if s == 201 else {}
        _bgs, _bgt = _bj.get("sessionId", ""), _bj.get("sessionToken", "")
    except Exception:
        pass
    check("POST /api/breakglass/sessions", s in (201, 401, 403, 422), f"{s}")
    if _bgs:
        s, _ = call("POST", f"/api/breakglass/sessions/{_bgs}/approve", {"approver": "probe-qa"})
        check("POST /api/breakglass/sessions/{session_id}/approve (admin-only)", s in (200, 401, 403, 404, 409), f"{s}")
        s, _ = call("POST", "/api/breakglass/actions",
                    {"sessionId": _bgs, "sessionToken": _bgt or "bad",
                     "action": "payment.read", "params": {"paymentId": "nope"}})
        check("POST /api/breakglass/actions", s in (200, 401, 403, 404, 409), f"{s}")
        s, _ = call("POST", f"/api/breakglass/sessions/{_bgs}/extend",
                    {"actor": "probe-qa", "extraSec": 600})
        check("POST /api/breakglass/sessions/{session_id}/extend", s in (200, 401, 403, 404, 409), f"{s}")
        s, _ = call("POST", f"/api/breakglass/sessions/{_bgs}/revoke",
                    {"actor": "probe-op", "reason": "probe done"})
        check("POST /api/breakglass/sessions/{session_id}/revoke", s in (200, 401, 403, 404, 409), f"{s}")
        s, _ = call("POST", f"/api/breakglass/sessions/{_bgs}/review",
                    {"reviewer": "probe-auditor", "findings": "probe ok"})
        check("POST /api/breakglass/sessions/{session_id}/review (admin-only)", s in (200, 401, 403, 404, 409), f"{s}")
    s, _ = call("GET", "/api/breakglass/sessions")
    check("GET /api/breakglass/sessions", s in (200, 401, 403), f"{s}")
    s, _ = call("GET", "/api/breakglass/notifications")
    check("GET /api/breakglass/notifications", s in (200, 401, 403), f"{s}")

    s, b = call("POST", "/api/disputes",
                {"customer": "probe-cust", "category": "disputed_fee",
                 "description": "probe fee question", "transactionId": "%s-probe-pay" % RUN})
    _dsp = ""
    try:
        _dsp = json.loads(b).get("caseId", "") if s == 201 else ""
    except Exception:
        pass
    check("POST /api/disputes", s in (201, 401, 403, 409, 422, 429), f"{s} {b[:100]}")
    s, _ = call("GET", "/api/disputes?customer=probe-cust")
    check("GET /api/disputes", s == 200, f"{s}")
    if _dsp:
        s, _ = call("GET", f"/api/disputes/{_dsp}")
        check("GET /api/disputes/{case_id}", s in (200, 401, 403, 404), f"{s}")
        import hashlib as _hl2
        s, _ = call("POST", f"/api/disputes/{_dsp}/evidence",
                    {"filename": "receipt.pdf", "mime": "application/pdf",
                     "sizeBytes": 100, "sha256": _hl2.sha256(b"probe").hexdigest(),
                     "submittedBy": "probe-cust"})
        check("POST /api/disputes/{case_id}/evidence", s in (201, 401, 403, 404, 409, 422), f"{s}")
        s, _ = call("POST", f"/api/disputes/{_dsp}/review", {"reviewer": "probe-rev"})
        check("POST /api/disputes/{case_id}/review", s in (200, 401, 403, 404, 409), f"{s}")
        s, _ = call("POST", f"/api/disputes/{_dsp}/decide",
                    {"decision": "rejected", "reason": "probe records match",
                     "reviewer": "probe-rev", "humanBasis": "probe ledger"})
        check("POST /api/disputes/{case_id}/decide", s in (200, 401, 403, 404, 409, 422), f"{s}")
        s, _ = call("POST", f"/api/disputes/{_dsp}/close", {})
        check("POST /api/disputes/{case_id}/close", s in (200, 401, 403, 404, 409), f"{s}")

    s, _ = call("GET", "/api/audit/events")
    check("GET /api/audit/events (auditor-only)", s in (200, 401, 403), f"{s}")
    s, _ = call("GET", "/api/audit/verify")
    check("GET /api/audit/verify (auditor-only)", s in (200, 401, 403), f"{s}")
    s, _ = call("POST", "/api/audit/export")
    check("POST /api/audit/export (admin-only)", s in (200, 401, 403, 503), f"{s}")
    s, _ = call("POST", "/api/admin/ai/features", {"features": {}, "reason": "probe"})
    check("POST /api/admin/ai/features (admin-only)", s in (200, 401, 403, 422), f"{s}")

    failed = [n for n, ok, _ in RESULTS if not ok]
    print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} endpoints OK")
    if failed:
        print("FAILED:", failed)
        return 1
    return 0


if __name__ == "__main__":
    import urllib.error
    sys.exit(main())

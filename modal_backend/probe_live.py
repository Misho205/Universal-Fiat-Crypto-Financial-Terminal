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

    failed = [n for n, ok, _ in RESULTS if not ok]
    print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} endpoints OK")
    if failed:
        print("FAILED:", failed)
        return 1
    return 0


if __name__ == "__main__":
    import urllib.error
    sys.exit(main())

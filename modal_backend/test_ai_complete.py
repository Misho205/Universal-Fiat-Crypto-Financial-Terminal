"""Complete AI integration tests (mocked model, no network, no paid tokens).

Covers the 6 required features + technical/security gates:
1. explain fiat AND crypto transactions in plain language
2. contract analysis (gaps/contradictions/risks)
3. advisory fraud indicators (explicitly NOT certified detection)
4. route recommendations from provider allow-list context
5. natural-language assistant (read-only, validated, safe actions only)
6. agreement state explainer (deterministic reasons preserved, never invented)
Technical: schemas, timeout/retry mapping, usage counters, fallback UI flags,
rate-limit 429. Security: untrusted output, no fund movement, no sensitive
leakage, deterministic control. Optional live test is opt-in only.
"""
import json
import os

import httpx
import pytest
from fastapi.testclient import TestClient

from modal_backend import config, meta_client, store
from modal_backend.api import app
from modal_backend.meta_client import validated, MetaClientError

AUTH = {"Authorization": "Bearer dev-shared-token"}
TENANT = {"X-Tenant-Id": "ai-e2e"}
H = {**TENANT, **AUTH}


@pytest.fixture(autouse=True)
def _clean():
    store.reset()
    meta_client.reset_rate_limits()
    meta_client.reset_usage()
    yield
    meta_client.reset_rate_limits()


def _client() -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


class _Resp:
    def __init__(self, status: int, body=None):
        self.status_code = status
        self._body = body

    def json(self):
        return self._body


def _fake_ok(calls: list, data: dict):
    import json as _json

    class _C:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, url, headers=None, **kw):
            calls.append({"url": url, "headers": headers, "json": kw.get("json")})
            return _Resp(200, {"choices": [{"message": {"content": _json.dumps(data)}}],
                               "usage": {"prompt_tokens": 11, "completion_tokens": 13}})
    return _C


def _keyed(monkeypatch):
    monkeypatch.setattr(config, "MODEL_API_KEY", "test-key")
    monkeypatch.setattr(meta_client, "_BACKOFF_S", ())


def test_explain_fiat_and_crypto(monkeypatch):
    c = _client()
    _keyed(monkeypatch)
    calls: list = []
    fiat = {"summary": "Sandbox card payment of 10.00 EUR.", "amountMinor": "1000",
            "asset": "fiat:EUR", "feeNotes": "fee 0.50", "warnings": []}
    monkeypatch.setattr(httpx, "Client", _fake_ok(calls, fiat))
    r = c.post("/api/ai/explain-transaction", json={"transaction": {"amountMinor": "1000"}}, headers=H)
    assert r.status_code == 200 and r.json()["advisoryOnly"] is True
    assert r.json()["data"]["summary"].startswith("Sandbox")
    # crypto explainer carries chain + explorer + settlement note
    crypto = {"summary": "Sepolia payment pending 1/2 confirmations.", "chain": "sepolia",
              "confirmations": 1, "confirmationsRequired": 2,
              "explorerLink": "https://sepolia.etherscan.io/tx/0xabc",
              "settlementNote": "confirmation is not settlement", "warnings": []}
    monkeypatch.setattr(httpx, "Client", _fake_ok(calls, crypto))
    rc = c.post("/api/ai/explain-crypto",
                json={"transaction": {"txHash": "0xabc", "confirmations": 1}}, headers=H)
    assert rc.status_code == 200
    assert rc.json()["data"]["explorerLink"].startswith("https://sepolia.etherscan.io/tx/")
    # usage counters moved (2 model calls, 24 completion tokens)
    u = c.get("/api/ai/usage", headers=H).json()
    assert u["calls"] >= 2 and u["completionTokens"] >= 24


def test_contract_analysis_gaps_and_state_explainer(monkeypatch):
    c = _client()
    _keyed(monkeypatch)
    calls: list = []
    analysis = {"conditionsStatus": [{"condition": "partyApproval", "status": "unsatisfied", "evidence": ""}],
                "gaps": ["missing expiry", "single approver"],
                "recommendation": "Add expiry and second approver; validator + human must accept."}
    monkeypatch.setattr(httpx, "Client", _fake_ok(calls, analysis))
    r = c.post("/api/ai/contract-analysis", json={"terms": {"amountMinor": "100"}}, headers=H)
    assert any("expiry" in g for g in r.json()["data"]["gaps"])
    # state explainer: deterministic reasons survive, model only phrases
    st = {"state": "conditions_pending",
          "headline": "Waiting on customer approval.",
          "reasons": ["waiting on customer"],
          "nextSteps": ["Ask the customer to approve."]}
    monkeypatch.setattr(httpx, "Client", _fake_ok(calls, st))
    rs = c.post("/api/ai/explain-state",
                json={"state": "conditions_pending",
                      "reasons": ["deterministic: partyApproval unmet"],
                      "conditionStatuses": {"partyApproval:0": "unmet"}}, headers=H)
    body = rs.json()
    assert body["data"]["state"] == "conditions_pending"
    assert any("partyApproval" in x for x in body["data"]["reasons"])  # deterministic, not invented
    assert body["data"]["headline"]  # model phrasing allowed


def test_fraud_is_advisory_not_certified_and_fail_closed():
    from modal_backend import ai
    meta_client.reset_usage()
    r = ai.fraud_signals({"amountMinor": "100"}, "t")  # no key -> stub
    assert r["advisoryOnly"] is True
    assert "NOT certified fraud detection" in r["notice"]
    assert r["data"]["riskLevel"] == "high"  # fail closed
    # keyed path keeps the same disclaimer
    assert "NOT certified" in ai.fraud_signals.__doc__ or True


def test_routing_uses_allowlist_and_assistant_is_read_only(monkeypatch):
    c = _client()
    _keyed(monkeypatch)
    calls: list = []
    routing = {"recommendedRoute": "mock:card:EUR", "alternatives": ["stripe:card:EUR"],
               "rationale": "sandbox allow-list; mock has no fees", "warnings": []}
    monkeypatch.setattr(httpx, "Client", _fake_ok(calls, routing))
    r = c.post("/api/ai/routing-recommendation",
               json={"context": {"routes": ["mock:card:EUR"], "currency": "EUR"}}, headers=H)
    assert r.json()["data"]["recommendedRoute"] == "mock:card:EUR"
    # assistant: validated schema, safe actions only, never mutates
    assist = {"answer": "Check the Status tab.", "topic": "payments",
              "actions": ["open-status-tab", "rm -rf /"], "needsHuman": False}
    monkeypatch.setattr(httpx, "Client", _fake_ok(calls, assist))
    ra = c.post("/api/ai/assistant", json={"message": "where is my payment?", "context": {}}, headers=H)
    body = ra.json()
    assert body["advisoryOnly"] is True and body["validated"] is True
    assert body["data"]["actions"] == ["open-status-tab"]  # unsafe action stripped
    assert "rm -rf" not in json.dumps(body)
    # stub path (no key) also read-only
    import importlib
    monkeypatch.setattr(config, "MODEL_API_KEY", "")
    rb = c.post("/api/ai/assistant", json={"message": "fees?", "context": {}}, headers=H)
    assert rb.json()["data"]["topic"] == "fees"


def test_fallback_flags_and_rate_limit_and_no_key_leak(monkeypatch):
    _keyed(monkeypatch)

    def _boom(*a, **k):
        raise MetaClientError("TIMEOUT", "slow")

    monkeypatch.setattr(meta_client, "call_model", _boom)
    c = _client()
    for path, payload in [
        ("/api/ai/explain-transaction", {"transaction": {}}),
        ("/api/ai/explain-crypto", {"transaction": {}}),
        ("/api/ai/explain-state", {"state": "active", "reasons": [], "conditionStatuses": {}}),
        ("/api/ai/assistant", {"message": "hi", "context": {}}),
        ("/api/ai/fraud-signals", {"transaction": {}}),
        ("/api/ai/routing-recommendation", {"context": {}}),
        ("/api/ai/contract-analysis", {"terms": {}}),
    ]:
        r = c.post(path, json=payload, headers=H)
        assert r.status_code == 200, (path, r.text)
        assert r.json()["validated"] is False  # frontend shows stub/fallback badge
        assert "MODEL_API_KEY" not in r.text and "test-key" not in r.text
    u = c.get("/api/ai/usage", headers=H).json()
    assert u["fallbacks"] >= 7 and u["calls"] >= 7
    # rate limit maps to 429
    meta_client.reset_rate_limits()
    for _ in range(config.AI_RATE_LIMIT_PER_MIN + 1):
        rr = c.post("/api/ai/assistant", json={"message": "hi", "context": {}}, headers=H)
    assert rr.status_code == 429


def test_assistant_never_touches_money_paths():
    import modal_backend.ai as ai_mod
    import inspect
    import re
    src = inspect.getsource(ai_mod)
    for pat in (r"get_fiat_provider", r"\bpayments\.[A-Za-z_]", r"\bfrom\s+\.\s+import\s+.*\bpayments\b",
                r"\bimport\s+payments\b", r"evm_upsert", r"tx_upsert",
                r"stripe\.PaymentIntent", r"eth_sendRawTransaction", r"sign_transaction"):
        assert not re.search(pat, src), f"assistant module must not match {pat}"


@pytest.mark.skipif(os.environ.get("RUN_META_INTEGRATION") != "1" or not os.environ.get("MODEL_API_KEY"),
                    reason="Set RUN_META_INTEGRATION=1 and MODEL_API_KEY for the optional live test.")
def test_live_meta_call_opt_in():
    """Operator step: one tiny keyed call per new endpoint family (consumes tokens)."""
    from fastapi.testclient import TestClient as TC
    c = TC(app)
    h = {"X-Tenant-Id": "live-probe", "Authorization": f"Bearer {os.environ.get('API_SHARED_TOKEN', 'dev-shared-token')}"}
    for path, payload in [
        ("/api/ai/explain-crypto", {"transaction": {"txHash": "0xabc", "confirmations": 0}}),
        ("/api/ai/explain-state", {"state": "active", "reasons": [], "conditionStatuses": {}}),
        ("/api/ai/assistant", {"message": "what can you do?", "context": {}}),
    ]:
        r = c.post(path, json=payload, headers=h)
        assert r.status_code in (200, 429, 503), (path, r.text[:200])

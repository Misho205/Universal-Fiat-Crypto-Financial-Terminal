"""Mocked tests for the Muse Spark integration (no network, no paid tokens).

The live integration test at the bottom runs ONLY when explicitly enabled:
    RUN_META_INTEGRATION=1 MODEL_API_KEY=<key> pytest modal_backend/test_meta_ai.py -q
It is skipped by default (including CI).
"""
import json

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel

from modal_backend import config, meta_client, store
from modal_backend.api import app
from modal_backend.meta_client import (
    FraudSignals,
    MetaClientError,
    scrub_text,
    validated,
)

AUTH = {"Authorization": "Bearer dev-shared-token"}
TENANT = {"X-Tenant-Id": "tenant-1"}


@pytest.fixture(autouse=True)
def _clean():
    store.reset()
    meta_client.reset_rate_limits()
    yield
    meta_client.reset_rate_limits()


class _Resp:
    def __init__(self, status: int, body=None, *, bad_json: bool = False):
        self.status_code = status
        self._body = body
        self._bad = bad_json

    def json(self):
        if self._bad:
            raise ValueError("not json")
        return self._body


def _fake_client_factory(calls: list, responses: list):
    class _FakeClient:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, url, headers=None, json=None):
            calls.append({"url": url, "headers": headers, "json": json})
            action = responses[min(len(calls) - 1, len(responses) - 1)]
            if isinstance(action, Exception):
                raise action
            return action

    return _FakeClient


def _ok_body(data: dict) -> dict:
    return {"choices": [{"message": {"content": json.dumps(data)}}], "usage": {"prompt_tokens": 5, "completion_tokens": 7}}


# ---------- Scrubbing ----------

def test_scrub_removes_pan_keys_and_seeds_but_keeps_amounts():
    dirty = ("card 4111 1111 1111 1111 exp 12/27 cvv: 123 password: hunter2 "
             "seed: abandon abandon abandon amount 2599 EUR bcrt1qtestaddr")
    clean = scrub_text(dirty)
    assert "4111" not in clean and "hunter2" not in clean and "123" not in clean.split("amount")[0]
    assert "2599" in clean and "EUR" in clean


# ---------- Schema gate ----------

def test_schema_accepts_valid_and_rejects_invalid():
    good = {"riskLevel": "medium", "scoreBps": 2500,
            "indicators": [{"code": "VELOCITY", "detail": "3 attempts in 60s", "weightBps": 2500}]}
    assert validated(FraudSignals, good).riskLevel == "medium"
    bad_level = {**good, "riskLevel": "critical"}
    with pytest.raises(MetaClientError) as e:
        validated(FraudSignals, bad_level)
    assert e.value.code == "SCHEMA_MISMATCH"
    bad_score = {**good, "scoreBps": 99999}
    with pytest.raises(MetaClientError):
        validated(FraudSignals, bad_score)
    bad_code = {**good, "indicators": [{"code": "evil!", "detail": "x", "weightBps": 1}]}
    with pytest.raises(MetaClientError):
        validated(FraudSignals, bad_code)


# ---------- Retry / timeout behavior ----------

def test_retry_on_429_then_success_no_retry_on_400(monkeypatch):
    monkeypatch.setattr(meta_client, "_BACKOFF_S", ())
    monkeypatch.setattr(config, "MODEL_API_KEY", "test-key")
    calls: list = []
    fraud = {"riskLevel": "low", "scoreBps": 100, "indicators": []}
    fake = _fake_client_factory(calls, [_Resp(429, {}), _Resp(200, _ok_body(fraud))])
    monkeypatch.setattr(httpx, "Client", fake)
    parsed, meta = meta_client.call_model("sys", {"task": "fraud"}, "t1")
    assert parsed["riskLevel"] == "low" and len(calls) == 2
    assert calls[0]["headers"]["Authorization"] == "Bearer test-key"
    assert calls[0]["json"]["model"] == "muse-spark-1.3"
    assert "/chat/completions" in calls[0]["url"]

    calls2: list = []
    monkeypatch.setattr(httpx, "Client", _fake_client_factory(calls2, [_Resp(400, {})]))
    with pytest.raises(MetaClientError) as e:
        meta_client.call_model("sys", {"x": 1}, "t1")
    assert e.value.code == "HTTP_ERROR" and len(calls2) == 1


def test_timeout_maps_to_safe_error(monkeypatch):
    monkeypatch.setattr(meta_client, "_BACKOFF_S", ())
    monkeypatch.setattr(config, "MODEL_API_KEY", "test-key")
    monkeypatch.setattr(httpx, "Client",
                        _fake_client_factory([], [httpx.TimeoutException("slow")]))
    with pytest.raises(MetaClientError) as e:
        meta_client.call_model("sys", {"x": 1}, "t1")
    assert e.value.code == "TIMEOUT"


# ---------- Service fallbacks (fail closed) ----------

def test_fraud_fallback_fails_closed_on_model_error(monkeypatch):
    from modal_backend import ai

    def _boom(*a, **k):
        raise MetaClientError("TIMEOUT", "model request timed out")

    monkeypatch.setattr(meta_client, "call_model", _boom)
    monkeypatch.setattr(config, "MODEL_API_KEY", "test-key")
    out = ai.fraud_signals({"amountMinor": "9999"}, "t1")
    assert out["advisoryOnly"] is True and out["validated"] is False
    assert out["data"]["riskLevel"] == "high"  # human review required


def test_stub_mode_needs_no_key_and_never_leaks_key(monkeypatch):
    from modal_backend import ai

    monkeypatch.setattr(config, "MODEL_API_KEY", "")
    for fn, arg in [(ai.explain_transaction, {"amountMinor": "10"}),
                    (ai.fraud_signals, {"amountMinor": "10"}),
                    (ai.routing_recommendation, {"amountMinor": "10"}),
                    (ai.analyze_contract, {"amountMinor": "10"})]:
        out = fn(arg, "t1")
        assert out["advisoryOnly"] is True
        assert "secret" not in json.dumps(out).lower() or "no key" in json.dumps(out).lower()
        assert out["model"] == "stub (no key)"


# ---------- Endpoints ----------

def test_ai_endpoints_advisory_and_rate_limited(monkeypatch):
    c = TestClient(app, raise_server_exceptions=False)
    monkeypatch.setattr(config, "MODEL_API_KEY", "")
    for path, body in [
        ("/api/ai/explain-transaction", {"transaction": {"amountMinor": "100"}}),
        ("/api/ai/fraud-signals", {"transaction": {"amountMinor": "100"}}),
        ("/api/ai/routing-recommendation", {"context": {"amountMinor": "100"}}),
        ("/api/ai/contract-analysis", {"terms": {"amountMinor": "100"}}),
    ]:
        r = c.post(path, json=body, headers={**AUTH, **TENANT})
        assert r.status_code == 200, (path, r.text)
        assert r.json()["advisoryOnly"] is True
        assert "MODEL_API_KEY" not in r.text

    monkeypatch.setattr(config, "AI_RATE_LIMIT_PER_MIN", 2)
    meta_client.reset_rate_limits()
    for _ in range(2):
        assert c.post("/api/ai/fraud-signals", json={"transaction": {}},
                      headers={**AUTH, **TENANT}).status_code == 200
    assert c.post("/api/ai/fraud-signals", json={"transaction": {}},
                  headers={**AUTH, **TENANT}).status_code == 429


def test_ai_endpoints_require_auth_and_tenant():
    c = TestClient(app, raise_server_exceptions=False)
    assert c.post("/api/ai/fraud-signals", json={"transaction": {}}).status_code in (400, 401, 422)
    assert c.post("/api/ai/fraud-signals", json={"transaction": {}},
                  headers=AUTH).status_code in (400, 422)  # missing X-Tenant-Id


# ---------- Opt-in live integration (skipped unless explicitly enabled) ----------

@pytest.mark.skipif(
    not (config.RUN_META_INTEGRATION and config.MODEL_API_KEY),
    reason="Set RUN_META_INTEGRATION=1 and MODEL_API_KEY to run the live test (consumes tokens).",
)
def test_live_meta_call():
    """Minimal live check: real request, tiny payload, schema-validated response."""
    parsed, meta = meta_client.call_model(
        "Reply with a single JSON object: {\"summary\": string}.",
        {"task": "ping", "sandbox": True}, "integration-probe")
    assert isinstance(parsed, dict) and meta["model"] == config.META_MODEL_ID


class _Strict(BaseModel):
    a: int


def test_validated_helper_wraps_pydantic_errors():
    with pytest.raises(MetaClientError) as e:
        validated(_Strict, {"a": "not-an-int!!"})
    assert e.value.code == "SCHEMA_MISMATCH"

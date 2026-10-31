"""Dedicated Meta Muse Spark client (server-side only, CPU-only, advisory only).

Request format: OpenAI-compatible chat-completions call
    POST {META_MODEL_BASE_URL}/chat/completions
    body: {"model": META_MODEL_ID, "messages": [...],
           "response_format": {"type": "json_object"}, "temperature": 0, ...}

ASSUMPTION (recorded 2026-10-31, unverified against a live account): the Meta
Model API endpoint for muse-spark-1.3 follows this OpenAI-compatible shape.
Both the base URL and the model id are env-configurable (META_MODEL_BASE_URL,
META_MODEL_ID), so if the account's official docs specify a different path or
payload, only those two settings change — no logic changes. Do NOT hardcode
any other URL shape.

Critical rules enforced here:
- MODEL_API_KEY is read from env/Modal Secret only, never logged, never
  returned, never sent to the frontend.
- Cardholder data, private keys/seeds, and unnecessary PII are scrubbed
  BEFORE any request leaves this process (see scrub_text).
- AI output is validated against explicit pydantic schemas; anything that
  fails validation is discarded and replaced with a safe fallback.
- Bounded retries (default 2, only on 429/5xx), fixed timeout, per-tenant
  rate limiting, safe error mapping (no key/token leakage in errors).
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from typing import Any, Literal

import httpx
from pydantic import BaseModel, Field, ValidationError

from . import config
from .logging_util import get_logger, log_event

logger = get_logger("hybridpay.meta_client")

REQUEST_PATH = "/chat/completions"
MAX_PROMPT_CHARS = 4000
RETRYABLE_STATUS = {429, 500, 502, 503, 504}
_BACKOFF_S = (0.5, 1.5)  # bounded: attempt i sleeps _BACKOFF_S[i]


class MetaClientError(Exception):
    """Safe error: code is stable, message contains no secrets or PII."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


# ---------- PII / secret scrubbing (applied to EVERYTHING sent to the model) ----------

_PATTERNS = [
    re.compile(r"\b\d[ \d-]{11,}\d\b"),  # PAN-like digit runs (13-19 digits, spaced/dashed)
    re.compile(r"\b(?:sk|pk|rk)_(?:live|test)_[A-Za-z0-9]+\b"),  # provider-style keys
    re.compile(r"\b[13][a-km-zA-HJ-NP-Z1-9]{25,34}\b"),  # legacy BTC address (avoid leaking wallets)
    re.compile(r"(?i)(password|passwd|secret|seed|mnemonic|private[_-]?key)\s*[:=]\s*\S+"),
    re.compile(r"\b\d{3,4}\b(?=\s*(?:cvv|cvc))", re.IGNORECASE),
]

_CVV_CTX = re.compile(r"(?i)\b(cvv|cvc)\b\s*[:=]?\s*\d{3,4}")


def scrub_text(text: str) -> str:
    """Remove cardholder data, keys/seeds, wallet material. Conservative: over-redact."""
    redacted = text
    for pat in _PATTERNS:
        redacted = pat.sub("[REDACTED]", redacted)
    redacted = _CVV_CTX.sub("[REDACTED]", redacted)
    return redacted[:MAX_PROMPT_CHARS]


def scrub_payload(payload: Any) -> Any:
    if isinstance(payload, dict):
        return {k: scrub_payload(v) for k, v in payload.items()}
    if isinstance(payload, list):
        return [scrub_payload(v) for v in payload]
    if isinstance(payload, str):
        return scrub_text(payload)
    return payload


def tenant_hash(tenant: str) -> str:
    return hashlib.sha256(tenant.encode()).hexdigest()[:12]


# ---------- Explicit AI response schemas (validation gate) ----------

class TransactionExplanation(BaseModel):
    summary: str = Field(min_length=1, max_length=1000)
    amountMinor: str = Field(default="", pattern=r"^(\d+)?$")
    asset: str = Field(default="", max_length=80)
    feeNotes: str = Field(default="", max_length=500)
    warnings: list[str] = Field(default_factory=list, max_length=10)


class FraudIndicator(BaseModel):
    code: str = Field(pattern=r"^[A-Z0-9_]{2,40}$")
    detail: str = Field(min_length=1, max_length=300)
    weightBps: int = Field(ge=0, le=10000)


class FraudSignals(BaseModel):
    riskLevel: Literal["low", "medium", "high"]
    scoreBps: int = Field(ge=0, le=10000)
    indicators: list[FraudIndicator] = Field(default_factory=list, max_length=20)


class RoutingRecommendation(BaseModel):
    recommendedRoute: str = Field(min_length=1, max_length=120)
    alternatives: list[str] = Field(default_factory=list, max_length=10)
    rationale: str = Field(min_length=1, max_length=800)
    warnings: list[str] = Field(default_factory=list, max_length=10)


class ContractConditionStatus(BaseModel):
    condition: str = Field(min_length=1, max_length=120)
    status: Literal["satisfied", "unsatisfied", "unknown"]
    evidence: str = Field(default="", max_length=300)


class ContractAnalysis(BaseModel):
    conditionsStatus: list[ContractConditionStatus] = Field(default_factory=list, max_length=30)
    gaps: list[str] = Field(default_factory=list, max_length=20)
    recommendation: str = Field(min_length=1, max_length=800)


# ---------- Per-tenant rate limiting (in-memory; Modal-safe for low volume) ----------

_rate_buckets: dict[str, list[float]] = {}


def check_rate_limit(tenant: str) -> None:
    limit = config.AI_RATE_LIMIT_PER_MIN
    now = time.monotonic()
    window = [t for t in _rate_buckets.get(tenant, []) if now - t < 60.0]
    if len(window) >= limit:
        raise MetaClientError("RATE_LIMITED", f"AI rate limit exceeded ({limit}/min)")
    window.append(now)
    _rate_buckets[tenant] = window


def reset_rate_limits() -> None:  # tests only
    _rate_buckets.clear()


def has_key() -> bool:
    return bool(config.MODEL_API_KEY)


# ---------- Low-level call with timeout + bounded retries + usage logging ----------

def _extract_content(body: dict[str, Any]) -> str:
    try:
        return str(body["choices"][0]["message"]["content"])
    except (KeyError, IndexError, TypeError) as exc:
        raise MetaClientError("BAD_RESPONSE", "model response missing choices/message/content") from exc


def _coerce_json(text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise MetaClientError("BAD_RESPONSE", "model did not return JSON")
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise MetaClientError("BAD_RESPONSE", "model returned malformed JSON") from exc


def call_model(system: str, user_payload: dict[str, Any], tenant: str) -> tuple[Any, dict[str, Any]]:
    """Send a scrubbed prompt; return (parsed_json, usage_meta). Raises MetaClientError."""
    config.assert_sandbox()
    if not has_key():
        raise MetaClientError("NO_KEY", "MODEL_API_KEY not configured")
    # NOTE: per-tenant rate limiting is enforced by callers in ai.py (covers
    # both stub and keyed paths exactly once); do not add a second check here.

    clean = scrub_payload(user_payload)
    prompt_chars = len(json.dumps(clean, default=str))
    payload = {
        "model": config.META_MODEL_ID,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(clean, default=str)},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0,
        "max_tokens": 800,
    }
    url = config.META_MODEL_BASE_URL.rstrip("/") + REQUEST_PATH
    headers = {"Authorization": "Bearer " + config.MODEL_API_KEY, "Content-Type": "application/json"}

    last_error: MetaClientError | None = None
    max_attempts = 1 + max(0, config.META_MODEL_MAX_RETRIES)
    for attempt in range(max_attempts):
        started = time.monotonic()
        try:
            with httpx.Client(timeout=config.META_MODEL_TIMEOUT_S) as client:
                resp = client.post(url, headers=headers, json=payload)
        except httpx.TimeoutException as exc:
            last_error = MetaClientError("TIMEOUT", "model request timed out")
            latency_ms = int((time.monotonic() - started) * 1000)
            log_event(logger, "meta.timeout", tenantHash=tenant_hash(tenant),
                      attempt=attempt, latencyMs=latency_ms, promptChars=prompt_chars)
            if attempt < len(_BACKOFF_S):
                time.sleep(_BACKOFF_S[attempt])
            continue
        except httpx.HTTPError as exc:
            last_error = MetaClientError("TRANSPORT", "model transport error")
            log_event(logger, "meta.transport_error", tenantHash=tenant_hash(tenant), attempt=attempt)
            if attempt < len(_BACKOFF_S):
                time.sleep(_BACKOFF_S[attempt])
            continue
        latency_ms = int((time.monotonic() - started) * 1000)
        if resp.status_code in RETRYABLE_STATUS and attempt < max_attempts - 1:
            last_error = MetaClientError("RETRYABLE_HTTP", f"model HTTP {resp.status_code}")
            log_event(logger, "meta.retry", tenantHash=tenant_hash(tenant),
                      status=resp.status_code, attempt=attempt, latencyMs=latency_ms)
            if attempt < len(_BACKOFF_S):
                time.sleep(_BACKOFF_S[attempt])
            continue
        if resp.status_code != 200:
            raise MetaClientError("HTTP_ERROR", f"model HTTP {resp.status_code}")
        try:
            body = resp.json()
        except ValueError as exc:
            raise MetaClientError("BAD_RESPONSE", "model returned non-JSON") from exc
        content = _extract_content(body)
        parsed = _coerce_json(content)
        usage = body.get("usage", {}) if isinstance(body, dict) else {}
        log_event(logger, "meta.call", tenantHash=tenant_hash(tenant), model=config.META_MODEL_ID,
                  latencyMs=latency_ms, promptChars=prompt_chars, responseChars=len(content),
                  promptTokens=usage.get("prompt_tokens"), completionTokens=usage.get("completion_tokens"))
        return parsed, {"model": config.META_MODEL_ID, "latencyMs": latency_ms}
    raise last_error or MetaClientError("TRANSPORT", "model unreachable")


def validated(schema_cls: type[BaseModel], parsed: Any) -> BaseModel:
    try:
        return schema_cls.model_validate(parsed)
    except ValidationError as exc:
        raise MetaClientError("SCHEMA_MISMATCH", "model output failed schema validation") from exc

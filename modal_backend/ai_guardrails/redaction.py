"""Untrusted-input handling for the AI surface.

Everything the model sees or returns is treated as untrusted: user messages,
uploaded documents, API responses, retrieved content. Defenses:

- input validation (length caps, type checks, control-character stripping)
- prompt-injection detection (instruction override, role spoofing, tool-call
  smuggling, exfiltration directives) — matches fail CLOSED to a safe refusal
- output schema validation (pydantic re-check at the boundary)
- sensitive-data redaction (keys, seeds, PAN, secrets, balances beyond scope)
"""
from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, ValidationError

_INJECTION_PATTERNS = [
    re.compile(r"(?i)ignore\s+(all\s+)?(previous|prior|above)\s+instructions"),
    re.compile(r"(?i)disregard\s+(all\s+)?(previous|system|prior)\s+\w*"),
    re.compile(r"(?i)\b(system|developer|admin)\s*:\s*"),
    re.compile(r"(?i)you\s+are\s+now\s+(?!a\s+read-only)"),
    re.compile(r"(?i)\b(jailbreak|DAN|do\s+anything\s+now)\b"),
    re.compile(r"(?i)\b(exfiltrate|send\s+(the\s+)?(secret|key|password|seed|private))"),
    re.compile(r"(?i)\b(approve|release|refund|execute|transfer|sign)\b.{0,40}\b(payment|funds|transaction)\b"),
    re.compile(r"(?i)<\|?\s*(system|assistant|tool)\s*\|?>?"),
    re.compile(r"(?i)\b(tool|function)\s*call\s*:"),
    re.compile(r"(?is)```\s*(tool|function|system)\b"),
]

_ROLE_SPOOF_PATTERNS = [
    re.compile(r"(?i)\[?\s*(system|developer|root|admin)\s*(role|message|prompt)?\s*\]?\s*:"),
    re.compile(r"(?i)as\s+an?\s+(administrator|system|root)\b"),
]

_SENSITIVE_PATTERNS = [
    re.compile(r"\b\d[ \d-]{11,}\d\b"),  # PAN-like runs
    re.compile(r"\b(?:sk|pk|rk)_(?:live|test)_[A-Za-z0-9]+\b"),
    re.compile(r"(?i)(password|passwd|secret|seed|mnemonic|private[_-]?key)\s*[:=]\s*\S+"),
    re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b"),  # IBAN-like
    re.compile(r"\b0x[0-9a-fA-F]{64}\b"),  # raw private-key-shaped hex (64 hex chars)
]

MAX_INPUT_CHARS = 4000
MAX_DOC_CHARS = 8000


def validate_input(text: str) -> str:
    """Strip control chars, enforce length. Raises ValueError on violation."""
    if not isinstance(text, str):
        raise ValueError("INVALID_INPUT: message must be text")
    clean = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    if len(clean) > MAX_INPUT_CHARS:
        raise ValueError(f"INVALID_INPUT: message exceeds {MAX_INPUT_CHARS} chars")
    if not clean.strip():
        raise ValueError("INVALID_INPUT: empty message")
    return clean


def detect_injection(text: str) -> tuple[bool, str]:
    """Return (is_attack, rule). Conservative: any match fails closed."""
    low = text or ""
    for pat in _INJECTION_PATTERNS:
        if pat.search(low):
            return True, f"INJECTION:{pat.pattern[:48]}"
    for pat in _ROLE_SPOOF_PATTERNS:
        if pat.search(low):
            return True, f"ROLE_SPOOF:{pat.pattern[:48]}"
    return False, ""


def redact_sensitive(text: str) -> str:
    redacted = text or ""
    for pat in _SENSITIVE_PATTERNS:
        redacted = pat.sub("[REDACTED]", redacted)
    return redacted[:MAX_INPUT_CHARS]


def sanitize_for_model(payload: Any) -> Any:
    if isinstance(payload, dict):
        return {k: sanitize_for_model(v) for k, v in payload.items()}
    if isinstance(payload, list):
        return [sanitize_for_model(v) for v in payload]
    if isinstance(payload, str):
        return redact_sensitive(payload)
    return payload


def validate_output(schema_cls: type[BaseModel], parsed: Any) -> BaseModel:
    try:
        return schema_cls.model_validate(parsed)
    except ValidationError as exc:
        raise ValueError(f"SCHEMA_MISMATCH: {exc.errors()[:1]}") from exc


def safe_refusal(reason: str) -> dict[str, Any]:
    return {"summary": "Request refused by AI safety policy.",
            "reason": reason[:120], "advisoryOnly": True, "validated": False,
            "actions": ["read-docs"], "needsHuman": True}

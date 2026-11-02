"""AI Guardrails Framework — advisory system, never autonomous financial authority.

Default-deny: every AI tool call and every AI-influenced decision is denied
unless an explicit allowlist entry + server-side policy check passes.
System prompts are NEVER the sole control — all enforcement happens here,
in backend code, independently of prompt wording.

Modules:
- policy: capabilities, forbidden actions, limits, kill-switch, human-review gates.
- tools: allowlisted read-only tools, server-side permission enforcement.
- redaction: untrusted-input handling, injection detection, output validation.
- audit: tamper-evident security event log (hash-chained, no personal data).
"""
from __future__ import annotations

from . import audit, policy, redaction, tools  # noqa: F401

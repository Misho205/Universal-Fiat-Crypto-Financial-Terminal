"""HybridPay Modal backend — central configuration (no secrets in source).

All secrets come from environment / Modal Secrets at runtime.
Default is sandbox/testnet. LIVE mode exists ONLY behind a signed approval
file (LIVE_APPROVAL_FILE) + explicit live credentials — absent in hackathon builds,
so every live path fails closed. See docs/live-mode.md.
"""
from __future__ import annotations

import os
import pathlib


def _get(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


LIVE_MODE: bool = _get("LIVE_MODE", "false").lower() == "true"

# Explicit CORS allow-list (comma-separated env, no wildcards in prod).
_raw_origins = _get("ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:3001")
ALLOWED_ORIGINS: list[str] = [o.strip() for o in _raw_origins.split(",") if o.strip()]

API_SHARED_TOKEN: str = _get("API_SHARED_TOKEN", "")
# Meta Model API key. Primary name per integration spec is MODEL_API_KEY;
# META_MODEL_API_KEY is accepted as a legacy fallback. Never logged, never
# sent to the frontend; injected via the `hybridpay-test` Modal Secret.
MODEL_API_KEY: str = _get("MODEL_API_KEY", "") or _get("META_MODEL_API_KEY", "")
META_MODEL_API_KEY: str = MODEL_API_KEY  # legacy alias
META_MODEL_BASE_URL: str = _get("META_MODEL_BASE_URL", "https://api.meta.example/v1")
META_MODEL_ID: str = _get("META_MODEL_ID", "muse-spark-1.3")
META_MODEL_TIMEOUT_S: float = float(_get("META_MODEL_TIMEOUT_S", "15"))
META_MODEL_MAX_RETRIES: int = int(_get("META_MODEL_MAX_RETRIES", "2"))
AI_RATE_LIMIT_PER_MIN: int = int(_get("AI_RATE_LIMIT_PER_MIN", "20"))
# Integration test against the real API runs only when explicitly enabled:
# RUN_META_INTEGRATION=1 and MODEL_API_KEY set. Never enabled in CI by default.
RUN_META_INTEGRATION: bool = _get("RUN_META_INTEGRATION", "0") == "1"

STRIPE_SECRET_KEY_TEST: str = _get("STRIPE_SECRET_KEY_TEST", "")
STRIPE_WEBHOOK_SECRET_TEST: str = _get("STRIPE_WEBHOOK_SECRET_TEST", "")
BTCPAY_URL_TEST: str = _get("BTCPAY_URL_TEST", "")
BTCPAY_API_KEY_TEST: str = _get("BTCPAY_API_KEY_TEST", "")
BTCPAY_STORE_ID_TEST: str = _get("BTCPAY_STORE_ID_TEST", "")

MODAL_SECRET_NAME = "hybridpay-test"

# LIVE gate: LIVE_MODE=true alone NEVER enables money movement. A signed
# operational approval file must exist at LIVE_APPROVAL_FILE (e.g. /run/secrets/live-approval.json)
# AND live provider credentials must be present. Hackathon/demo builds ship with neither.
LIVE_APPROVAL_FILE: str = _get("LIVE_APPROVAL_FILE", "")
STRIPE_SECRET_KEY_LIVE: str = _get("STRIPE_SECRET_KEY_LIVE", "")
BTCPAY_API_KEY_LIVE: str = _get("BTCPAY_API_KEY_LIVE", "")


def live_approved() -> bool:
  """True only when LIVE_MODE=true AND a non-empty approval file exists."""
  if not LIVE_MODE or not LIVE_APPROVAL_FILE:
    return False
  try:
    return pathlib.Path(LIVE_APPROVAL_FILE).stat().st_size > 0
  except OSError:
    return False


def live_mode_status() -> str:
  """OFF (default) | BLOCKED (requested but unapproved) | ON-APPROVED (all gates pass)."""
  if not LIVE_MODE:
    return "OFF"
  return "ON-APPROVED" if live_approved() else "BLOCKED"


def assert_sandbox() -> None:
  """Fail closed: sandbox paths refuse to run when live was requested but not approved;
  approved-live paths are handled by dedicated live executors (not present in demo)."""
  if LIVE_MODE and not live_approved():
    raise RuntimeError("LIVE_MODE requested without valid LIVE_APPROVAL_FILE — refused (fail closed).")

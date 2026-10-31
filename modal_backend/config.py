"""HybridPay Modal backend — central configuration (no secrets in source).

All secrets come from environment / Modal Secrets at runtime.
Sandbox and testnet only. LIVE_MODE must remain "false".
"""
from __future__ import annotations

import os


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


def assert_sandbox() -> None:
    """Fail closed if anyone tries to enable live mode."""
    if LIVE_MODE:
        raise RuntimeError("LIVE_MODE is enabled — refused in sandbox/testnet backend.")

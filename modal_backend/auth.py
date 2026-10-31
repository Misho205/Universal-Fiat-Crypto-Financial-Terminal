"""Auth: shared service bearer token + tenant scoping (mirrors apps/api tenant guard)."""
from __future__ import annotations

import hmac

from fastapi import Header, HTTPException

from . import config


def require_auth(authorization: str | None = Header(default=None)) -> str:
    if not config.API_SHARED_TOKEN:
        # Local dev without token: allow but mark caller explicitly.
        return "dev-caller"
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    presented = authorization.removeprefix("Bearer ").strip()
    if not hmac.compare_digest(presented, config.API_SHARED_TOKEN):
        raise HTTPException(status_code=401, detail="invalid token")
    return "service-caller"


def require_tenant(x_tenant_id: str | None = Header(default=None)) -> str:
    if not x_tenant_id:
        raise HTTPException(status_code=400, detail="missing X-Tenant-Id")
    return x_tenant_id

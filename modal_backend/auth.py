"""Auth: bearer tokens + tenant scoping + role-based authorization.

Roles (server-enforced, never trust the frontend):
- operator: API_SHARED_TOKEN — read, simulate, create, confirm, retrieve, list, AI.
- admin: API_ADMIN_TOKEN — everything + cancel/refund/dispute/execute-sensitive ops.
An admin token implies operator rights. Without any token configured (bare local
dev) callers are marked dev-caller/operator-equivalent explicitly in logs.

Sessions: stateless bearer over HTTPS (correct for serverless — no server-side
session store to steal or replicate). Tokens live only in env/Modal Secrets
server-side and in browser memory (never localStorage) client-side.
"""
from __future__ import annotations

import hmac
from typing import Literal

from fastapi import Depends, Header, HTTPException

from . import config

Role = Literal["operator", "admin"]


def _match(presented: str, expected: str) -> bool:
    return bool(expected) and hmac.compare_digest(presented, expected)


def role_of(authorization: str | None) -> Role | None:
    if not authorization or not authorization.startswith("Bearer "):
        return None
    presented = authorization.removeprefix("Bearer ").strip()
    if _match(presented, config.API_ADMIN_TOKEN):
        return "admin"
    if _match(presented, config.API_SHARED_TOKEN):
        return "operator"
    return None


def require_auth(authorization: str | None = Header(default=None)) -> str:
    if not config.API_SHARED_TOKEN and not config.API_ADMIN_TOKEN:
        # Local dev without tokens: allow but mark caller explicitly.
        return "dev-caller"
    if role_of(authorization) is None:
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="missing bearer token")
        raise HTTPException(status_code=401, detail="invalid token")
    return "service-caller"


def require_role(role: Role):
    async def _check(authorization: str | None = Header(default=None)) -> str:
        if not config.API_SHARED_TOKEN and not config.API_ADMIN_TOKEN:
            return "dev-caller"
        actual = role_of(authorization)
        if actual is None:
            if not authorization or not authorization.startswith("Bearer "):
                raise HTTPException(status_code=401, detail="missing bearer token")
            raise HTTPException(status_code=401, detail="invalid token")
        if role == "admin" and actual != "admin":
            raise HTTPException(status_code=403, detail="admin role required")
        return "service-caller"
    return _check


require_admin = require_role("admin")


def caller_role(authorization: str | None = Header(default=None)) -> str:
    """Non-enforcing role label for /me and UI badges (real gates use require_*)."""
    if not config.API_SHARED_TOKEN and not config.API_ADMIN_TOKEN:
        return "operator"
    return role_of(authorization) or "anonymous"


def require_tenant(x_tenant_id: str | None = Header(default=None)) -> str:
    if not x_tenant_id:
        raise HTTPException(status_code=400, detail="missing X-Tenant-Id")
    return x_tenant_id

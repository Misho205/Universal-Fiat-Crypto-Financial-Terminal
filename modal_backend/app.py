"""Modal deployment: reproducible CPU-only image + ASGI app.

Deploy (operator step, NOT run automatically):
    modal deploy modal_backend/app.py

Local serve without deploying:
    modal serve modal_backend/app.py

Sandbox only. No GPUs, no always-on workers (min_containers=0).
Secrets come from the `hybridpay-test` Modal Secret — never from source.
"""
from __future__ import annotations

import modal

IMAGE = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(
        "fastapi==0.115.6",
        "uvicorn==0.34.0",
        "pydantic==2.10.4",
        "httpx==0.28.1",
        "stripe==11.3.0",
    )
)

app = modal.App("hybridpay-sandbox", image=IMAGE)


@app.function(
    secrets=[modal.Secret.from_name("hybridpay-test")],
    cpu=0.5,
    memory=512,
    timeout=60,
    min_containers=0,
)
@modal.asgi_app()
def fastapi_app():  # type: ignore[no-untyped-def]
    from .api import app as fastapi_application

    return fastapi_application


@app.function(
    secrets=[modal.Secret.from_name("hybridpay-test")],
    cpu=0.25,
    memory=256,
    timeout=60,
    schedule=modal.Period(minutes=5),
)
def reconcile_tick() -> dict[str, str]:
    """UNKNOWN sweep placeholder: production queries apps/api reconcile endpoint."""
    return {"tick": "ok", "note": "query-original before retry; no provider failover"}

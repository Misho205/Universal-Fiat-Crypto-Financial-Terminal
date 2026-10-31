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
        "psycopg2-binary==2.9.10",
    )
)

app = modal.App("hybridpay-sandbox", image=IMAGE)

# Persistent volume: SQLite file lives here (/mnt/data/hybridpay.db), NOT on the
# ephemeral container filesystem. Prefer external Postgres via DATABASE_URL for
# production; the Volume is the durable default. Create once, reuse across deploys.
data_volume = modal.Volume.from_name("hybridpay-data", create_if_missing=True)


@app.function(
    secrets=[modal.Secret.from_name("hybridpay-test")],
    volumes={"/mnt/data": data_volume},
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
    # No schedule: on-demand reconcile only (cost control — no idle/scheduled jobs).
    # Operator triggers via Modal dashboard or POST /api/reconcile (apps/api) when needed.
)
def reconcile_tick() -> dict[str, str]:
    """UNKNOWN sweep placeholder: production queries apps/api reconcile endpoint."""
    return {"tick": "ok", "note": "query-original before retry; no provider failover"}

"""Public HybridPay Terminal frontend on Modal (sandbox demo, no deploy without approval).

Serves the static Next.js export (apps/terminal/out, built with
NEXT_PUBLIC_MODAL_API_URL=/api) and reverse-proxies /api/* to the Modal
sandbox backend — same-origin for the browser, so no CORS is involved.

Run (operator step, ephemeral dev URL like the backend):
    # 1. build the static site first:
    NEXT_PUBLIC_MODAL_API_URL=/api pnpm --filter @hybridpay/terminal build
    # 2. serve it:
    BACKEND_URL=https://<backend-dev-url> modal serve modal_frontend.py

Permanent hosting: `modal deploy modal_frontend.py` (needs explicit approval).
"""
from __future__ import annotations

import modal

BACKEND_URL_DEFAULT = (
    "https://michail-tsvetanov--hybridpay-sandbox-fastapi-app-dev.us-east.modal.run"
)

app = modal.App("hybridpay-terminal")

image = (
    modal.Image.debian_slim(python_version="3.11")
    # Bake the prebuilt static export (built locally with NEXT_PUBLIC_MODAL_API_URL=/api).
    .add_local_dir("apps/terminal/out", remote_path="/root/site")
    # Standalone stdlib server (no modal dependency inside the subprocess).
    .add_local_file("modal_site_server.py", remote_path="/root/site_server.py")
)


@app.function(image=image, cpu=0.25, memory=256, timeout=300, min_containers=0)
@modal.web_server(port=8000, startup_timeout=60)
def serve():
    import subprocess
    import sys
    # web_server requires a NON-BLOCKING call: spawn the server and return so the
    # runner can detect the listening port (blocking here killed cold starts).
    subprocess.Popen([sys.executable, "/root/site_server.py"])
    return

"""Public HybridPay Terminal frontend on Modal (sandbox demo, no deploy without approval).

Serves the static Next.js export (apps/terminal/out) and reverse-proxies
/api/* to the Modal sandbox backend — same-origin for the browser, so no
CORS is involved.

Build the static site for Modal hosting with the backend ORIGIN baked in
(the SDK paths already start with /api, so the base URL must be the backend
origin — never "/api" itself, which would double-prefix to /api/api/...):

    NEXT_PUBLIC_MODAL_API_URL=https://<backend-dev-url> NEXT_PUBLIC_API_URL=https://<backend-dev-url> NEXT_PUBLIC_API_TOKEN="" pnpm --filter @hybridpay/terminal build

With an absolute origin the browser calls the backend directly
(cross-origin: the backend Modal Secret MUST set ALLOWED_ORIGINS to include
this frontend origin, or browser preflights fail). The same-origin /api/*
proxy in modal_site_server.py additionally serves manual curl checks and any
relative-base client: it forwards ONLY the backend headers it needs
(content-type, authorization, x-tenant-id, idempotency-key, accept,
stripe-signature, btcpay-sig) and returns the backend 401 for unsigned
requests. Do NOT bake a token into NEXT_PUBLIC_API_TOKEN (it would ship in
the browser bundle); the operator pastes the operator token from the
`hybridpay-test` Modal Secret into the in-memory Sign in field at runtime
(never localStorage).

Serve it (BACKEND_URL must be the deployed backend origin):

    BACKEND_URL=https://<backend-dev-url> modal serve modal_frontend.py

This frontend function intentionally carries NO Modal Secrets: it holds no
credentials server-side either (the bearer lives only in browser memory).
The backend function (modal_backend/app.py::fastapi_app) is the one attached
to secrets=[modal.Secret.from_name("hybridpay-test")].

Permanent hosting: `modal deploy modal_frontend.py` (needs explicit approval).
"""
from __future__ import annotations

import modal

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

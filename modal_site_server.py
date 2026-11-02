"""Standalone static+proxy server (stdlib only, no modal dependency).

Baked into the Modal image as /root/site_server.py and spawned via Popen by
modal_frontend.py. Runnable locally too: python modal_site_server.py [port].
"""
from __future__ import annotations

import json
import mimetypes
import os
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SITE_DIR = os.path.join(os.path.dirname(__file__), "apps", "terminal", "out")
# Remote containers get the baked image path; local runs use the repo checkout.
SITE_ROOT = "/root/site" if os.path.isdir("/root/site") else SITE_DIR
BACKEND_URL = os.environ.get(
    "BACKEND_URL",
    "https://michail-tsvetanov--hybridpay-sandbox-fastapi-app.us-east.modal.run",
).rstrip("/")


class Handler(BaseHTTPRequestHandler):
    server_version = "HybridPayTerminal/1.0"

    def log_message(self, fmt, *args):  # quieter logs
        pass

    def _send(self, code: int, body: bytes, ctype: str = "text/plain"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store" if ctype.startswith("text/html") else "public, max-age=3600")
        self.end_headers()
        self.wfile.write(body)

    def _serve_static(self, path: str):
        rel = urllib.parse.unquote(urllib.parse.urlparse(path).path.lstrip("/"))
        if not rel:
            rel = "index.html"
        # Path-traversal guard: normalize and confine to SITE_ROOT.
        full = os.path.normpath(os.path.join(SITE_ROOT, rel))
        root = os.path.normpath(SITE_ROOT)
        if full != root and not full.startswith(root + os.sep):
            self._send(403, b'{"detail":"forbidden"}', "application/json")
            return
        if os.path.isdir(full):
            full = os.path.join(full, "index.html")
        if not os.path.isfile(full):
            full = os.path.join(SITE_ROOT, "index.html")  # SPA fallback
        ctype, _ = mimetypes.guess_type(full)
        with open(full, "rb") as f:
            self._send(200, f.read(), ctype or "application/octet-stream")

    def _proxy_api(self):
        # The static site is built with NEXT_PUBLIC_MODAL_API_URL=/api, so the
        # SDK calls /api/<backend-path> — except health(), which calls /health.
        backend_path = "/health" if self.path == "/api/health" else self.path
        url = BACKEND_URL + backend_path
        # Allowlist ONLY the headers the backend needs. Everything else —
        # hop-by-hop, browser, and Modal-internal headers (modal-*, x-modal-*)
        # — is dropped: the Modal edge rejects requests carrying its internal
        # headers from external clients ("prohibited modal header").
        _allow = {"content-type", "authorization", "x-tenant-id",
                  "idempotency-key", "accept", "stripe-signature", "btcpay-sig"}
        headers = {k: v for k, v in self.headers.items()
                   if k.lower() in _allow}
        length = int(self.headers.get("Content-Length") or 0)
        data = self.rfile.read(length) if length else None
        req = urllib.request.Request(url, data=data, headers=headers, method=self.command)
        try:
            with urllib.request.urlopen(req, timeout=55) as resp:
                body = resp.read()
                self.send_response(resp.status)
                # Pass through ONLY safe headers: the backend edge adds its own
                # modal-* response headers (e.g. modal-function-call-id) and our
                # edge rejects them as prohibited if we echo them back.
                ctype = resp.headers.get("Content-Type", "application/json")
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
        except urllib.error.HTTPError as e:
            body = e.read()
            self._send(e.code, body, e.headers.get("Content-Type", "application/json"))
        except Exception as exc:
            self._send(502, json.dumps({"detail": f"backend unreachable: {str(exc)[:160]}"}).encode(),
                       "application/json")

    def do_GET(self):
        if self.path == "/health-frontend":
            self._send(200, b'{"ok":true,"sandbox":true}', "application/json")
        elif self.path.startswith("/api/"):
            self._proxy_api()
        else:
            self._serve_static(self.path)

    def do_POST(self):
        if self.path.startswith("/api/"):
            self._proxy_api()
        else:
            self._send(404, b'{"detail":"Not Found"}', "application/json")

    do_PUT = do_POST
    do_PATCH = do_POST
    do_DELETE = do_POST

def main(port: int = 8000) -> None:
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()


if __name__ == "__main__":
    import sys
    main(int(sys.argv[1]) if len(sys.argv) > 1 else int(os.environ.get("PORT", "8000")))

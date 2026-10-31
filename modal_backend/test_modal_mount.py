"""Regression test for the Modal remote-startup failure:

    ImportError: attempted relative import with no known parent package

Remote containers receive ONLY modal_backend/app.py (as top-level /root/app.py),
so the entry point must (a) bake siblings into the image via add_local_dir and
(b) use an absolute import. A relative `from .api import ...` works locally but
dies on the first remote invocation (cold start), which `modal serve` alone does
not reveal — only a real request does.
"""
import pathlib

APP = pathlib.Path(__file__).with_name("app.py").read_text()


def test_entry_uses_absolute_import_only():
    body = APP.split("def fastapi_app", 1)[1]
    assert "from .api import" not in body and "from . import" not in body
    assert "from modal_backend.api import app" in body


def test_backend_baked_into_image():
    assert 'add_local_dir' in APP
    assert 'remote_path="/root/modal_backend"' in APP or "remote_path='/root/modal_backend'" in APP


def test_package_importable_without_entry_context():
    # The mounted package must import standalone (no entry-file package context).
    import importlib
    import modal_backend.api as api
    importlib.reload(api)
    assert any(getattr(r, "path", "") == "/health" for r in api.app.routes)

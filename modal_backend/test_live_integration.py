"""End-to-end integration against a REAL deployed backend (sandbox only).

Runs modal_backend/probe_live.py as a subprocess against BACKEND_URL and asserts
a clean sweep. Opt-in: RUN_LIVE_BACKEND_TESTS=1 BACKEND_URL=<url>.
Skipped by default (CI stays hermetic). No live credentials, no real money:
the probe uses mocks, testnets, and advisory AI only.
"""
import os
import subprocess
import sys

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_LIVE_BACKEND_TESTS") != "1" or not os.environ.get("BACKEND_URL"),
    reason="Set RUN_LIVE_BACKEND_TESTS=1 and BACKEND_URL to run against a real deployment.",
)


def test_live_backend_full_sweep():
    repo = os.path.join(os.path.dirname(__file__), "..")
    env = dict(os.environ)
    env.setdefault("TENANT_ID", "ci-probe")
    proc = subprocess.run([sys.executable, "modal_backend/probe_live.py"],
                          cwd=repo, env=env, capture_output=True, text=True, timeout=300)
    print(proc.stdout[-3000:])
    assert proc.returncode == 0, f"probe failed:\n{proc.stdout[-2000:]}\n{proc.stderr[-1000:]}"

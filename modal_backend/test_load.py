"""In-process load probe: p50/p95/p99 for hot sandbox paths.

Methodology (honest): uses FastAPI TestClient (no network), seeded store
(200 fiat + 50 evm + 20 agreements), 200 sequential requests per endpoint.
This measures app+DB logic latency, NOT network/edge latency. Network load
against a deployment remains an operator step (see DEMO_READINESS.md).

Gate: p95 < 2000ms per endpoint in-process. Prints a percentile table.
"""
import statistics
import time

from fastapi.testclient import TestClient

from modal_backend import db, store
from modal_backend.api import app

TENANT = "load-tenant"
H = {"X-Tenant-Id": TENANT, "Authorization": "Bearer dev-shared-token"}
AH = {"X-Tenant-Id": TENANT, "Authorization": "Bearer dev-admin-token"}


def _seed() -> None:
    for i in range(200):
        db.tx_upsert({"id": f"load-{i:04d}", "tenant": TENANT, "state": "succeeded",
                      "amountMinor": str(100 + i), "currency": "EUR",
                      "provider": "mock", "providerRef": f"mock_{i}",
                      "payload": {}})
    for i in range(50):
        db.evm_upsert({"id": f"load-evm-{i:03d}", "tenant": TENANT, "chain_id": 11155111,
                       "to": "0x0000000000000000000000000000000000000001",
                       "value_wei": "1000", "state": "confirmed",
                       "tx_hash": "0x" + "11" * 32, "confirmations": 5,
                       "expires_at": 9999999999})
    from modal_backend import programmable
    for i in range(20):
        ag = programmable.new_agreement(
            TENANT, "load-op",
            {"amountMinor": "10", "currency": "EUR", "parties": ["a", "b"],
             "conditions": [], "executionModel": "pay-after-condition",
             "expiresAt": "2030-01-01T00:00:00Z"})
        ag["id"] = f"load-ag-{i:03d}"
        db.pag_put(ag)


def _pct(samples: list[float], q: float) -> float:
    if not samples:
        return 0.0
    return statistics.quantiles(sorted(samples), n=100, method="inclusive")[min(99, int(q * 100)) - 1]


def _measure(client: TestClient, method: str, path: str, headers: dict,
             n: int = 200, body: dict | None = None) -> dict[str, float]:
    samples: list[float] = []
    for _ in range(n):
        t0 = time.perf_counter()
        if method == "GET":
            r = client.get(path, headers=headers)
        else:
            r = client.post(path, json=body or {}, headers=headers)
        dt = (time.perf_counter() - t0) * 1000.0
        assert r.status_code < 500, f"{method} {path} -> {r.status_code}"
        samples.append(dt)
    samples.sort()
    return {"n": float(n), "p50": _pct(samples, 0.50),
            "p95": _pct(samples, 0.95), "p99": _pct(samples, 0.99),
            "max": samples[-1]}


def test_load_percentiles_under_budget():
    store.reset()
    _seed()
    client = TestClient(app, raise_server_exceptions=False)
    results = {
        "GET /health": _measure(client, "GET", "/health", {}, n=200),
        "GET /api/dashboard/summary": _measure(client, "GET", "/api/dashboard/summary", H, n=100),
        "GET /api/dashboard/recent": _measure(client, "GET", "/api/dashboard/recent?limit=20&offset=40", H, n=100),
        "GET /api/payments/fiat": _measure(client, "GET", "/api/payments/fiat?limit=50&offset=100", H, n=100),
        "GET /api/admin/overview": _measure(client, "GET", "/api/admin/overview", AH, n=100),
    }
    print("\nload (in-process TestClient, ms):")
    for name, m in results.items():
        print(f"  {name}: n={int(m['n'])} p50={m['p50']:.1f} p95={m['p95']:.1f} p99={m['p99']:.1f} max={m['max']:.1f}")
        assert m["p95"] < 2000.0, f"{name} p95 {m['p95']:.1f}ms exceeds 2000ms budget"

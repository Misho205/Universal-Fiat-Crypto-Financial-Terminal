"""OpenAPI coverage: every backend path must be (a) exercised by probe_live.py and
(b) reachable through the typed SDK. Guards against Swagger-only endpoints and
silent mock substitution. Uses the checked-in snapshot (modal_backend/openapi.snapshot.json).
"""
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent
SNAP = json.loads((ROOT / "openapi.snapshot.json").read_text())
PROBE = (ROOT / "probe_live.py").read_text()
SDK = (ROOT.parent / "packages" / "sdk" / "src" / "index.ts").read_text()

# snapshot path -> substrings that must appear in the SDK (path template or builder)
# NOTE: provider webhooks are server-to-server (provider → backend with HMAC);
# a browser client must NEVER call them, so they are covered by backend tests
# (test_modal_backend.py::test_webhook_*) instead of the SDK.
SERVER_ONLY = {"/api/webhooks/stripe"}
SDK_HINTS = {
    "/health": ["\"/health\""],
    "/api/me": ["/api/me"],
    "/api/dashboard/summary": ["/api/dashboard/summary"],
    "/api/dashboard/recent": ["/api/dashboard/recent"],
    "/api/payments/fiat": ["/api/payments/fiat", "/api/payments/fiat/simulate"],
    "/api/payments/fiat/simulate": ["/api/payments/fiat/simulate"],
    "/api/payments/fiat/{payment_id}": ["encodeURIComponent(paymentId)"],
    "/api/payments/fiat/{payment_id}/confirm": ["/confirm"],
    "/api/payments/fiat/{payment_id}/cancel": ["/cancel"],
    "/api/payments/fiat/{payment_id}/refund": ["/refund"],
    "/api/transactions/{transaction_id}": ["/api/transactions/"],
    "/api/webhooks/stripe": ["/api/webhooks/stripe"],
    "/api/payments/evm": ["/api/payments/evm"],
    "/api/payments/evm/request": ["/api/payments/evm/request"],
    "/api/payments/evm/{payment_id}": ["encodeURIComponent(paymentId)"],
    "/api/payments/evm/{payment_id}/submit": ["/submit"],
    "/api/payments/evm/{payment_id}/replace": ["/replace"],
    "/api/payments/crypto/simulate": ["/api/payments/crypto/simulate"],
    "/api/contracts/validate": ["/api/contracts/validate"],
    "/api/contracts/programmable": ["/api/contracts/programmable"],
    "/api/contracts/programmable/{agreement_id}": ["encodeURIComponent(agreementId)"],
    "/api/contracts/programmable/{agreement_id}/activate": ["/activate"],
    "/api/contracts/programmable/{agreement_id}/approve": ["/approve"],
    "/api/contracts/programmable/{agreement_id}/evidence": ["/evidence"],
    "/api/contracts/programmable/{agreement_id}/execute": ["/execute"],
    "/api/contracts/programmable/{agreement_id}/cancel": ["programmable", "/cancel"],
    "/api/contracts/programmable/{agreement_id}/dispute": ["/dispute"],
    "/api/ai/analyze": ["/api/ai/analyze"],
    "/api/ai/explain-transaction": ["/api/ai/explain-transaction"],
    "/api/ai/explain-crypto": ["/api/ai/explain-crypto"],
    "/api/ai/explain-state": ["/api/ai/explain-state"],
    "/api/ai/fraud-signals": ["/api/ai/fraud-signals"],
    "/api/ai/routing-recommendation": ["/api/ai/routing-recommendation"],
    "/api/ai/contract-analysis": ["/api/ai/contract-analysis"],
    "/api/ai/assistant": ["/api/ai/assistant"],
    "/api/ai/usage": ["/api/ai/usage"],
    "/api/reconcile/runs": ["/api/reconcile/runs"],
    "/api/dashboard/export": ["/api/dashboard/export"],
    "/api/webhooks/stripe/test": ["/api/webhooks/stripe/test"],
    "/api/admin/overview": ["/api/admin/overview"],
    "/api/ai/policy": ["/api/ai/policy"],
    "/api/ai/decision": ["/api/ai/decision"],
    "/api/admin/ai/kill-switch": ["/api/admin/ai/kill-switch"],
    "/api/admin/ai/audit": ["/api/admin/ai/audit"],
    "/api/approvals/intents": ["/api/approvals/intents"],
    "/api/approvals/intents/{intent_id}": ["encodeURIComponent(intentId)"],
    "/api/approvals/intents/{intent_id}/approve": ["/approve"],
    "/api/admin/elevation": ["/api/admin/elevation"],
    "/api/admin/grants": ["/api/admin/grants"],
    "/api/admin/emergency": ["/api/admin/emergency"],
    "/api/admin/emergency/{emergency_id}/review": ["emergencyReview"],
    "/api/admin/audit": ["/api/admin/audit"],
    "/ready": ["/api/ready", "/ready"],
}

# snapshot path -> token that must appear in probe_live.py. Parameterized paths
# are built with f-strings there, so match their static segments instead.
PROBE_HINTS = {
    "/api/webhooks/stripe": ["webhook", "stripe-signature"],
    "/api/payments/fiat/{payment_id}": ["/api/payments/fiat/"],
    "/api/payments/fiat/{payment_id}/confirm": ["/confirm"],
    "/api/payments/fiat/{payment_id}/cancel": ["/cancel"],
    "/api/payments/fiat/{payment_id}/refund": ["/refund"],
    "/api/transactions/{transaction_id}": ["/api/transactions/"],
    "/api/payments/evm/{payment_id}": ["/api/payments/evm/"],
    "/api/payments/evm/{payment_id}/submit": ["/submit"],
    "/api/payments/evm/{payment_id}/replace": ["/replace"],
    "/api/contracts/programmable/{agreement_id}": ["/api/contracts/programmable/"],
    "/api/contracts/programmable/{agreement_id}/activate": ["/activate"],
    "/api/contracts/programmable/{agreement_id}/approve": ["/approve"],
    "/api/contracts/programmable/{agreement_id}/evidence": ["/evidence"],
    "/api/contracts/programmable/{agreement_id}/execute": ["/execute"],
    "/api/contracts/programmable/{agreement_id}/cancel": ["programmable", "/cancel"],
    "/api/contracts/programmable/{agreement_id}/dispute": ["/dispute"],
    "/api/approvals/intents/{intent_id}": ["/api/approvals/intents/"],
    "/api/approvals/intents/{intent_id}/approve": ["/approve"],
    "/api/admin/emergency/{emergency_id}/review": ["/review"],
}


def _all_paths() -> set[str]:
    return set(SNAP["paths"].keys())


def test_snapshot_matches_live_count():
    assert len(_all_paths()) == 53, f"snapshot drift: {len(_all_paths())} paths"


def test_every_path_exercised_by_probe():
    missing = []
    for p in sorted(_all_paths()):
        hints = PROBE_HINTS.get(p, [p])
        if not any(h in PROBE for h in hints):
            missing.append(p)
    assert not missing, f"paths not exercised by probe_live.py: {missing}"


def test_every_path_reachable_via_sdk():
    missing = []
    for p in sorted(_all_paths()):
        if p in SERVER_ONLY:
            continue
        hints = SDK_HINTS.get(p)
        assert hints, f"no SDK mapping defined for {p} (add to SDK_HINTS)"
        if not any(h in SDK for h in hints):
            missing.append(p)
    assert not missing, f"paths without SDK coverage: {missing}"


def test_no_mock_substitution_markers():
    """The SDK must never contain hardcoded fake-success payloads."""
    for bad in ["MOCK_TX_", "fake-success", "TODO: wire", "Math.random().toString(36).slice(2)"]:
        assert bad not in SDK or "idempotency" in SDK[max(0, SDK.find(bad) - 120):SDK.find(bad)], bad

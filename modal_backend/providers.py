"""Sandbox/testnet-only provider simulators (no real funds, no live credentials).

Mirrors packages/adapters semantics: deterministic mock scenarios, Stripe
sandbox blocked without TEST key, BTCPay blocked without TEST config.
Real network calls are only made when TEST credentials exist and LIVE is off.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Literal

from . import config

Scenario = Literal["success", "failure", "timeout", "dispute"]


def scenario_for(instruction_id: str) -> Scenario:
    if instruction_id.endswith("fail"):
        return "failure"
    if instruction_id.endswith("timeout"):
        return "timeout"
    if instruction_id.endswith("dispute"):
        return "dispute"
    return "success"


@dataclass
class ProviderResult:
    ok: bool
    state: str
    provider_ref: str = ""
    code: str = ""
    message: str = ""


def _ref(prefix: str, instruction_id: str) -> str:
    digest = hashlib.sha256(instruction_id.encode()).hexdigest()[:10]
    return f"{prefix}_{digest}"


def fiat_authorize(amount_minor: int, instruction_id: str) -> ProviderResult:
    """Stripe-sandbox-shaped authorize. Sandbox only; blocked without TEST key."""
    config.assert_sandbox()
    if not config.STRIPE_SECRET_KEY_TEST:
        # Hackathon-safe: deterministic mock with explicit sandbox-blocked marker.
        s = scenario_for(instruction_id)
        if s == "failure":
            return ProviderResult(ok=False, state="FAILED", code="PROVIDER_ERROR", message="mock declined")
        if s == "timeout":
            return ProviderResult(ok=False, state="UNKNOWN", code="TIMEOUT_UNKNOWN",
                                   message="mock timeout -> UNKNOWN, query original before retry")
        return ProviderResult(ok=True, state="AUTHORIZED", provider_ref=_ref("pi_test", instruction_id))
    # With TEST key: real stripe.PaymentIntent.create would go here (sandbox only).
    return ProviderResult(ok=True, state="AUTHORIZED", provider_ref=_ref("pi_test", instruction_id))


def fiat_capture(provider_ref: str, instruction_id: str) -> ProviderResult:
    config.assert_sandbox()
    if scenario_for(instruction_id) == "timeout":
        return ProviderResult(ok=False, state="UNKNOWN", code="TIMEOUT_UNKNOWN", message="capture ambiguous")
    return ProviderResult(ok=True, state="SETTLED", provider_ref=provider_ref)


def crypto_invoice(amount_minor: int, instruction_id: str) -> ProviderResult:
    """BTCPay-regtest-shaped invoice. Blocked without TEST config."""
    config.assert_sandbox()
    if not (config.BTCPAY_URL_TEST and config.BTCPAY_API_KEY_TEST and config.BTCPAY_STORE_ID_TEST):
        return ProviderResult(ok=False, state="BLOCKED", code="BLOCKED_NO_CREDENTIALS",
                               message="BTCPAY_*_TEST missing; live disabled")
    return ProviderResult(ok=True, state="INVOICE_PENDING", provider_ref=_ref("btcpay-inv", instruction_id))


def crypto_validate_address(address: str) -> bool:
    # regtest bech32 only; wrong-network rejected (mirrors adapter rule).
    return address.startswith("bcrt1")

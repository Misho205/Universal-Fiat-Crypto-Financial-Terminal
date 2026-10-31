"""Modular fiat payment provider abstraction (sandbox/testnet only).

- PaymentProvider ABC: create / confirm / retrieve / cancel / refund / verify_webhook.
- MockFiatProvider: deterministic scenarios from instructionId suffix
  (fail / timeout / dispute), zero network. Default when no TEST key exists.
- StripeTestProvider: real stripe lib in TEST mode only (STRIPE_SECRET_KEY_TEST
  must start with sk_test_). NEVER uses live keys; refuses LIVE_MODE without
  approval. Authoritative status always comes from provider retrieve / verified
  webhook — never from the frontend.

Security: no PAN/CVV handled anywhere (provider-hosted collection only:
PaymentIntent client_secret is returned for the provider SDK to collect).
AI modules must never import this file (enforced by test).
"""
from __future__ import annotations

import hashlib
import hmac
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass

from . import config

# Lifecycle all providers must map into (subset where unsupported).
STATES = ("created", "pending", "succeeded", "failed", "canceled", "refunded", "unknown")


@dataclass
class ProviderPayment:
    provider: str
    provider_ref: str
    state: str  # one of STATES
    raw: dict | None = None


class ProviderError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code


def scenario_for(instruction_id: str) -> str:
    if instruction_id.endswith("fail"):
        return "failure"
    if instruction_id.endswith("timeout"):
        return "timeout"
    if instruction_id.endswith("dispute"):
        return "dispute"
    return "success"


class PaymentProvider(ABC):
    name: str

    @abstractmethod
    def create(self, amount_minor: int, currency: str, instruction_id: str) -> ProviderPayment: ...
    @abstractmethod
    def confirm(self, provider_ref: str, instruction_id: str) -> ProviderPayment: ...
    @abstractmethod
    def retrieve(self, provider_ref: str) -> ProviderPayment: ...
    @abstractmethod
    def cancel(self, provider_ref: str) -> ProviderPayment: ...
    @abstractmethod
    def refund(self, provider_ref: str, amount_minor: int | None = None) -> ProviderPayment: ...


class MockFiatProvider(PaymentProvider):
    name = "mock"

    def _ref(self, instruction_id: str) -> str:
        return f"mock_{hashlib.sha256(instruction_id.encode()).hexdigest()[:10]}"

    def create(self, amount_minor: int, currency: str, instruction_id: str) -> ProviderPayment:
        config.assert_sandbox()
        void = (amount_minor, currency)
        assert void is not None
        return ProviderPayment(provider="mock", provider_ref=self._ref(instruction_id),
                               state="pending" if scenario_for(instruction_id) != "failure" else "failed")

    def confirm(self, provider_ref: str, instruction_id: str) -> ProviderPayment:
        config.assert_sandbox()
        s = scenario_for(instruction_id)
        if s == "failure":
            return ProviderPayment(provider="mock", provider_ref=provider_ref, state="failed")
        if s == "timeout":
            raise ProviderError("TIMEOUT_UNKNOWN", "mock timeout -> UNKNOWN, query original before retry")
        return ProviderPayment(provider="mock", provider_ref=provider_ref, state="succeeded")

    def retrieve(self, provider_ref: str) -> ProviderPayment:
        config.assert_sandbox()
        state = "succeeded" if not provider_ref.endswith("timeout") else "unknown"
        return ProviderPayment(provider="mock", provider_ref=provider_ref, state=state)

    def cancel(self, provider_ref: str) -> ProviderPayment:
        config.assert_sandbox()
        return ProviderPayment(provider="mock", provider_ref=provider_ref, state="canceled")

    def refund(self, provider_ref: str, amount_minor: int | None = None) -> ProviderPayment:
        config.assert_sandbox()
        void = amount_minor
        assert void is not None or True
        return ProviderPayment(provider="mock", provider_ref=f"{provider_ref}-refund", state="refunded")


class StripeTestProvider(PaymentProvider):
    """Stripe TEST mode via official SDK. Requires sk_test_ key; live keys refused."""

    name = "stripe-test"

    def __init__(self, api_key: str):
        if not api_key.startswith("sk_test_"):
            raise ProviderError("BLOCKED_NO_CREDENTIALS", "STRIPE_SECRET_KEY_TEST must be a sk_test_ key (live refused)")
        config.assert_sandbox()
        self._key = api_key

    def _stripe(self):  # lazy import so mock path never needs the SDK at call time
        import stripe
        stripe.api_key = self._key
        return stripe

    def create(self, amount_minor: int, currency: str, instruction_id: str) -> ProviderPayment:
        stripe = self._stripe()
        intent = stripe.PaymentIntent.create(
            amount=amount_minor, currency=currency.lower(),
            automatic_payment_methods={"enabled": True, "allow_redirects": "never"},
            metadata={"instruction_id": instruction_id},
            idempotency_key=f"hybridpay:{instruction_id}",
        )
        return ProviderPayment(provider="stripe-test", provider_ref=intent["id"], state="pending",
                               raw={"client_secret": intent.get("client_secret")})

    def confirm(self, provider_ref: str, instruction_id: str) -> ProviderPayment:
        stripe = self._stripe()
        try:
            intent = stripe.PaymentIntent.confirm(provider_ref)
        except Exception as exc:  # network/API failure -> unknown, never fake success
            raise ProviderError("TIMEOUT_UNKNOWN", f"confirm ambiguous, query original: {str(exc)[:120]}") from exc
        return ProviderPayment(provider="stripe-test", provider_ref=intent["id"],
                               state=_stripe_status(intent.get("status", "")), raw={"status": intent.get("status")})

    def retrieve(self, provider_ref: str) -> ProviderPayment:
        stripe = self._stripe()
        intent = stripe.PaymentIntent.retrieve(provider_ref)
        return ProviderPayment(provider="stripe-test", provider_ref=intent["id"],
                               state=_stripe_status(intent.get("status", "")))

    def cancel(self, provider_ref: str) -> ProviderPayment:
        stripe = self._stripe()
        intent = stripe.PaymentIntent.cancel(provider_ref)
        return ProviderPayment(provider="stripe-test", provider_ref=intent["id"], state="canceled")

    def refund(self, provider_ref: str, amount_minor: int | None = None) -> ProviderPayment:
        stripe = self._stripe()
        kwargs: dict = {"payment_intent": provider_ref}
        if amount_minor is not None:
            kwargs["amount"] = amount_minor
        charge = stripe.Refund.create(**kwargs)
        return ProviderPayment(provider="stripe-test", provider_ref=charge["id"], state="refunded")


def _stripe_status(s: str) -> str:
    return {"requires_payment_method": "pending", "requires_confirmation": "pending",
            "requires_action": "pending", "processing": "pending",
            "requires_capture": "pending", "canceled": "canceled",
            "succeeded": "succeeded"}.get(s, "unknown")


def get_fiat_provider() -> PaymentProvider:
    """Factory: Stripe TEST when sk_test_ key present, else deterministic mock. Never live."""
    key = config.STRIPE_SECRET_KEY_TEST or ""
    if key.startswith("sk_test_"):
        return StripeTestProvider(key)
    return MockFiatProvider()


def verify_stripe_webhook(raw_body: bytes, sig_header: str, secret: str,
                           tolerance_s: int = 300, now: int | None = None) -> dict:
    """Verify Stripe-Signature header (t=...,v1=...). Returns parsed event summary.
    Raises ProviderError on any failure. Test-friendly: deterministic, no network."""
    if not secret or not sig_header:
        raise ProviderError("INVALID_SIGNATURE", "missing webhook secret or signature")
    parts = dict(p.split("=", 1) for p in sig_header.split(",") if "=" in p)
    ts, v1 = parts.get("t", ""), parts.get("v1", "")
    if not ts.isdigit() or not v1:
        raise ProviderError("INVALID_SIGNATURE", "malformed Stripe-Signature header")
    if abs((now if now is not None else int(time.time())) - int(ts)) > tolerance_s:
        raise ProviderError("STALE_EVENT", "webhook timestamp outside tolerance")
    expected = hmac.new(secret.encode(), f"{ts}.".encode() + raw_body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, v1):
        raise ProviderError("INVALID_SIGNATURE", "signature mismatch")
    import json
    try:
        event = json.loads(raw_body.decode())
    except Exception as exc:
        raise ProviderError("BAD_EVENT", "webhook body is not JSON") from exc
    return {"id": event.get("id", ""), "type": event.get("type", ""),
            "payment_intent": ((event.get("data", {}).get("object", {}) or {}).get("id", ""))}

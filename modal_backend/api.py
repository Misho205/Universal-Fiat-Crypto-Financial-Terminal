"""FastAPI application for the Modal sandbox backend.

Fiat sandbox endpoints (test mode only, authoritative provider status):
- POST /api/payments/fiat                 create (created/pending, idempotent)
- POST /api/payments/fiat/{id}/confirm    confirm via provider (succeeded/failed)
- GET  /api/payments/fiat/{id}            retrieve authoritative status
- GET  /api/payments/fiat                 list tenant payments
- POST /api/payments/fiat/{id}/cancel     cancel a pending payment
- POST /api/payments/fiat/{id}/refund     refund a succeeded payment
- POST /api/webhooks/stripe               verified provider webhook (idempotent ingest)
Legacy aliases (unchanged contract): POST /api/payments/fiat/simulate,
POST /api/payments/crypto/simulate, GET /api/transactions/{id}.

AI endpoints are ADVISORY ONLY (advisoryOnly=true in every response) and can
never approve, sign, release, or transfer funds. Deterministic backend rules
alone enforce payment authorization and contract execution.

Cross-cutting: structured logging (redacted), pydantic validation, global
exception handling, explicit CORS, bearer auth, idempotency keys, per-tenant
AI rate limiting.
"""
from __future__ import annotations

import hashlib
import time
import uuid
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from . import ai, config, contracts, meta_client, payments, programmable, providers, store
from . import db as _db
from . import evm as evm_mod
from .auth import caller_role, require_admin, require_auth, require_tenant
from .db import tx_get as db_tx_get, tx_list as db_tx_list, tx_upsert as db_tx_upsert
from .logging_util import get_logger, log_event
from .payments import ProviderError, get_fiat_provider, verify_stripe_webhook

logger = get_logger("hybridpay.api")

app = FastAPI(title="HybridPay Modal Sandbox Backend", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type", "X-Tenant-Id", "Idempotency-Key"],
)


@app.exception_handler(Exception)
async def unhandled_handler(_: Request, exc: Exception) -> JSONResponse:
    log_event(logger, "error.unhandled", error=str(exc)[:200])
    return JSONResponse(status_code=500, content={"detail": "internal error"})


# ---------- Schemas ----------

class AiAnalyzeIn(BaseModel):
    order: dict[str, str] = Field(default_factory=dict)
    text: str = Field(default="", max_length=4000)


class FiatSimulateIn(BaseModel):
    amountMinor: str = Field(pattern=r"^\d+$", max_length=12)
    instructionId: str = Field(min_length=1, max_length=80)
    currency: str = Field(default="EUR", pattern=r"^[A-Z]{3}$")


class FiatCreateIn(BaseModel):
    """Create a sandbox fiat payment. Provider-hosted collection only —
    the response clientSecret (Stripe TEST) is for the provider SDK; raw
    card numbers/CVV are never accepted here (no such fields exist)."""
    amountMinor: str = Field(pattern=r"^\d+$", max_length=12)
    currency: str = Field(default="EUR", pattern=r"^[A-Z]{3}$")
    instructionId: str = Field(min_length=1, max_length=80)


class FiatRefundIn(BaseModel):
    amountMinor: str | None = Field(default=None, pattern=r"^\d+$", max_length=12)


class EvmRequestIn(BaseModel):
    to: str = Field(min_length=42, max_length=42)
    valueWei: str = Field(pattern=r"^\d+$", max_length=32)
    chainId: int = Field(default=11155111)
    expiresInSec: int = Field(default=3600, ge=60, le=86400)


class EvmSubmitIn(BaseModel):
    txHash: str = Field(min_length=66, max_length=66)


class EvmReplaceIn(BaseModel):
    newTxHash: str = Field(min_length=66, max_length=66)


class PagCreateIn(BaseModel):
    terms: dict[str, Any]
    creator: str = Field(min_length=1, max_length=80)


class PagActorIn(BaseModel):
    actor: str = Field(min_length=1, max_length=80)
    role: str = Field(min_length=1, max_length=20)


class PagEvidenceIn(BaseModel):
    actor: str = Field(min_length=1, max_length=80)
    evidence: dict[str, Any] = Field(default_factory=dict)


class CryptoSimulateIn(BaseModel):
    amountMinor: str = Field(pattern=r"^\d+$", max_length=16)
    instructionId: str = Field(min_length=1, max_length=80)
    address: str = Field(min_length=5, max_length=120)


class ContractValidateIn(BaseModel):
    terms: dict[str, Any]


class AiTransactionIn(BaseModel):
    transaction: dict[str, Any] = Field(default_factory=dict)


class AiRoutingIn(BaseModel):
    context: dict[str, Any] = Field(default_factory=dict)


class AiContractIn(BaseModel):
    terms: dict[str, Any]


class AiCryptoIn(BaseModel):
    transaction: dict[str, Any] = Field(default_factory=dict)


class AiStateIn(BaseModel):
    state: str = Field(min_length=1, max_length=40)
    reasons: list[str] = Field(default_factory=list, max_length=10)
    conditionStatuses: dict[str, str] = Field(default_factory=dict)


class AiAssistantIn(BaseModel):
    message: str = Field(min_length=1, max_length=1000)
    context: dict[str, Any] = Field(default_factory=dict)


def _ai_or_429(fn, *args: Any) -> dict[str, Any]:
    """Run an advisory AI service; map rate limiting to HTTP 429."""
    try:
        return fn(*args)
    except meta_client.MetaClientError as exc:
        if exc.code == "RATE_LIMITED":
            raise HTTPException(status_code=429, detail="AI rate limit exceeded") from exc
        raise HTTPException(status_code=503, detail=f"AI_ERROR:{exc.code}") from exc


# ---------- Routes ----------

@app.get("/health")
async def health() -> dict[str, Any]:
  mode = config.live_mode_status()
  return {"ok": True, "liveMode": mode, "sandbox": mode != "ON-APPROVED", "ts": int(time.time())}


@app.post("/api/ai/analyze")
async def ai_analyze(body: AiAnalyzeIn, caller: str = Depends(require_auth)) -> dict[str, Any]:
    log_event(logger, "ai.analyze", caller=caller)
    draft = ai.draft_agreement_brief(body.order)
    return {"draft": draft, "authoritative": False,
            "notice": "AI output is advisory only; validator + human acceptance required."}


@app.post("/api/ai/explain-transaction")
async def ai_explain(body: AiTransactionIn, tenant: str = Depends(require_tenant),
                     caller: str = Depends(require_auth)) -> dict[str, Any]:
    log_event(logger, "ai.explain.request", caller=caller)
    return _ai_or_429(ai.explain_transaction, body.transaction, tenant)


@app.post("/api/ai/fraud-signals")
async def ai_fraud(body: AiTransactionIn, tenant: str = Depends(require_tenant),
                   caller: str = Depends(require_auth)) -> dict[str, Any]:
    log_event(logger, "ai.fraud.request", caller=caller)
    return _ai_or_429(ai.fraud_signals, body.transaction, tenant)


@app.post("/api/ai/routing-recommendation")
async def ai_routing(body: AiRoutingIn, tenant: str = Depends(require_tenant),
                     caller: str = Depends(require_auth)) -> dict[str, Any]:
    log_event(logger, "ai.routing.request", caller=caller)
    return _ai_or_429(ai.routing_recommendation, body.context, tenant)


@app.post("/api/ai/contract-analysis")
async def ai_contract(body: AiContractIn, tenant: str = Depends(require_tenant),
                      caller: str = Depends(require_auth)) -> dict[str, Any]:
    log_event(logger, "ai.contract.request", caller=caller)
    return _ai_or_429(ai.analyze_contract, body.terms, tenant)


@app.post("/api/ai/explain-crypto")
async def ai_explain_crypto(body: AiCryptoIn, tenant: str = Depends(require_tenant),
                            caller: str = Depends(require_auth)) -> dict[str, Any]:
    log_event(logger, "ai.explain-crypto.request", caller=caller)
    return _ai_or_429(ai.explain_crypto, body.transaction, tenant)


@app.post("/api/ai/explain-state")
async def ai_explain_state(body: AiStateIn, tenant: str = Depends(require_tenant),
                           caller: str = Depends(require_auth)) -> dict[str, Any]:
    log_event(logger, "ai.explain-state.request", caller=caller)
    return _ai_or_429(ai.explain_agreement_state, body.model_dump(), tenant)


@app.post("/api/ai/assistant")
async def ai_assistant(body: AiAssistantIn, tenant: str = Depends(require_tenant),
                       caller: str = Depends(require_auth)) -> dict[str, Any]:
    log_event(logger, "ai.assistant.request", caller=caller)
    return _ai_or_429(ai.assistant, body.message, body.context, tenant)


@app.get("/api/ai/usage")
async def ai_usage(tenant: str = Depends(require_tenant),
                   caller: str = Depends(require_auth)) -> dict[str, Any]:
    from .meta_client import usage_snapshot
    snap = usage_snapshot()
    log_event(logger, "ai.usage.read", caller=caller)
    return {"tenant": tenant, "calls": snap["calls"], "fallbacks": snap["fallbacks"],
            "promptTokens": snap["prompt_tokens"], "completionTokens": snap["completion_tokens"],
            "sandbox": True}


def _public(response: dict[str, Any]) -> dict[str, Any]:
    """Strip internal idempotency bookkeeping before returning to clients."""
    return {k: v for k, v in response.items() if k != "_payload"}


def _idem_key(tenant: str, route: str, key: str | None, body: dict[str, Any]) -> str:
    raw = f"{tenant}:{route}:{key or hashlib.sha256(str(body).encode()).hexdigest()}"
    return raw


@app.post("/api/payments/fiat/simulate", status_code=201)
async def fiat_simulate(
    body: FiatSimulateIn,
    tenant: str = Depends(require_tenant),
    caller: str = Depends(require_auth),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict[str, Any]:
    payload = body.model_dump()
    key = _idem_key(tenant, "fiat", idempotency_key, payload)
    hit = store.idem_lookup(key)
    if hit:
        if hit["payload"] != payload:
            raise HTTPException(status_code=409, detail="IDEMPOTENCY_CONFLICT")
        return _public(hit["response"])
    amount = int(body.amountMinor)
    result = providers.fiat_authorize(amount, body.instructionId)
    if not result.ok:
        status = 502 if result.code == "TIMEOUT_UNKNOWN" else 422
        raise HTTPException(status_code=status, detail=f"{result.code}: {result.message}")
    tx_id = f"tx-{uuid.uuid4().hex[:12]}"
    response = {"transactionId": tx_id, "state": result.state,
                "providerRef": result.provider_ref, "sandbox": True}
    store.tx_store(tx_id, {"tenant": tenant, **response})
    store.idem_store(key, {"payload": payload, "response": response})
    log_event(logger, "payment.fiat.simulated", tenant=tenant, caller=caller,
              transactionId=tx_id, state=result.state, amountMinor=body.amountMinor)
    return response


@app.post("/api/payments/crypto/simulate", status_code=201)
async def crypto_simulate(
    body: CryptoSimulateIn,
    tenant: str = Depends(require_tenant),
    caller: str = Depends(require_auth),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict[str, Any]:
    if not providers.crypto_validate_address(body.address):
        raise HTTPException(status_code=422, detail="wrong-network or bad regtest address")
    payload = body.model_dump()
    key = _idem_key(tenant, "crypto", idempotency_key, payload)
    hit = store.idem_lookup(key)
    if hit:
        if hit["payload"] != payload:
            raise HTTPException(status_code=409, detail="IDEMPOTENCY_CONFLICT")
        return _public(hit["response"])
    result = providers.crypto_invoice(int(body.amountMinor), body.instructionId)
    if not result.ok:
        raise HTTPException(status_code=503, detail=f"{result.code}: {result.message}")
    tx_id = f"tx-{uuid.uuid4().hex[:12]}"
    response = {"transactionId": tx_id, "state": result.state,
                "providerRef": result.provider_ref, "sandbox": True}
    store.tx_store(tx_id, {"tenant": tenant, **response})
    store.idem_store(key, {"payload": payload, "response": response})
    log_event(logger, "payment.crypto.simulated", tenant=tenant, caller=caller, transactionId=tx_id)
    return response


@app.post("/api/contracts/validate")
async def contracts_validate(body: ContractValidateIn, caller: str = Depends(require_auth)) -> dict[str, Any]:
    errors = contracts.validate_terms(body.terms)
    log_event(logger, "contract.validated", caller=caller, ok=not errors)
    return {"ok": not errors, "errors": errors,
            "versionHash": contracts.version_hash(body.terms) if not errors else None}


@app.get("/api/transactions/{transaction_id}")
async def tx_get(transaction_id: str, tenant: str = Depends(require_tenant),
                 caller: str = Depends(require_auth)) -> dict[str, Any]:
    record = store.tx_get(transaction_id)
    if not record or record.get("tenant") != tenant:
        raise HTTPException(status_code=404, detail="not found")
    log_event(logger, "tx.read", caller=caller, transactionId=transaction_id)
    return {k: v for k, v in record.items() if k != "tenant"}


# ---------- Fiat sandbox payments (modular provider, authoritative status) ----------

def _provider_label() -> str:
    return get_fiat_provider().name


@app.post("/api/payments/fiat", status_code=201)
async def fiat_create(
    body: FiatCreateIn,
    tenant: str = Depends(require_tenant),
    caller: str = Depends(require_auth),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict[str, Any]:
    """Create a sandbox payment (state created->pending). Idempotent per key+payload."""
    payload = body.model_dump()
    key = _idem_key(tenant, "fiat-create", idempotency_key, payload)
    hit = store.idem_lookup(key)
    if hit:
        if hit["payload"] != payload:
            raise HTTPException(status_code=409, detail="IDEMPOTENCY_CONFLICT")
        return _public(hit["response"])
    try:
        created = get_fiat_provider().create(int(body.amountMinor), body.currency, body.instructionId)
    except ProviderError as exc:
        raise HTTPException(status_code=422 if exc.code != "TIMEOUT_UNKNOWN" else 502,
                            detail=f"{exc.code}: {exc}") from exc
    tx_id = f"pay-{uuid.uuid4().hex[:12]}"
    response: dict[str, Any] = {"paymentId": tx_id, "state": created.state,
                                "provider": created.provider, "providerRef": created.provider_ref,
                                "amountMinor": body.amountMinor, "currency": body.currency,
                                "sandbox": True, "liveMode": config.live_mode_status()}
    if created.raw and created.raw.get("client_secret"):
        response["clientSecret"] = created.raw["client_secret"]  # provider SDK only, TEST mode
    db_tx_upsert({"id": tx_id, "tenant": tenant, "state": created.state,
                  "amountMinor": body.amountMinor, "currency": body.currency,
                  "provider": created.provider, "providerRef": created.provider_ref,
                  "idempotencyKey": key, "payload": {}})
    store.idem_store(key, {"payload": payload, "response": response})
    log_event(logger, "payment.fiat.created", tenant=tenant, caller=caller,
              transactionId=tx_id, state=created.state, provider=created.provider)
    return _public(response)


def _load_owned(payment_id: str, tenant: str) -> dict[str, Any]:
    rec = db_tx_get(payment_id, tenant)
    if not rec:
        raise HTTPException(status_code=404, detail="not found")
    return rec


@app.post("/api/payments/fiat/{payment_id}/confirm")
async def fiat_confirm(payment_id: str, tenant: str = Depends(require_tenant),
                       caller: str = Depends(require_auth)) -> dict[str, Any]:
    """Confirm via the PROVIDER (authoritative). Never trusts frontend state."""
    rec = _load_owned(payment_id, tenant)
    if rec["state"] in ("succeeded", "refunded", "canceled"):
        return {"paymentId": payment_id, "state": rec["state"], "providerRef": rec["providerRef"],
                "sandbox": True, "note": "terminal state, no re-confirm"}
    instruction = rec.get("payload", {}).get("instructionId", payment_id)
    try:
        result = get_fiat_provider().confirm(rec["providerRef"], instruction)
    except ProviderError as exc:
        if exc.code == "TIMEOUT_UNKNOWN":
            db_tx_upsert({**rec, "id": payment_id, "tenant": tenant,
                          "amountMinor": rec.get("amountMinor", "0"), "state": "unknown",
                          "providerRef": rec.get("providerRef", ""), "payload": rec.get("payload", {})})
            raise HTTPException(status_code=502, detail=f"TIMEOUT_UNKNOWN: query original before retry") from exc
        raise HTTPException(status_code=422, detail=f"{exc.code}: {exc}") from exc
    db_tx_upsert({**rec, "id": payment_id, "tenant": tenant,
                  "amountMinor": rec.get("amountMinor", "0"), "state": result.state,
                  "providerRef": result.provider_ref, "payload": rec.get("payload", {})})
    log_event(logger, "payment.fiat.confirmed", tenant=tenant, caller=caller,
              transactionId=payment_id, state=result.state)
    return {"paymentId": payment_id, "state": result.state, "providerRef": result.provider_ref, "sandbox": True}


@app.get("/api/payments/fiat/{payment_id}")
async def fiat_retrieve(payment_id: str, tenant: str = Depends(require_tenant),
                        caller: str = Depends(require_auth)) -> dict[str, Any]:
    """Authoritative retrieve: queries provider when TEST key present, else stored state."""
    rec = _load_owned(payment_id, tenant)
    if config.STRIPE_SECRET_KEY_TEST and rec.get("provider") == "stripe-test" and rec.get("providerRef"):
        try:
            live = get_fiat_provider().retrieve(rec["providerRef"])
            if live.state != rec["state"]:
                db_tx_upsert({**rec, "id": payment_id, "tenant": tenant,
                              "amountMinor": rec.get("amountMinor", "0"), "state": live.state,
                              "providerRef": live.provider_ref, "payload": rec.get("payload", {})})
                rec = {**rec, "state": live.state, "providerRef": live.provider_ref}
        except ProviderError as exc:
            rec = {**rec, "providerNote": f"{exc.code}: retrieve ambiguous, stored state returned"}
    log_event(logger, "payment.fiat.retrieved", tenant=tenant, caller=caller, transactionId=payment_id)
    return {"paymentId": payment_id, "state": rec["state"], "provider": rec.get("provider"),
            "providerRef": rec.get("providerRef"), "amountMinor": rec.get("amountMinor"),
            "currency": rec.get("currency"), "sandbox": True}


@app.get("/api/payments/fiat")
async def fiat_list(tenant: str = Depends(require_tenant),
                    caller: str = Depends(require_auth)) -> dict[str, Any]:
    items = db_tx_list(tenant)
    log_event(logger, "payment.fiat.listed", tenant=tenant, caller=caller, count=len(items))
    return {"payments": items, "sandbox": True}


@app.post("/api/payments/fiat/{payment_id}/cancel")
async def fiat_cancel(payment_id: str, tenant: str = Depends(require_tenant),
                      caller: str = Depends(require_admin)) -> dict[str, Any]:
    """Admin only: cancels a non-terminal payment (money movement)."""
    rec = _load_owned(payment_id, tenant)
    if rec["state"] not in ("created", "pending", "unknown"):
        raise HTTPException(status_code=409, detail=f"cannot cancel from state {rec['state']}")
    try:
        result = get_fiat_provider().cancel(rec["providerRef"])
    except ProviderError as exc:
        raise HTTPException(status_code=422, detail=f"{exc.code}: {exc}") from exc
    db_tx_upsert({**rec, "id": payment_id, "tenant": tenant,
                  "amountMinor": rec.get("amountMinor", "0"), "state": result.state,
                  "providerRef": result.provider_ref, "payload": rec.get("payload", {})})
    return {"paymentId": payment_id, "state": result.state, "sandbox": True}


@app.post("/api/payments/fiat/{payment_id}/refund")
async def fiat_refund(payment_id: str, body: FiatRefundIn, tenant: str = Depends(require_tenant),
                      caller: str = Depends(require_admin)) -> dict[str, Any]:
    """Admin only: refunds a succeeded payment (money movement)."""
    rec = _load_owned(payment_id, tenant)
    if rec["state"] != "succeeded":
        raise HTTPException(status_code=409, detail="only succeeded payments can be refunded")
    try:
        result = get_fiat_provider().refund(rec["providerRef"],
                                            int(body.amountMinor) if body.amountMinor else None)
    except ProviderError as exc:
        raise HTTPException(status_code=422, detail=f"{exc.code}: {exc}") from exc
    db_tx_upsert({**rec, "id": payment_id, "tenant": tenant,
                  "amountMinor": rec.get("amountMinor", "0"), "state": result.state,
                  "providerRef": result.provider_ref, "payload": rec.get("payload", {})})
    log_event(logger, "payment.fiat.refunded", tenant=tenant, caller=caller, transactionId=payment_id)
    return {"paymentId": payment_id, "state": result.state, "refundRef": result.provider_ref, "sandbox": True}


@app.post("/api/webhooks/stripe")
async def stripe_webhook(request: Request, caller: str = Depends(require_auth)) -> dict[str, Any]:
    """Verified Stripe webhook: signature-checked, idempotent, authoritative state source."""
    raw = await request.body()
    sig = request.headers.get("stripe-signature", "")
    secret = config.STRIPE_WEBHOOK_SECRET_TEST
    try:
        event = verify_stripe_webhook(raw, sig, secret)
    except ProviderError as exc:
        code = 410 if exc.code == "STALE_EVENT" else 401
        raise HTTPException(status_code=code, detail=f"{exc.code}: {exc}") from exc
    if not event["id"]:
        raise HTTPException(status_code=422, detail="bad event")
    dedupe_key = f"wh:stripe:{event['id']}"
    if store.idem_lookup(dedupe_key):
        return {"received": True, "deduped": True}
    store.idem_store(dedupe_key, {"payload": event, "response": {"received": True}})
    etype = event.get("type", "")
    new_state = {"payment_intent.succeeded": "succeeded", "payment_intent.payment_failed": "failed",
                 "payment_intent.canceled": "canceled"}.get(etype)
    updated = 0
    if new_state and event.get("payment_intent"):
        rows = _db.tx_by_provider_ref(event["payment_intent"])
        for r in rows:
            current = db_tx_get(r["id"], r["tenant"])
            if current and current["state"] not in ("refunded", "succeeded"):
                db_tx_upsert({**current, "id": r["id"], "tenant": r["tenant"],
                              "amountMinor": current.get("amountMinor", "0"),
                              "state": new_state, "providerRef": event["payment_intent"],
                              "payload": current.get("payload", {})})
                updated += 1
    log_event(logger, "webhook.stripe.verified", caller=caller, etype=etype, updated=updated)
    return {"received": True, "event": etype, "updated": updated}


# ---------- EVM Sepolia testnet (wallet signs, backend tracks + verifies) ----------

@app.post("/api/payments/evm/request", status_code=201)
async def evm_request(
    body: EvmRequestIn,
    tenant: str = Depends(require_tenant),
    caller: str = Depends(require_auth),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict[str, Any]:
    """Create a tracked Sepolia payment request. The wallet signs; the backend never sees keys."""
    try:
        evm_mod.assert_testnet(body.chainId)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not evm_mod.is_valid_address(body.to):
        raise HTTPException(status_code=422, detail="invalid EVM address (0x + 40 hex)")
    payload = body.model_dump()
    key = _idem_key(tenant, "evm-request", idempotency_key, payload)
    hit = store.idem_lookup(key)
    if hit:
        if hit["payload"] != payload:
            raise HTTPException(status_code=409, detail="IDEMPOTENCY_CONFLICT")
        return _public(hit["response"])
    pid = evm_mod.request_id(tenant, body.to, body.valueWei, idempotency_key or payload["to"])
    now = int(time.time())
    _db.evm_upsert({"id": pid, "tenant": tenant, "chain_id": body.chainId, "to": body.to,
                    "value_wei": body.valueWei, "state": "requested",
                    "expires_at": now + body.expiresInSec, "created_at": now})
    response = {"paymentId": pid, "chainId": body.chainId, "to": body.to,
                "valueWei": body.valueWei, "state": "requested",
                "explorerBase": "https://sepolia.etherscan.io/tx/",
                "sandbox": True, "note": "Sign with your wallet (Sepolia only). Backend never handles keys."}
    store.idem_store(key, {"payload": payload, "response": response})
    log_event(logger, "payment.evm.requested", tenant=tenant, caller=caller, paymentId=pid)
    return _public(response)


@app.post("/api/payments/evm/{payment_id}/submit")
async def evm_submit(payment_id: str, body: EvmSubmitIn, tenant: str = Depends(require_tenant),
                     caller: str = Depends(require_auth)) -> dict[str, Any]:
    """Register the wallet-submitted tx hash. Does NOT mark success — receipt decides."""
    rec = _db.evm_get(payment_id, tenant)
    if not rec:
        raise HTTPException(status_code=404, detail="not found")
    if not evm_mod.is_valid_txhash(body.txHash):
        raise HTTPException(status_code=422, detail="invalid tx hash")
    if rec["state"] in ("confirmed", "failed", "expired"):
        raise HTTPException(status_code=409, detail=f"terminal state {rec['state']}, no resubmit")
    if rec["tx_hash"] and rec["tx_hash"] != body.txHash:
        rec = {**rec, "state": "replaced", "replaced_by": body.txHash}
    rec = {**rec, "state": "pending", "tx_hash": body.txHash}
    _db.evm_upsert(rec)
    log_event(logger, "payment.evm.submitted", tenant=tenant, caller=caller, paymentId=payment_id)
    return {"paymentId": payment_id, "state": "pending", "txHash": body.txHash,
            "explorer": evm_mod.explorer_link(body.txHash), "sandbox": True,
            "note": "pending = submitted, NOT confirmed. Receipt verification decides."}


@app.get("/api/payments/evm/{payment_id}")
async def evm_status(payment_id: str, tenant: str = Depends(require_tenant),
                     caller: str = Depends(require_auth)) -> dict[str, Any]:
    """Verify receipt via RPC (when configured) and report chain state + business note."""
    rec = _db.evm_get(payment_id, tenant)
    if not rec:
        raise HTTPException(status_code=404, detail="not found")
    confirmations, receipt_note = rec.get("confirmations", 0), "stored state (RPC not configured)"
    if rec.get("tx_hash"):
        try:
            receipt = evm_mod.verify_receipt(rec["tx_hash"],
                                            config.EVM_CONFIRMATIONS_REQUIRED)
            state = evm_mod.evaluate_chain_state(
                receipt, config.EVM_CONFIRMATIONS_REQUIRED, rec.get("expires_at"))
            confirmations, receipt_note = receipt.confirmations, "verified via RPC"
            if state != rec["state"]:
                rec = {**rec, "state": state, "confirmations": receipt.confirmations}
                _db.evm_upsert(rec)
        except ConnectionError as exc:
            receipt_note = f"{exc} — returning stored state; safe to retry"
    settled = rec["state"] == "confirmed"
    return {"paymentId": payment_id, "chainId": rec["chain_id"], "state": rec["state"],
            "txHash": rec.get("tx_hash", ""), "confirmations": confirmations,
            "confirmationsRequired": config.EVM_CONFIRMATIONS_REQUIRED,
            "explorer": evm_mod.explorer_link(rec["tx_hash"]) if rec.get("tx_hash") else None,
            "businessSettled": False,
            "note": f"chain: {receipt_note}. confirmed != settled: settlement is a separate business step. {'Eligible for settlement review.' if settled else ''}",
            "sandbox": True}


@app.post("/api/payments/evm/{payment_id}/replace")
async def evm_replace(payment_id: str, body: EvmReplaceIn, tenant: str = Depends(require_tenant),
                      caller: str = Depends(require_auth)) -> dict[str, Any]:
    """Register a replacement tx (same nonce, higher fee). Old hash linked, not lost."""
    rec = _db.evm_get(payment_id, tenant)
    if not rec:
        raise HTTPException(status_code=404, detail="not found")
    if not evm_mod.is_valid_txhash(body.newTxHash):
        raise HTTPException(status_code=422, detail="invalid tx hash")
    if rec["state"] in ("confirmed", "failed", "expired"):
        raise HTTPException(status_code=409, detail=f"terminal state {rec['state']}")
    old = rec.get("tx_hash", "")
    rec = {**rec, "state": "pending", "tx_hash": body.newTxHash, "replaced_by": body.newTxHash}
    _db.evm_upsert(rec)
    log_event(logger, "payment.evm.replaced", tenant=tenant, caller=caller,
              paymentId=payment_id, oldTx=old)
    return {"paymentId": payment_id, "state": "pending", "txHash": body.newTxHash,
            "replaced": old, "explorer": evm_mod.explorer_link(body.newTxHash), "sandbox": True}


@app.get("/api/payments/evm")
async def evm_list(tenant: str = Depends(require_tenant),
                   caller: str = Depends(require_auth)) -> dict[str, Any]:
    items = [{**p, "explorer": evm_mod.explorer_link(p["tx_hash"]) if p.get("tx_hash") else None}
             for p in _db.evm_list(tenant)]
    return {"payments": items, "chainId": evm_mod.SEPOLIA_CHAIN_ID, "sandbox": True}


# ---------- programmable fiat agreements (deterministic, sandbox) ----------

def _load_pag(ag_id: str, tenant: str) -> dict[str, Any]:
    ag = _db.pag_get(ag_id, tenant)
    if not ag:
        raise HTTPException(status_code=404, detail="not found")
    return ag


@app.post("/api/contracts/programmable", status_code=201)
async def pag_create(body: PagCreateIn, tenant: str = Depends(require_tenant),
                     caller: str = Depends(require_auth),
                     idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")) -> dict[str, Any]:
    errors = programmable.validate_creation(body.terms)
    if errors:
        raise HTTPException(status_code=422, detail={"errors": errors})
    key = _idem_key(tenant, "pag-create", idempotency_key, body.model_dump())
    hit = store.idem_lookup(key)
    if hit:
        return _public(hit["response"])
    ag = programmable.new_agreement(tenant, body.creator, body.terms)
    _db.pag_put(ag)
    response = {"agreementId": ag["id"], "version": 1, "state": "draft",
                "disclosure": programmable.DISCLOSURE, "sandbox": True}
    store.idem_store(key, {"payload": body.model_dump(), "response": response})
    log_event(logger, "contract.pag.created", tenant=tenant, caller=caller, agreementId=ag["id"])
    return _public(response)


@app.get("/api/contracts/programmable/{agreement_id}")
async def pag_get(agreement_id: str, tenant: str = Depends(require_tenant),
                  caller: str = Depends(require_auth)) -> dict[str, Any]:
    ag = _load_pag(agreement_id, tenant)
    now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    if programmable.check_expiry(ag, now_iso) and ag["state"] not in ("completed", "canceled", "expired"):
        ok, _ = programmable.can_transition(ag["state"], "expired", "system")
        if ok:
            programmable.append_event(ag, "system", "evaluate", "expired")
            _db.pag_put(ag)
    statuses = programmable.evaluate_all(ag["terms"], ag.get("evidence", {}), now_iso)
    return {"agreementId": ag["id"], "version": ag.get("version", 1), "state": ag["state"],
            "terms": ag["terms"], "evidence": ag.get("evidence", {}),
            "conditionStatuses": statuses, "eligible": programmable.all_met(statuses),
            "chainValid": programmable.verify_chain(ag), "history": ag.get("history", []),
            "disclosure": programmable.DISCLOSURE, "sandbox": True}


@app.post("/api/contracts/programmable/{agreement_id}/activate")
async def pag_activate(agreement_id: str, body: PagActorIn, tenant: str = Depends(require_tenant),
                       caller: str = Depends(require_auth)) -> dict[str, Any]:
    ag = _load_pag(agreement_id, tenant)
    ok, why = programmable.can_transition(ag["state"], "active", body.role)
    if not ok:
        raise HTTPException(status_code=409 if "illegal" in why else 403, detail=why)
    programmable.append_event(ag, body.actor, "activate", "active")
    programmable.append_event(ag, "system", "evaluate", "conditions_pending")
    _db.pag_put(ag)
    return {"agreementId": ag["id"], "state": ag["state"], "sandbox": True}


@app.post("/api/contracts/programmable/{agreement_id}/approve")
async def pag_approve(agreement_id: str, body: PagActorIn, tenant: str = Depends(require_tenant),
                      caller: str = Depends(require_auth)) -> dict[str, Any]:
    ag = _load_pag(agreement_id, tenant)
    if ag["state"] not in ("active", "conditions_pending", "disputed"):
        raise HTTPException(status_code=409, detail=f"cannot approve in {ag['state']}")
    ev = ag.setdefault("evidence", {}).setdefault("approvals", [])
    if body.actor not in ev:
        ev.append(body.actor)
    _db.pag_put(ag)
    now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    statuses = programmable.evaluate_all(ag["terms"], ag["evidence"], now_iso)
    if programmable.all_met(statuses):
        ok, _ = programmable.can_transition(ag["state"], "eligible_for_execution", "system")
        if ok:
            programmable.append_event(ag, "system", "evaluate", "eligible_for_execution")
            _db.pag_put(ag)
    return {"agreementId": ag["id"], "state": ag["state"], "eligible": programmable.all_met(statuses),
            "sandbox": True}


@app.post("/api/contracts/programmable/{agreement_id}/evidence")
async def pag_evidence(agreement_id: str, body: PagEvidenceIn, tenant: str = Depends(require_tenant),
                       caller: str = Depends(require_auth)) -> dict[str, Any]:
    """Attach authenticated evidence (delivery/external). Source MUST be authenticated
    by the caller before submission — the engine treats the flag as authoritative."""
    ag = _load_pag(agreement_id, tenant)
    if ag["state"] not in ("active", "conditions_pending", "disputed"):
        raise HTTPException(status_code=409, detail=f"cannot submit evidence in {ag['state']}")
    incoming = body.evidence or {}
    for k, v in (incoming.get("deliveries", {}) or {}).items():
        if not isinstance(v, dict) or v.get("confirmedByAuthenticatedSource") is not True:
            raise HTTPException(status_code=422, detail=f"delivery {k} not from authenticated source")
    for k, v in (incoming.get("externalEvents", {}) or {}).items():
        if not isinstance(v, dict) or v.get("authenticated") is not True:
            raise HTTPException(status_code=422, detail=f"external event {k} not authenticated")
    ag_ev = ag.setdefault("evidence", {})
    for k, v in (incoming.get("deliveries", {}) or {}).items():
        ag_ev.setdefault("deliveries", {})[k] = v
    for k, v in (incoming.get("externalEvents", {}) or {}).items():
        ag_ev.setdefault("externalEvents", {})[k] = v
    _db.pag_put(ag)
    now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    statuses = programmable.evaluate_all(ag["terms"], ag["evidence"], now_iso)
    if programmable.all_met(statuses):
        ok, _ = programmable.can_transition(ag["state"], "eligible_for_execution", "system")
        if ok:
            programmable.append_event(ag, "system", "evaluate", "eligible_for_execution")
            _db.pag_put(ag)
    return {"agreementId": ag["id"], "state": ag["state"], "eligible": programmable.all_met(statuses),
            "sandbox": True}


@app.post("/api/contracts/programmable/{agreement_id}/execute")
async def pag_execute(agreement_id: str, body: PagActorIn, tenant: str = Depends(require_tenant),
                      caller: str = Depends(require_admin),
                      idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")) -> dict[str, Any]:
    """Execute an ELIGIBLE agreement via the fiat sandbox provider. Three gates:
    deterministic eligibility AND explicit human authorization (role executor) AND
    admin bearer token. Eligibility alone never triggers payment."""
    ag = _load_pag(agreement_id, tenant)
    if body.role != "executor":
        raise HTTPException(status_code=403, detail="execution requires human executor authorization")
    now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    if programmable.check_expiry(ag, now_iso):
        raise HTTPException(status_code=410, detail="agreement expired")
    statuses = programmable.evaluate_all(ag["terms"], ag.get("evidence", {}), now_iso)
    if not programmable.all_met(statuses):
        raise HTTPException(status_code=409, detail={"eligible": False, "conditionStatuses": statuses,
                                                     "note": "eligibility and execution are separate; conditions unmet"})
    if ag["state"] != "eligible_for_execution":
        raise HTTPException(status_code=409, detail=f"state {ag['state']} is not eligible_for_execution")
    key = _idem_key(tenant, "pag-execute", idempotency_key, {"agreement": agreement_id})
    hit = store.idem_lookup(key)
    if hit:
        return _public(hit["response"])
    programmable.assert_sandbox_execution()
    terms = ag["terms"]
    try:
        created = get_fiat_provider().create(int(terms["amountMinor"]), terms.get("currency", "EUR"),
                                             f"{agreement_id}-exec")
        result = get_fiat_provider().confirm(created.provider_ref, f"{agreement_id}-exec")
    except ProviderError as exc:
        raise HTTPException(status_code=502 if exc.code == "TIMEOUT_UNKNOWN" else 422,
                            detail=f"{exc.code}: {exc}") from exc
    programmable.append_event(ag, body.actor, "execute", "completed")
    _db.pag_put(ag)
    response = {"agreementId": ag["id"], "state": "completed",
                "provider": created.provider, "providerRef": result.provider_ref,
                "providerState": result.state, "sandbox": True,
                "note": "Provider response is authoritative; this receipt is not a settlement guarantee."}
    store.idem_store(key, {"payload": {"agreement": agreement_id}, "response": response})
    log_event(logger, "contract.pag.executed", tenant=tenant, caller=caller, agreementId=ag["id"])
    return _public(response)


@app.post("/api/contracts/programmable/{agreement_id}/cancel")
async def pag_cancel(agreement_id: str, body: PagActorIn, tenant: str = Depends(require_tenant),
                     caller: str = Depends(require_admin)) -> dict[str, Any]:
    """Admin only (irreversible terminal state)."""
    ag = _load_pag(agreement_id, tenant)
    ok, why = programmable.can_transition(ag["state"], "canceled", body.role)
    if not ok:
        raise HTTPException(status_code=409 if "illegal" in why else 403, detail=why)
    programmable.append_event(ag, body.actor, "cancel", "canceled")
    _db.pag_put(ag)
    return {"agreementId": ag["id"], "state": "canceled", "sandbox": True}


@app.post("/api/contracts/programmable/{agreement_id}/dispute")
async def pag_dispute(agreement_id: str, body: PagActorIn, tenant: str = Depends(require_tenant),
                      caller: str = Depends(require_admin)) -> dict[str, Any]:
    """Admin only (freezes execution). Raising party identity is recorded in history."""
    ag = _load_pag(agreement_id, tenant)
    ok, why = programmable.can_transition(ag["state"], "disputed", body.role)
    if not ok:
        raise HTTPException(status_code=409 if "illegal" in why else 403, detail=why)
    programmable.append_event(ag, body.actor, "dispute", "disputed")
    _db.pag_put(ag)
    return {"agreementId": ag["id"], "state": "disputed", "sandbox": True}


@app.get("/api/contracts/programmable")
async def pag_list(tenant: str = Depends(require_tenant),
                   caller: str = Depends(require_auth)) -> dict[str, Any]:
    return {"agreements": _db.pag_list(tenant), "sandbox": True,
            "disclosure": programmable.DISCLOSURE}


# ---------- identity + unified dashboard (operator-readable) ----------

@app.get("/api/me")
async def me(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    """Who am I: role label for UI badges. No token is ever echoed back."""
    return {"role": caller_role(authorization), "sandbox": True,
            "liveMode": config.live_mode_status()}


@app.get("/api/dashboard/summary")
async def dashboard_summary(tenant: str = Depends(require_tenant),
                            caller: str = Depends(require_auth)) -> dict[str, Any]:
    """Tenant-scoped counts by state across fiat, EVM, and agreements (single call)."""
    from collections import Counter
    fiat = db_tx_list(tenant, limit=1000)
    evm_items = _db.evm_list(tenant, limit=1000)
    pags = _db.pag_list(tenant, limit=1000)
    by_state = lambda items, key="state": dict(Counter(p.get(key, "?") for p in items))
    log_event(logger, "dashboard.summary", tenant=tenant, caller=caller)
    return {"tenant": tenant, "sandbox": True,
            "fiat": {"total": len(fiat), "byState": by_state(fiat)},
            "evm": {"total": len(evm_items), "byState": by_state(evm_items),
                    "chainId": evm_mod.SEPOLIA_CHAIN_ID},
            "agreements": {"total": len(pags), "byState": by_state(pags)}}


@app.get("/api/dashboard/recent")
async def dashboard_recent(tenant: str = Depends(require_tenant),
                           caller: str = Depends(require_auth),
                           kind: str = "all", state: str = "", q: str = "",
                           limit: int = 50) -> dict[str, Any]:
    """Combined, filterable history: kind in {all,fiat,evm,agreement}, optional
    state substring and id/providerRef substring filters. Newest first."""
    lim = max(1, min(limit, 200))
    items: list[dict[str, Any]] = []
    if kind in ("all", "fiat"):
        for p in db_tx_list(tenant, limit=lim):
            items.append({"kind": "fiat", "id": p["id"], "state": p["state"],
                          "detail": f'{p.get("amountMinor", "?")} {p.get("currency", "")} via {p.get("provider", "")}',
                          "ref": p.get("providerRef", "")})
    if kind in ("all", "evm"):
        for p in _db.evm_list(tenant, limit=lim):
            items.append({"kind": "evm", "id": p["id"], "state": p["state"],
                          "detail": f'{p.get("value_wei", "?")} wei to {p.get("to", "")}',
                          "ref": p.get("tx_hash", ""),
                          "explorer": evm_mod.explorer_link(p["tx_hash"]) if p.get("tx_hash") else None})
    if kind in ("all", "agreement"):
        for p in _db.pag_list(tenant, limit=lim):
            items.append({"kind": "agreement", "id": p["id"], "state": p["state"],
                          "detail": f"v{p.get('version', 1)} updated {p.get('updatedAt', '')}",
                          "ref": ""})
    if state:
        items = [i for i in items if state.lower() in i["state"].lower()]
    if q:
        ql = q.lower()
        items = [i for i in items if ql in i["id"].lower() or ql in i["ref"].lower()
                 or ql in i["detail"].lower()]
    log_event(logger, "dashboard.recent", tenant=tenant, caller=caller, count=len(items))
    return {"items": items[:lim], "sandbox": True}

"""FastAPI application for the Modal sandbox backend.

Endpoints (sandbox/testnet only):
- GET  /health
- POST /api/ai/analyze                  (draft only — never authorizes transfers)
- POST /api/ai/explain-transaction      (advisory explanation)
- POST /api/ai/fraud-signals            (advisory risk indicators, fail-closed)
- POST /api/ai/routing-recommendation   (advisory route suggestion)
- POST /api/ai/contract-analysis        (advisory agreement analysis)
- POST /api/payments/fiat/simulate
- POST /api/payments/crypto/simulate
- POST /api/contracts/validate
- GET  /api/transactions/{transaction_id}

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

from . import ai, config, contracts, meta_client, providers, store
from .auth import require_auth, require_tenant
from .logging_util import get_logger, log_event

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
        return hit["response"]
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
        return hit["response"]
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

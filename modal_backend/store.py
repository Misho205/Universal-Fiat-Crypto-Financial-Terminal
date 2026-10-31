"""Durable store facade: same function names as before, backed by db.py (SQLite file).

Records survive restarts in ./data/hybridpay.db (or HYBRIDPAY_DB_PATH).
Tests call reset() to clear rows. Tenant is embedded in the idempotency key
("tenant:route:...") so it can be recovered without changing callers.
"""
from __future__ import annotations

import json
from typing import Any

from . import db


def _tenant_from_key(key: str) -> str:
    return key.split(":", 1)[0] if ":" in key else ""


def idem_lookup(key: str) -> dict[str, Any] | None:
    hit = db.idem_get(key)
    if not hit:
        return None
    response = hit["response"] or {}
    payload = response.get("_payload", {})
    return {"payload": payload, "response": response}


def idem_store(key: str, record: dict[str, Any]) -> None:
    payload = record.get("payload", {})
    response = dict(record.get("response", {}))
    response.setdefault("_payload", payload)
    db.idem_put(key, _tenant_from_key(key), payload, response)


def tx_store(tx_id: str, record: dict[str, Any]) -> None:
    db.tx_upsert({"id": tx_id, "tenant": record.get("tenant", ""),
                  "state": record.get("state", "unknown"),
                  "amountMinor": str(record.get("amountMinor", "0")),
                  "currency": record.get("currency", "EUR"),
                  "provider": record.get("provider", "mock"),
                  "providerRef": record.get("providerRef", ""),
                  "idempotencyKey": record.get("idempotencyKey", ""),
                  "payload": {"transactionId": tx_id, "state": record.get("state"),
                              "providerRef": record.get("providerRef", ""),
                              "sandbox": record.get("sandbox", True)}})


def tx_get(tx_id: str) -> dict[str, Any] | None:
    conn = db._connect()
    row = conn.execute("SELECT * FROM transactions WHERE id=?", (tx_id,)).fetchone()
    if not row:
        return None
    payload = json.loads(row["payload_json"] or "{}")
    return {"tenant": row["tenant"], **payload}


def reset() -> None:
    db.reset_for_tests()

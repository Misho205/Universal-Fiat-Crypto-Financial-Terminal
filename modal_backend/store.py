"""Ephemeral in-memory store for the Modal sandbox backend.

WARNING: Modal container storage is NOT durable. This store is for local
development and hackathon demo only. Production MUST use an external durable
database (the existing PostgreSQL / NestJS apps/api remains the system of
record — Modal never becomes authoritative for money).
"""
from __future__ import annotations

from threading import Lock
from typing import Any

_lock = Lock()
_transactions: dict[str, dict[str, Any]] = {}
_idem: dict[str, dict[str, Any]] = {}


def idem_lookup(key: str) -> dict[str, Any] | None:
    with _lock:
        return _idem.get(key)


def idem_store(key: str, record: dict[str, Any]) -> None:
    with _lock:
        _idem[key] = record


def tx_store(tx_id: str, record: dict[str, Any]) -> None:
    with _lock:
        _transactions[tx_id] = record


def tx_get(tx_id: str) -> dict[str, Any] | None:
    with _lock:
        return _transactions.get(tx_id)


def reset() -> None:  # tests only
    with _lock:
        _transactions.clear()
        _idem.clear()

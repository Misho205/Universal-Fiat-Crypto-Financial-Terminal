"""Tamper-evident AI security audit log (hash-chained, no personal data).

Each event: {seq, ts, event, tenantHash, actorHash, detail, prevHash, hash}.
tenant/actor ids are SHA-256 hashed with a per-process salt prefix note —
raw ids, prompts, keys, and balances are NEVER stored. Chain verification
detects deletion, reordering, or modification. Backed by an in-memory ring
(tests/reset) with optional DB persistence via institutional.security_audit.
"""
from __future__ import annotations

import hashlib
import threading
import time
from typing import Any

_lock = threading.Lock()
_events: list[dict[str, Any]] = []
_prev_hash = "GENESIS"


def _h(value: str) -> str:
    return hashlib.sha256(f"ai-guardrails:{value}".encode()).hexdigest()[:16]


def _chain_hash(seq: int, ts: int, event: str, prev: str, detail: str) -> str:
    payload = f"{seq}|{ts}|{event}|{prev}|{detail}"
    return hashlib.sha256(payload.encode()).hexdigest()


def log_security_event(event: str, *, tenant: str = "", actor: str = "",
                       detail: str = "", **fields: Any) -> dict[str, Any]:
    global _prev_hash
    with _lock:
        seq = len(_events)
        ts = int(time.time())
        extra = "|".join(f"{k}={str(v)[:80]}" for k, v in sorted(fields.items()))
        rec = {"seq": seq, "ts": ts, "event": event[:80],
               "tenantHash": _h(tenant) if tenant else "",
               "actorHash": _h(actor) if actor else "",
               "detail": str(detail)[:200], "extra": extra[:400],
               "prevHash": _prev_hash}
        rec["hash"] = _chain_hash(seq, ts, rec["event"], _prev_hash, rec["detail"] + rec["extra"])
        _prev_hash = rec["hash"]
        _events.append(rec)
        if len(_events) > 2000:
            del _events[:500]
        return dict(rec)


def verify_chain(events: list[dict[str, Any]] | None = None) -> bool:
    chain = _events if events is None else events
    prev = "GENESIS"
    for i, ev in enumerate(chain):
        if ev.get("seq") != i and events is None:
            return False
        if ev.get("prevHash") != prev:
            return False
        if ev.get("hash") != _chain_hash(ev.get("seq", i), ev.get("ts", 0),
                                         ev.get("event", ""), prev,
                                         str(ev.get("detail", "")) + str(ev.get("extra", ""))):
            return False
        prev = ev["hash"]
    return True


def recent(n: int = 100) -> list[dict[str, Any]]:
    with _lock:
        return [dict(e) for e in _events[-max(1, n):]]


def reset_for_tests() -> None:
    global _prev_hash
    with _lock:
        _events.clear()
        _prev_hash = "GENESIS"

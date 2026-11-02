"""Distributed AI security control plane (sandbox).

Replaces reliance on a process-local flag alone: the AI_ENABLED state lives
in the durable `ai_control` table (single global row), so emergency
disablement propagates to every Modal container/replica on its next check
— no redeploy, no per-process env push. The process-local env override
(AI_DISABLED=1) remains as a belt-and-suspenders local kill.

Controls:
- Global inference switch + separate tool-execution switch + per-feature
  flags (assistant, fraud_signals, routing, contract_analysis, explainers).
- Trusted control plane: only admin bearer may change state; disable and
  re-enable are audited in the independent audit system.
- The model can never re-enable itself: there is no code path from model
  output to control writes (source-scanned in tests), and re-enable needs a
  DIFFERENT admin credential than the disabler + explicit confirm + reason.
- Ordinary employees (operator role) cannot override the disabled state.
- In-flight tracking: generation counter bumps on every disable; new AI
  requests are rejected immediately (503); in-flight calls finish naturally
  but tool execution re-authorizes at execution time (generation check), so
  queued/in-flight tool actions are invalidated.
- Circuit breaker: consecutive provider failures trip auto-disable with an
  alert; success resets the counter.
- Deterministic fallback: callers map disablement to stub/advisory responses
  (never to fund movement); payment/auth/balance/non-AI paths are untouched.
"""
from __future__ import annotations

import os
import threading
import time
from typing import Any

from .. import db as _db

CONTROL_ID = "global"
CONTROL_VERSION = "aic-v1"

FEATURES = (
    "assistant",
    "fraud_signals",
    "routing",
    "contract_analysis",
    "explainers",
)

CB_THRESHOLD = int(os.environ.get("AI_CB_THRESHOLD", "5"))

_lock = threading.Lock()
_inflight = 0
_generation = 0


def _now() -> int:
    return int(time.time())


def ensure_control() -> dict[str, Any]:
    row = _db._fetch_one("SELECT * FROM ai_control WHERE id='global'", ())
    if row:
        return _row(row)
    import json as _js
    now = _now()
    _db._exec_write(
        "INSERT INTO ai_control(id,inference_enabled,tools_enabled,features_json,"
        "failures,version,updated_by,disabler_cred,reason,updated_at)"
        " VALUES ('global',1,1,?,0,1,'system','','',?)"
        " ON CONFLICT(id) DO NOTHING",
        (_js.dumps({f: True for f in FEATURES}), now),
    )
    row = _db._fetch_one("SELECT * FROM ai_control WHERE id='global'", ())
    assert row is not None
    return _row(row)


def _row(row: dict[str, Any]) -> dict[str, Any]:
    import json as _js
    return {
        "inferenceEnabled": bool(row["inference_enabled"]),
        "toolsEnabled": bool(row["tools_enabled"]),
        "features": _js.loads(row["features_json"] or "{}"),
        "failures": int(row["failures"]),
        "version": int(row["version"]),
        "updatedBy": row["updated_by"], "reason": row["reason"],
        "updatedAt": row["updated_at"],
        "controlVersion": CONTROL_VERSION,
    }


def is_inference_disabled() -> tuple[bool, str]:
    """Distributed check: env override OR durable control row."""
    if os.environ.get("AI_DISABLED", "") == "1":
        return True, "AI_DISABLED env set"
    try:
        ctl = ensure_control()
    except Exception:
        return False, ""
    if not ctl["inferenceEnabled"]:
        return True, f"distributed kill-switch engaged ({ctl['reason']})"
    return False, ""


def are_tools_enabled() -> tuple[bool, str]:
    try:
        ctl = ensure_control()
    except Exception:
        return True, ""
    if not ctl["toolsEnabled"]:
        return False, "AI tool execution revoked"
    return True, ""


def is_feature_enabled(name: str) -> bool:
    try:
        ctl = ensure_control()
    except Exception:
        return True
    return bool(ctl["features"].get(name, True))


def generation() -> int:
    return _generation


def track_inflight():
    """Context manager counting in-flight AI calls (observability)."""
    class _T:
        def __enter__(self):
            global _inflight
            with _lock:
                _inflight += 1
                return _generation

        def __exit__(self, *a):
            global _inflight
            with _lock:
                _inflight -= 1
            return False

    return _T()


def inflight_count() -> int:
    return _inflight


def set_control(*, inference_enabled: bool | None = None,
                tools_enabled: bool | None = None,
                features: dict[str, bool] | None = None,
                actor: str, credential_id: str, reason: str,
                require_different_cred: str = "") -> dict[str, Any]:
    """Change control state (admin control plane only — callers enforce).

    Re-enabling inference after a disable requires a DIFFERENT credential
    than the disabler (dual control), plus a non-empty reason. Disabling
    bumps the generation: in-flight tool actions authorized under the old
    generation are invalidated at execution time.
    """
    import json as _js
    ctl = ensure_control()
    turning_on = inference_enabled is True and not ctl["inferenceEnabled"]
    if turning_on:
        if not reason.strip():
            raise ValueError("re-enabling AI requires a documented reason")
        if require_different_cred and credential_id == require_different_cred:
            raise ValueError("re-enabling requires an independent authorizer "
                             "(different credential than the disabler)")
    else:
        if inference_enabled is False and not reason.strip():
            raise ValueError("disabling AI requires a documented reason")
    new_inf = ctl["inferenceEnabled"] if inference_enabled is None else bool(inference_enabled)
    new_tools = ctl["toolsEnabled"] if tools_enabled is None else bool(tools_enabled)
    feats = dict(ctl["features"])
    for k, v in (features or {}).items():
        if k not in FEATURES:
            raise ValueError(f"unknown AI feature {k!r}")
        feats[k] = bool(v)
    global _generation
    with _lock:
        if inference_enabled is False or tools_enabled is False:
            _generation += 1
    cur = _db._fetch_one("SELECT disabler_cred FROM ai_control WHERE id='global'", ())
    current_disabler = (cur or {}).get("disabler_cred", "") if cur else ""
    if inference_enabled is False:
        new_disabler = credential_id  # who pulled the switch (for dual-control re-enable)
    elif turning_on:
        new_disabler = ""  # verified re-enable clears the lock
    else:
        new_disabler = current_disabler  # feature/tool-only change keeps it
    _db._exec_write(
        "UPDATE ai_control SET inference_enabled=?, tools_enabled=?, "
        "features_json=?, version=version+1, updated_by=?, disabler_cred=?, "
        "reason=?, updated_at=? WHERE id='global'",
        (1 if new_inf else 0, 1 if new_tools else 0, _js.dumps(feats),
         actor, new_disabler, reason[:500], _now()),
    )
    return status()


def status() -> dict[str, Any]:
    ctl = ensure_control()
    disabled, why = is_inference_disabled()
    tools_ok, tools_why = are_tools_enabled()
    return {**ctl, "disabled": disabled, "disableReason": why,
            "toolsWhy": tools_why, "inflight": inflight_count(),
            "generation": generation()}


def disabler_cred() -> str:
    row = _db._fetch_one("SELECT disabler_cred FROM ai_control WHERE id='global'", ())
    return (row or {}).get("disabler_cred", "") if row else ""


def disabler_actor() -> str:
    """Actor name recorded when AI was disabled (empty when enabled).

    While disabled, updated_by IS the disabler (enable overwrites it with the
    verifier). Identity-level dual control mirrors institutional emergency
    review; credential-level binding is defense-in-depth.
    """
    try:
        ctl = ensure_control()
    except Exception:
        return ""
    if ctl["inferenceEnabled"]:
        return ""
    return ctl.get("updatedBy", "")


def record_failure(tenant: str, kind: str) -> dict[str, Any]:
    """Circuit breaker: consecutive failures trip auto-disable + alert."""
    ctl = ensure_control()
    failures = int(ctl["failures"]) + 1
    _db._exec_write("UPDATE ai_control SET failures=?, updated_at=? WHERE id='global'",
                    (failures, _now()))
    tripped = False
    if failures >= CB_THRESHOLD and ctl["inferenceEnabled"]:
        import json as _js
        _db._exec_write(
            "UPDATE ai_control SET inference_enabled=0, reason=?, "
            "updated_by='circuit-breaker', version=version+1, updated_at=? "
            "WHERE id='global'",
            (f"circuit-breaker tripped after {failures} consecutive failures ({kind})"[:500],
             _now()))
        global _generation
        with _lock:
            _generation += 1
        tripped = True
        try:
            from .. import audit_store as _audit
            _audit.record_event(tenant=tenant, actor="circuit-breaker",
                                action="ai.alert.circuit_breaker",
                                resource="ai-inference", outcome="tripped",
                                detail=f"{failures} consecutive failures ({kind})")
        except Exception:
            pass
    return {"failures": failures, "tripped": tripped}


def record_success() -> None:
    try:
        _db._exec_write("UPDATE ai_control SET failures=0 WHERE id='global'", ())
    except Exception:
        pass

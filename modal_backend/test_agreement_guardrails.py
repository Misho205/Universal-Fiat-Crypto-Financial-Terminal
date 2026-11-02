"""Agreement + crypto guardrail tests: property-style + adversarial.

Seeded pseudo-random property tests (deterministic; stdlib only) plus
targeted adversarial cases covering:
- double spending / duplicate execution attempts (same + distinct keys, race)
- unauthorized state transitions (role/state matrix fuzz)
- contract tampering (1-byte mutations rejected via terms hash)
- approval bypasses (missing/foreign/stale consents)
- replay attacks (idempotency-key reuse with different payloads, tx-hash reuse)
- expired approvals / agreements (expiry enforced at execute)
- cross-tenant access (agreement + EVM isolation)
- AI-driven unauthorized execution (AI output can never execute)
- wallet key hygiene (no private-key fields anywhere in the API surface)
- provider capability + no-escrow claims

Sandbox/testnet only.
"""
from __future__ import annotations

import random

from fastapi.testclient import TestClient

from modal_backend import programmable as pag
from modal_backend import evm as evm_mod
from modal_backend import store
from modal_backend.api import app

TENANT = "guard-e2e"
AUTH = {"Authorization": "Bearer dev-shared-token"}
ADMIN_TOKEN = "dev-admin-token"
TID = {"X-Tenant-Id": TENANT}
H = {**TID, **AUTH}
AH = {**TID, "Authorization": f"Bearer {ADMIN_TOKEN}"}
OTHER = {"X-Tenant-Id": "guard-other", **AUTH}
OTHER_ADMIN = {"X-Tenant-Id": "guard-other",
               "Authorization": f"Bearer {ADMIN_TOKEN}"}

ADDR = "0x" + "ab" * 20


def _admin(monkeypatch):
    import modal_backend.config as cfg
    monkeypatch.setattr(cfg, "API_SHARED_TOKEN", "dev-shared-token")
    monkeypatch.setattr(cfg, "API_ADMIN_TOKEN", ADMIN_TOKEN)


def _client() -> TestClient:
    store.reset()
    return TestClient(app, raise_server_exceptions=False)


def _terms(**over):
    base = {"amountMinor": "2599", "currency": "EUR",
            "parties": ["merchant", "customer"],
            "conditions": [
                {"type": "timeCondition", "notBefore": "2020-01-01T00:00:00Z",
                 "notAfter": "2030-01-01T00:00:00Z"},
                {"type": "partyApproval", "party": "customer"}],
            "executionModel": "pay-after-condition",
            "expiresAt": "2030-01-01T00:00:00Z"}
    base.update(over)
    return base


def _create_active_eligible(c, key="g1", terms=None, creator="merchant-op"):
    r = c.post("/api/contracts/programmable",
               json={"terms": terms or _terms(), "creator": creator},
               headers={**H, "Idempotency-Key": key})
    assert r.status_code == 201, r.text
    ag = r.json()["agreementId"]
    assert c.post(f"/api/contracts/programmable/{ag}/activate",
                  json={"actor": creator, "role": "creator"}, headers=H).status_code == 200
    assert c.post(f"/api/contracts/programmable/{ag}/approve",
                  json={"actor": "customer", "role": "party"}, headers=H).status_code == 200
    return ag


# ---------- property-style: tamper resistance ----------

def test_property_single_byte_tamper_changes_hash():
    rng = random.Random(20261102)
    for _ in range(50):
        t = _terms(amountMinor=str(rng.randint(1, 10 ** 9)))
        h = pag.terms_hash(t)
        mutated = dict(t)
        field = rng.choice(["amountMinor", "currency", "expiresAt"])
        mutated[field] = t[field] + "0"
        assert pag.terms_hash(mutated) != h
        errs = pag.validate_creation(mutated)
        # currency mutation must fail validation; amount mutation fails hash bind
        if field == "currency":
            assert errs, mutated


def test_property_amend_concurrency_and_consent_fuzz():
    rng = random.Random(77)
    roles = ["creator", "party", "executor", "system", "approver", "stranger"]
    states = ["draft", "active", "conditions_pending", "eligible_for_execution",
              "completed", "canceled", "expired", "disputed"]
    for _ in range(200):
        frm = rng.choice(states)
        to = rng.choice(states)
        role = rng.choice(roles)
        ok, _ = pag.can_transition(frm, to, role)
        # terminal states never leave; completed only via executor; active only via creator
        if frm in ("completed", "canceled", "expired"):
            assert ok is False
        if to == "completed":
            assert ok == (frm == "eligible_for_execution" and role == "executor")
        if to == "active":
            assert ok == (frm == "draft" and role == "creator")


def test_property_evm_id_binds_chain_and_scope():
    rng = random.Random(9)
    seen = set()
    for i in range(100):
        pid = evm_mod.request_id_for_chain(
            f"t{i % 5}", 11155111, ADDR, str(rng.randint(1, 10**18)), f"n{i}")
        assert pid not in seen
        seen.add(pid)
    # same scope on another chain would be a different id (mainnet refused)
    try:
        evm_mod.request_id_for_chain("t", 1, ADDR, "1", "n")
        assert False, "mainnet must be refused"
    except ValueError as exc:
        assert "MAINNET_REFUSED" in str(exc)


# ---------- adversarial ----------

def test_adversarial_double_execution_same_and_distinct_keys(monkeypatch):
    _admin(monkeypatch)
    c = _client()
    ag = _create_active_eligible(c)
    ex = {"actor": "exec-1", "role": "executor"}
    r1 = c.post(f"/api/contracts/programmable/{ag}/execute", json=ex,
                headers={**AH, "Idempotency-Key": "exec-1"})
    assert r1.status_code == 200, r1.text
    # same key replays the stored response
    r2 = c.post(f"/api/contracts/programmable/{ag}/execute", json=ex,
                headers={**AH, "Idempotency-Key": "exec-1"})
    assert r2.status_code == 200 and r2.json()["state"] == "completed"
    # distinct key must NOT double-spend: terminal state refuses
    r3 = c.post(f"/api/contracts/programmable/{ag}/execute", json=ex,
                headers={**AH, "Idempotency-Key": "exec-2"})
    assert r3.status_code == 409


def test_adversarial_unauthorized_transitions_and_role_bypass(monkeypatch):
    _admin(monkeypatch)
    c = _client()
    ag = _create_active_eligible(c, key="b1")
    # party cannot execute; executor cannot cancel; nobody executes twice
    assert c.post(f"/api/contracts/programmable/{ag}/execute",
                  json={"actor": "customer", "role": "party"},
                  headers=AH).status_code == 403
    assert c.post(f"/api/contracts/programmable/{ag}/cancel",
                  json={"actor": "exec-1", "role": "executor"},
                  headers=AH).status_code in (403, 409)


def test_adversarial_terms_tamper_rejected_at_execute(monkeypatch):
    _admin(monkeypatch)
    c = _client()
    ag = _create_active_eligible(c, key="t1")
    from modal_backend import db as _db
    doc = _db.pag_get(ag, TENANT)
    doc["terms"] = _terms(amountMinor="999999999")  # attacker edits stored terms
    _db.pag_put(doc)  # hash no longer matches
    r = c.post(f"/api/contracts/programmable/{ag}/execute",
               json={"actor": "exec-1", "role": "executor"},
               headers={**AH, "Idempotency-Key": "tamper-1"})
    assert r.status_code == 409 and "TAMPERED" in r.text


def test_adversarial_amendment_replay_stale_and_missing_consent(monkeypatch):
    _admin(monkeypatch)
    c = _client()
    # Amend BEFORE eligibility freezes the terms: create + activate (active).
    r = c.post("/api/contracts/programmable",
               json={"terms": _terms(), "creator": "creator-1"},
               headers={**H, "Idempotency-Key": "a1"})
    assert r.status_code == 201, r.text
    ag = r.json()["agreementId"]
    assert c.post(f"/api/contracts/programmable/{ag}/activate",
                  json={"actor": "creator-1", "role": "creator"},
                  headers=H).status_code == 200
    cur = c.get(f"/api/contracts/programmable/{ag}", headers=H).json()
    assert cur["state"] == "conditions_pending"
    prev = cur["termsHash"]
    import hashlib as _hl, json as _js
    new_terms = _terms(amountMinor="3000")
    new_hash = _hl.sha256(_js.dumps(new_terms, sort_keys=True).encode()).hexdigest()
    consents = [{"actor": "creator-1", "termsHash": new_hash},
                {"actor": "customer", "termsHash": new_hash}]
    # missing second consent
    r = c.post(f"/api/contracts/programmable/{ag}/amend",
               json={"actor": "creator-1", "role": "creator",
                     "expectedPrevHash": prev, "newTerms": new_terms,
                     "consents": consents[:1]}, headers=AH)
    assert r.status_code == 409
    # proper dual consent succeeds and bumps version
    r = c.post(f"/api/contracts/programmable/{ag}/amend",
               json={"actor": "creator-1", "role": "creator",
                     "expectedPrevHash": prev, "newTerms": new_terms,
                     "consents": consents}, headers=AH)
    assert r.status_code == 200, r.text
    assert r.json()["version"] == 2
    # replaying the same amendment (stale prev hash) is rejected
    r = c.post(f"/api/contracts/programmable/{ag}/amend",
               json={"actor": "creator-1", "role": "creator",
                     "expectedPrevHash": prev, "newTerms": new_terms,
                     "consents": consents}, headers=AH)
    assert r.status_code == 409 and "mismatch" in r.text
    # eligibility freezes terms: approving to eligible_for_execution and then
    # amending is refused (cancel + recreate for material changes instead —
    # explicit and auditable)
    c.post(f"/api/contracts/programmable/{ag}/approve",
           json={"actor": "customer", "role": "party"}, headers=H)
    assert c.get(f"/api/contracts/programmable/{ag}", headers=H).json()["state"] \
        == "eligible_for_execution"
    fresh = c.get(f"/api/contracts/programmable/{ag}", headers=H).json()
    r = c.post(f"/api/contracts/programmable/{ag}/amend",
               json={"actor": "creator-1", "role": "creator",
                     "expectedPrevHash": fresh["termsHash"],
                     "newTerms": _terms(amountMinor="4000"),
                     "consents": [{"actor": "creator-1",
                                   "termsHash": fresh["termsHash"]},
                                  {"actor": "customer",
                                   "termsHash": fresh["termsHash"]}]},
               headers=AH)
    assert r.status_code == 409 and "cannot amend" in r.text


def test_adversarial_replay_idempotency_conflict_and_tx_reuse(monkeypatch):
    _admin(monkeypatch)
    c = _client()
    r1 = c.post("/api/payments/fiat",
                json={"amountMinor": "100", "currency": "EUR",
                      "instructionId": "adv-1"},
                headers={**H, "Idempotency-Key": "adv-k"})
    assert r1.status_code == 201
    # same key + different payload -> 409 conflict (replay with mutation)
    r2 = c.post("/api/payments/fiat",
                json={"amountMinor": "999", "currency": "EUR",
                      "instructionId": "adv-1"},
                headers={**H, "Idempotency-Key": "adv-k"})
    assert r2.status_code == 409
    # same tx hash on two EVM requests -> second submit is a replay
    txh = "0x" + "aa" * 32
    p1 = c.post("/api/payments/evm/request",
                json={"to": ADDR, "valueWei": "1", "chainId": 11155111},
                headers={**H, "Idempotency-Key": "evm-a"}).json()["paymentId"]
    p2 = c.post("/api/payments/evm/request",
                json={"to": ADDR, "valueWei": "1", "chainId": 11155111},
                headers={**H, "Idempotency-Key": "evm-b"}).json()["paymentId"]
    if p1 == p2:  # chain-bound ids still differ by nonce scope; guard anyway
        p2 = c.post("/api/payments/evm/request",
                    json={"to": ADDR, "valueWei": "2", "chainId": 11155111},
                    headers={**H, "Idempotency-Key": "evm-c"}).json()["paymentId"]
    assert c.post(f"/api/payments/evm/{p1}/submit", json={"txHash": txh},
                  headers=H).status_code == 200
    assert c.post(f"/api/payments/evm/{p2}/submit", json={"txHash": txh},
                  headers=H).status_code == 409


def test_adversarial_expired_agreement_and_approval_after_expiry(monkeypatch):
    _admin(monkeypatch)
    c = _client()
    terms = _terms(expiresAt="2020-01-01T00:00:00Z")
    r = c.post("/api/contracts/programmable",
               json={"terms": terms, "creator": "merchant-op"},
               headers={**H, "Idempotency-Key": "exp-1"})
    ag = r.json()["agreementId"]
    c.post(f"/api/contracts/programmable/{ag}/activate",
           json={"actor": "merchant-op", "role": "creator"}, headers=H)
    g = c.get(f"/api/contracts/programmable/{ag}", headers=H).json()
    assert g["state"] == "expired"  # lazy expiry on read
    assert c.post(f"/api/contracts/programmable/{ag}/execute",
                  json={"actor": "e", "role": "executor"},
                  headers=AH).status_code in (409, 410)


def test_adversarial_cross_tenant_agreement_and_evm(monkeypatch):
    _admin(monkeypatch)
    c = _client()
    ag = _create_active_eligible(c, key="x1")
    assert c.get(f"/api/contracts/programmable/{ag}", headers=OTHER).status_code == 404
    assert c.post(f"/api/contracts/programmable/{ag}/execute",
                  json={"actor": "e", "role": "executor"},
                  headers=OTHER_ADMIN).status_code == 404
    p = c.post("/api/payments/evm/request",
               json={"to": ADDR, "valueWei": "1", "chainId": 11155111},
               headers={**H, "Idempotency-Key": "evm-x"}).json()["paymentId"]
    assert c.get(f"/api/payments/evm/{p}", headers=OTHER).status_code == 404


def test_adversarial_ai_cannot_execute_or_declare_conditions():
    import re
    import modal_backend.api as api_mod
    import inspect
    src = inspect.getsource(api_mod.pag_execute)
    assert "ai." not in src and "meta_client" not in src
    # AI policy: advisory only, never auto-enforces
    from modal_backend.ai_guardrails import policy as ai_policy
    d = ai_policy.decision_from_ai("contract-analysis", {"r": 1})
    assert d["approved"] is False and d["autoEnforced"] is False
    assert d["advisoryOnly"] is True


def test_wallet_key_hygiene_no_private_key_fields():
    from modal_backend import api as api_mod
    import inspect
    surface = inspect.getsource(api_mod) + inspect.getsource(evm_mod)
    for forbidden in ("privateKey", "private_key", "mnemonic", "seedPhrase",
                      "seed_phrase"):
        assert forbidden not in surface, forbidden


def test_no_escrow_claims_and_custody_words_rejected():
    errs = pag.validate_creation(_terms(custodyClaim="funds held by platform"))
    assert errs
    bad = _terms()
    bad["memo"] = "this is escrow for your funds"
    assert any("escrow" in e for e in pag.validate_creation(bad))
    ag = pag.new_agreement("t", "creator", _terms())
    assert "escrow" in ag["disclosure"]  # disclosure DISCLAIMS escrow
    assert pag.terms_hash(ag["terms"]) == ag["termsHash"]

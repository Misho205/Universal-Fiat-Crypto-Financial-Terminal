# Threat Model — Universal Hybrid Payment Terminal (sandbox backend)

Date: 2026-11-02. System: Modal FastAPI sandbox backend + Next.js terminal.
Trust boundary: server-side backend is authoritative; frontend, wallet, and
all client input are untrusted. No real money, no mainnet (fail-closed).

## 1. Assets

A1 sandbox payment records / agreement state; A2 approval authority
(maker/checker credentials); A3 audit evidence; A4 customer restriction/appeal
records; A5 AI advisory outputs; A6 bearer tokens / secrets (server-side only).

## 2. Actors

- Customer (own account only), Operator (create/confirm/track), Approver/
  Compliance/Auditor (review), Admin (sensitive ops), Owner (break-glass via
  intent), Service accounts (none provisioned in sandbox).
- Adversaries: malicious customer, rogue employee, compromised admin token,
  compromised AI service/model output, network attacker (TLS assumed),
  malicious/buggy client.

## 3. Attack surfaces & mitigations

| Surface | Threats | Mitigations (implemented) |
|---|---|---|
| Auth (bearer) | Token theft, role forgery, tenant spoofing | HMAC-compared tokens; server-side tenant binding; PDP cross-tenant deny; tenant-scoped queries |
| Intents/approvals | Self-approval, alt-accounts, replay, expiry reuse, param swap | Step-up + no-self-approval (identity + credId on bindings); quorum; canonical digests; single-use atomic consume; expiry+amount rechecked (STRICT) |
| Execution | Double-spend, TOCTOU, tampered terms | Idempotency keys; consume-before-provider; revalidate digest+state immediately before mutation; terms-hash check; post-provider race guard |
| Agreements | Condition bypass, unilateral amend, replayed amend | Deterministic evaluator; role×state matrix; dual-consent amend + prev-hash; eligibility freezes terms |
| Crypto (Sepolia) | Mainnet confusion, tx replay, fake success | Chain-bound IDs; MAINNET_REFUSED; cross-payment tx binding; receipt-gated states; backend never signs/holds keys |
| AI | Unauthorized action, injection, score-as-verdict | Advisory-only envelopes; allowlisted read-only tools; injection screening; kill-switch (payments unaffected); scores never authorize (engine + tests) |
| Rights/restrictions | Arbitrary freeze, gag leaks, reviewer capture | Grounds+reason+evidence gates; independent reviewer; disclosure matrix; appeal+correction; abuse monitoring |
| Audit | Erasure, forgery, silent loss, admin rewrite | No mutation API; hash chains (legacy + structured); must_audit fail-closed on sensitive paths; export+outbox; read-only auditor endpoints |

## 4. Trust assumptions (explicit)

T1 Server clock is approximately correct (no trusted timestamping in sandbox).
T2 Bearer tokens reach the backend uncompromised (TLS; memory-only browser).
T3 DB writes imply host/Volume trust — hash chains detect, WORM prevents
   (WORM is NOT deployed in sandbox; exports are the independent copy).
T4 HMAC audit key (when set) stays secret; without it, chain integrity rests
   on independent exports.
T5 AI model output is untrusted input (validated, never authoritative).

## 5. Out of scope / not mitigated here

Cloud account compromise, Modal platform compromise, endpoint compromise,
insider with DB+export access colluding, legal-process abuse, economic/fraud
strategy beyond rule gates, availability/DDoS.

## 6. Residual risks (accepted in sandbox; must clear before real funds)

R1 Legacy intent path lacks digest binding + atomic consume (bindings are the
   hardened path; migration pending — REMEDIATION_PLAN R-03/R-04).
R2 PDP sandbox wiring passes permissive intent context (strict rollout pending).
R3 No WORM storage; single-admin DB access can rewrite chains (detectable via
   exports, not prevented).
R4 Signer identity is bearer-credential binding, not asymmetric/WebAuthn.
R5 AI tool gateway (`invoke_tool`) unwired — wire with allowlist or remove.

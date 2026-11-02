# AI Security Policy — Universal Hybrid Payment Terminal

Status: sandbox/testnet only. No production deployment without explicit approval.
Enforcement: backend code (`modal_backend/ai_guardrails/`), never prompts alone.

## 1. Core principle

The AI (Meta Muse Spark 1.3 via Modal FastAPI) is an **advisory system, never an
autonomous financial authority**. No AI output may approve, sign, release,
transfer, freeze, seize, or otherwise move funds — directly or indirectly.

## 2. Capabilities (allowlisted, read-only)

The AI may only phrase explanations over data the backend already authorized:

- `explain_receipt`, `summarize_agreement`, `list_eligible_routes`,
  `risk_indicators_readonly`, `explain_chain_state`, `assistant_reply`

Every AI response carries `advisoryOnly: true`. Fraud/risk outputs additionally
state they are heuristic and **NOT certified fraud detection**.

## 3. Forbidden actions (denied by construction)

Payment execution/capture/refund/cancel, wallet signing, private-key/seed
access, account freezing, asset seizure, balance/ledger mutation, permission or
role management, tenant reassignment, contract modification, settlement
declaration, credential/API-key disclosure. No tool exists for these; the
policy engine (`policy.py`) double-denies them by name even if smuggled in.

## 4. Enforcement layers (defense in depth, server-side)

1. **Deterministic policy engine** (`ai_guardrails/policy.py`): default-deny
   tool authorization; AI decisions evaluate to `approved: false` always.
2. **Input validation**: length caps, control-character stripping, schema checks.
3. **Prompt-injection / role-spoofing / exfiltration filters** (`redaction.py`):
   matches fail closed to a safe refusal; no model call is made.
4. **Sensitive-data redaction**: API keys, secrets, seeds, PAN/IBAN-like runs,
   private-key-shaped hex are scrubbed before any model request and from logs.
5. **Output schema validation**: pydantic models; failures → safe fallback
   (fraud fails closed to `high` = human review required).
6. **Rate limits** (`AI_RATE_LIMIT_PER_MIN`, 429), **timeouts**, bounded retries,
   **spending caps** via `max_tokens: 800` and per-tenant usage counters.
7. **Human review**: fraud signals, risk assessments, and financial
   recommendations require a recorded human decision; AI output must never
   automatically become an account restriction or payment decision
   (no consumer of AI output is wired to any authorization path).
8. **Kill-switch**: `POST /api/admin/ai/kill-switch` (admin) or `AI_DISABLED=1`
   stops all `/api/ai/*` model routes with `503 AI_DISABLED` while payment,
   dashboard, and reconcile APIs keep serving.

## 5. Trust boundaries

User messages, uploaded documents, API responses, and retrieved content are
**untrusted**. They are validated, screened, and redacted before reaching the
model, and model output is validated again before reaching the user.

## 6. Logging without personal data

AI tool requests, policy decisions, injection blocks, and kill-switch events
are logged to a tamper-evident, hash-chained audit log. Tenant/actor ids are
stored as hashes only; prompts, keys, PANs, and balances are never stored.

## 7. Testing

Adversarial coverage in `modal_backend/test_ai_guardrails.py` and the
red-team plan in `AI_RED_TEAM_TESTS.md`: injection, role spoofing,
unauthorized tool use, exfiltration, kill-switch blast radius. CI must keep
them green; any failure blocks deployment.

## 8. Deployment rule

Do not deploy without approval. Production additionally requires
`INSTITUTIONAL_STRICT=1`, bound tenant env vars, and a clean red-team run.

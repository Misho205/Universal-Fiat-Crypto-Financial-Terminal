# Meta Muse Spark AI integration — advisory only, never execution

> Model: `muse-spark-1.3` via `MODEL_API_KEY` (Modal Secret `hybridpay-test`).
> Request shape: OpenAI-compatible `POST {META_MODEL_BASE_URL}/chat/completions`
> (`model`, `messages`, `response_format: {json_object}`, temperature 0).
> AI output is untrusted: validated against explicit pydantic schemas, failures
> degrade to safe stub/fallback envelopes (`validated: false`, fraud fails CLOSED to high).

## Features (all through the Modal backend; key never reaches the browser)
1. **Explain fiat** (`POST /api/ai/explain-transaction`): plain-language receipt walkthrough.
2. **Explain crypto** (`POST /api/ai/explain-crypto`): chain, confirmations progress,
   explorer link, explicit chain-vs-settlement note.
3. **Contract analysis** (`POST /api/ai/contract-analysis`): missing conditions,
   contradictions, operational risks — gaps list; deterministic validator stays authoritative.
4. **Fraud indicators** (`POST /api/ai/fraud-signals`): heuristic weighted indicators with
   explicit notice that they are NOT certified fraud detection; human review decides.
5. **Route recommendations** (`POST /api/ai/routing-recommendation`): from the provided
   provider allow-list + fees/currency/constraints context; never executes.
6. **Agreement state explainer** (`POST /api/ai/explain-state`): why a programmable payment
   is pending/eligible/blocked/completed — deterministic reasons from
   `programmable.evaluate_all` are preserved verbatim; the model only phrases the headline.
7. **Assistant** (`POST /api/ai/assistant`): natural-language terminal helper. Intent is
   classified deterministically first; replies are schema-validated; actions are restricted
   to a read-only allow-list (`open-status-tab`, `open-agreements-tab`, `open-evm-tab`,
   `open-simulator`, `read-docs`); unsafe actions are stripped server-side.

## Technical guarantees
- Timeouts (`META_MODEL_TIMEOUT_S` 15 s) + bounded retries (429/5xx only, backoff 0.5/1.5 s,
  never on 400) + per-tenant rate limit (`AI_RATE_LIMIT_PER_MIN` → 429) + safe error mapping.
- **Usage monitoring**: `GET /api/ai/usage` → `{calls, fallbacks, promptTokens, completionTokens}`;
  counters increment on every model call and every fallback; per-call latency/token
  logging (sizes only, no content, no key) in `meta.call` events.
- **Fallback UI**: every envelope carries `validated` + `model` (`stub (no key)` when offline);
  the terminal shows stub/fallback badges and deterministic data (Status tab, simulator)
  instead of dead ends.
- PII scrubbing (`meta_client.scrub_payload`: PAN runs, provider keys, BTC addresses,
  passwords/seeds/keys, CVV contexts) runs BEFORE any request leaves the process.

## Security (asserted by tests)
- Model output never triggers financial transactions (assistant module contains no
  provider/payment/storage calls — asserted on source).
- No cardholder data, credentials, wallet private keys, or unnecessary PII is sent
  (`test_scrub_*` keeps amounts/currencies while redacting the rest).
- Deterministic backend (`contracts`, `programmable`, provider adapters) alone controls
  authorization and execution; AI envelopes are marked `authoritative: False` / `advisoryOnly`.

## Tests
- Mocked (no network, no tokens): `pytest modal_backend/test_ai_complete.py -q`
  (6 passed: explain fiat+crypto, analysis+state, fraud disclaimer+fail-closed,
  routing+assistant safety, fallback/rate-limit/no-leak, no-money-paths; 1 skipped live).
- Legacy: `pytest modal_backend/test_meta_ai.py -q` (9 passed, 1 skipped).
- Optional live (consumes tokens, one tiny call per new family):
  `RUN_META_INTEGRATION=1 MODEL_API_KEY=<key> META_MODEL_BASE_URL=<url>
  API_SHARED_TOKEN=dev-shared-token pytest modal_backend/test_ai_complete.py -q`
- Frontend (mocked): terminal `demo-flow.test.ts` assistant + state-explainer cases.

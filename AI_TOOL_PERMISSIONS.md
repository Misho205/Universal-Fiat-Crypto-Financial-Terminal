# AI Tool Permissions — allowlist matrix

Server-side enforcement: `modal_backend/ai_guardrails/policy.py::evaluate_tool`
+ `tools.py::invoke_tool`. Default-deny: anything not listed here is refused
with `DENY`, logged, and audited. Prompts cannot grant permissions.

## Allowlisted read-only tools

| Tool | Reads | Writes | Roles | Notes |
|---|---|---|---|---|
| `explain_receipt` | receipt passed by route | none | operator, admin | summary + state only |
| `summarize_agreement` | agreement passed by route | none | operator, admin | eligibility ≠ execution note |
| `list_eligible_routes` | static allowlist | none | operator, admin | deterministic engine decides |
| `risk_indicators_readonly` | tx passed by route | none | operator, admin | heuristic; human review required |
| `explain_chain_state` | snapshot passed by route | none | operator, admin | confirmed ≠ settled |
| `assistant_reply` | topic string | none | operator, admin | UI hints only (`read-docs`, `open-simulator`) |

All return `{advisoryOnly: true, authoritative: false}`. No tool receives
credentials, keys, or cross-tenant data (routes already enforce bearer auth
+ token-derived tenant scope).

## Forbidden actions (never a tool; denied by name)

`execute_payment`, `capture_payment`, `refund_payment`, `cancel_payment`,
`sign_transaction`, `sign_wallet`, `export_private_key`, `reveal_seed`,
`freeze_account`, `seize_assets`, `modify_balance`, `adjust_ledger`,
`grant_permission`, `revoke_permission`, `change_role`, `reassign_tenant`,
`modify_contract`, `declare_settlement`, `approve_payment`, `release_funds`,
`disclose_api_key`, `disclose_secret`, `disclose_credentials`.

## Decision gate (`POST /api/ai/decision`)

Deterministic, computed by the backend — not the model:

```json
{"approved": false, "autoEnforced": false, "requiresHumanReview": true,
 "advisoryOnly": true, "kind": "fraud"}
```

`approved` is always `false`. `requiresHumanReview` is `true` for fraud, risk,
routing, contract, and financial-recommendation kinds, or whenever
`riskLevel` is medium/high.

## Limits

- Rate: `AI_RATE_LIMIT_PER_MIN` per tenant (429 beyond).
- Spend: `max_tokens: 800`, temperature 0, JSON-only, bounded retries (2).
- Blast radius of kill-switch: `/api/ai/*` → 503; payments unaffected.

## Transparency

`GET /api/ai/policy` publishes this matrix (no secrets). Changes require code
review + red-team re-run (`AI_RED_TEAM_TESTS.md`).

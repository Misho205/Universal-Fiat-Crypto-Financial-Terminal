# Bank & Exchange Integration Guide — HybridPay Terminal

How to embed the terminal in a bank or exchange system: as an iframe widget,
as a white-labeled standalone app, or headless via SDK + webhooks.
Scope: sandbox/testnet integration. Production go-live additionally requires
`docs/real-money-roadmap.md` (license, fiscal, KYC/KYB, custody, audit).

## 1. Integration patterns

| Pattern | Use when | Entry point |
|---|---|---|
| **A. Embedded widget (iframe)** | Bank portal / exchange dashboard tab | `…/banking?embed=1&tenant=bank-a` |
| **B. White-labeled app** | Standalone e-banking module | `NEXT_PUBLIC_BRAND_*` build (see `docs/white-label-embed.md`) |
| **C. Headless API** | Core-banking / matching-engine backend calls us | `@hybridpay/sdk` + webhooks, no UI |

All patterns share one backend contract: **bearer auth + token-derived tenant
scope + idempotency keys**. The frontend never authorizes anything.

## 2. Prerequisites

1. Deploy or point at the Modal backend (`docs/modal-deploy-checklist.md`).
2. Create the `hybridpay-test` Modal Secret:
   `API_SHARED_TOKEN` (operators), `API_ADMIN_TOKEN` (admins/checkers),
   `TENANT_FOR_SHARED_TOKEN` / `TENANT_FOR_ADMIN_TOKEN` (bind each token to
   exactly one tenant, e.g. `bank-a`), `STRIPE_SECRET_KEY_TEST` (`sk_test_…`),
   `STRIPE_WEBHOOK_SECRET_TEST`, `SEPOLIA_RPC_URL` (optional, receipt verify).
3. Verify: `GET /health` → `liveMode OFF`; `GET /ready` → `{"ok":true,…}`.
   Wire `/ready` into your load balancer / Kubernetes readiness probe.

## 3. Authentication & tenant isolation (bank-grade)

- Every request: `Authorization: Bearer <token>` + `X-Tenant-Id`.
- When `TENANT_FOR_*` is set, the tenant **derives from the token** and the
  header is ignored — a portal user cannot spoof another bank's tenant.
- Roles: `operator` (read/create/confirm) vs `admin` (cancel/refund/dispute/
  execute, approvals, kill-switch, audit). Never share the admin token with
  end users; keep it in your back office service.
- Tokens live in memory only (never localStorage); see `session.tsx`.

## 4. Core-banking mapping (banks)

| Bank concept | HybridPay primitive |
|---|---|
| Payment order | `POST /api/payments/fiat` (idempotent) → `…/confirm` → `GET …/{id}` |
| Cancellation / return | `POST …/{id}/cancel` / `…/refund` (admin + maker-checker intent; strict mode: approved intent required) |
| Four-eyes principle | `POST /api/approvals/intents` (maker) → `POST …/approve` (distinct checker, step-up `confirm:true` + reason + Idempotency-Key) |
| Escrow-like hold | **Not supported by design** — programmable agreements are conditional instruction sets, never custody (`docs/programmable-contracts.md`) |
| Statement / audit | `GET /api/dashboard/export?format=csv`, `GET /api/admin/audit` (hash-chained, tenant-scored) |
| Health for ops | `GET /health` (liveness), `GET /ready` (readiness: migrations + store) |

Idempotency: send `Idempotency-Key` on every mutating call; `409
IDEMPOTENCY_CONFLICT` means the same key was reused with a different payload —
generate a new key, never retry blindly. `UNKNOWN` states: query the original
before retry (no failover).

## 5. Exchange mapping

| Exchange concept | HybridPay primitive |
|---|---|
| Fiat on-ramp intent | `POST /api/payments/fiat` + provider `clientSecret` (Stripe TEST hosts card capture; raw PAN never touches us) |
| Crypto leg (testnet) | `POST /api/payments/evm/request` → user signs in own wallet → `…/submit` → `GET …/{id}` (receipt + confirmations; confirmed ≠ settled) |
| Conditional release (e.g. pay-after-KYC/delivery) | `POST /api/contracts/programmable` → activate → evidence (authenticated source only) → approve → `…/execute` (human executor + admin + eligibility) |
| Risk screening (advisory) | `POST /api/ai/fraud-signals` → heuristic only, `policyDecision.requiresHumanReview: true`; never blocks automatically |
| Market/route hints (advisory) | `POST /api/ai/routing-recommendation` → allowlist routes; deterministic engine decides |

## 6. Webhooks (bank ledger updates)

Subscribe your ledger service to `POST /api/webhooks/stripe`:

1. Verify HMAC `stripe-signature` (`t,v1`) against `STRIPE_WEBHOOK_SECRET_TEST`
   (see `payments.verify_stripe_webhook`; test vector via
   `POST /api/webhooks/stripe/test`). Reject on mismatch (401), stale (410).
2. Dedupe on `event.id` (backend already does; keep your own table too).
3. Apply only terminal transitions (`succeeded/failed/canceled`); treat
   `unknown` as "query the original", never as failure.
4. Never trust frontend state — re-`GET` the payment before posting to the ledger.

TypeScript sketch:

```ts
import { createHmac, timingSafeEqual } from "crypto";
export function verifyStripeWebhook(raw: Buffer, sig: string, secret: string, toleranceS = 300): boolean {
  const parts = Object.fromEntries(sig.split(",").map((p) => p.split("=")));
  if (Math.abs(Date.now() / 1000 - Number(parts.t)) > toleranceS) return false;
  const expect = createHmac("sha256", secret).update(`${parts.t}.`).update(raw).digest("hex");
  return timingSafeEqual(Buffer.from(expect), Buffer.from(parts.v1 ?? ""));
}
```

## 7. Institutional controls your compliance team gets for free

- Segregation of duties, no self-approval (same credential = same person),
  multi-party quorum for high-risk amounts (`INSTITUTIONAL_HIGH_RISK_MINOR`,
  default 50000 minor).
- Time-limited purpose-bound JIT elevation (`POST /api/admin/elevation`),
  emergency access with justification + mandatory independent review.
- AI kill-switch (`POST /api/admin/ai/kill-switch`) stops advisory AI without
  touching payments. Full matrix: `AI_SECURITY_POLICY.md`,
  `AI_TOOL_PERMISSIONS.md`, tests: `test_institutional_guardrails.py`.

## 8. Testing checklist (do this in your staging)

1. `pytest modal_backend/ -q` → 101 passed.
2. `node --test tests/property/money-property.test.mjs tests/integration/api-flow.test.mjs`.
3. `modal_backend/probe_live.py` against your deployment URL (covers all 53 paths).
4. Negative tests: forged webhook (401), replay with same key + changed payload
   (409), operator calling refund (403), self-approval (403), kill-switch (503
   AI / 201 payments), cross-tenant read (404).

## 9. Go-live gates (all must hold)

`LIVE_MODE=false` until: signed approval file + live creds (fail-closed,
`docs/live-mode.md`), bound tenants, `INSTITUTIONAL_STRICT=1`, license, fiscal
(NRA H-18), KYC/KYB, custody arrangement, contract audit, pentest, DPA —
see `docs/real-money-roadmap.md`. **Do not deploy without explicit approval.**

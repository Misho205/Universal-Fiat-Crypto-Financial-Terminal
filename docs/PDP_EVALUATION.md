# PDP Evaluation: OPA vs Cerbos vs Embedded Deterministic PDP

Date: 2026-11-02. Context: Modal FastAPI serverless backend
(`modal_backend/`), sandbox only. Decision record for the authorization
architecture. See also `docs/POLICY_MATRIX.md` and `docs/ADRs/`.

## 1. Requirements (from the authorization brief)

Centralize policies for AI, customers, banking staff, administrators, and
service accounts; enforce at every sensitive entry point; default-deny;
attributes (identity, tenant, resource, action, environment, context); no
client-controlled tenant trust; separate evaluation from execution;
multi-party approvals; immutable approval scope + expiry; no privilege
escalation/bypass; independently reviewed, version-controlled policy changes;
compromised-admin containment; explainable decisions; fail-closed; safe
read-only availability; simulation/dry-run; rollback; comprehensive tests.

## 2. Options

### Option A — Open Policy Agent (OPA)

- Mature, Rego policies, `packages/policies/rego/policy_v1.rego` already in
  repo; `infra/docker-compose.yml` runs `opa:0.68.0`; `OPA_URL` configured.
- Cons for THIS backend: OPA is a separate sidecar/process. Modal serverless
  functions are ephemeral and scale to zero — a sidecar means either a remote
  OPA service (network hop, latency, availability coupling, secret plumbing)
  or bundling the OPA binary (image weight, cold starts). Rego bundle
  distribution/versioning needs extra machinery. The existing Rego policy is
  also **not wired** to any backend (`grep OPA_URL` hits docs/compose only).
- Verdict: keep Rego as the portable policy mirror for the NestJS/docker
  path, not as the Modal runtime PDP.

### Option B — Cerbos

- Excellent resource/action/principal model, audit logging, playgrounds.
- Cons for THIS backend: same sidecar problem as OPA (needs a PDP cluster
  beside the API), plus a new vendor dependency, schema-mapping work, and no
  existing in-repo footprint. Overkill for a sandbox with 5 sensitive
  clusters and 2 transport roles.
- Verdict: rejected for now; re-evaluate if multi-service (Nest API + worker
  + Modal) shared enforcement is required in production.

### Option C — Embedded deterministic PDP (SELECTED)

- Implementation: `modal_backend/pdp/policy.py` (pure, no I/O) +
  `modal_backend/pdp/enforcement.py` (FastAPI dependencies).
- Why it wins here: zero infra (baked into the Modal image with the rest of
  `modal_backend/`), zero network hops, deterministic and fully testable
  (46+ policy/rights/guardrail tests), fail-closed by construction, versioned
  in git (`POLICY_BUNDLE_VERSION`), explainable decisions with obligations,
  simulation endpoint, rollback via git revert.
- Honest limits: runs in-process (a compromised backend process compromises
  the PDP too — same is true of any in-app check); policy updates ride with
  deploys (acceptable for sandbox; production should add bundle signing +
  dual-control promotion, see rollout plan).

## 3. How the selected PDP meets each requirement

| Requirement | Mechanism |
|---|---|
| Centralize policies | Single `POLICY_MATRIX` (23 actions); one `evaluate()` |
| Enforce at sensitive entries | `require_policy()` on fiat cancel/refund, agreement execute/cancel/dispute/amend + all rights routes |
| Default-deny | Unknown action/role/resource → DENY; exceptions → DENY |
| Attributes | role (from bearer), tenant (server binding), resource + tenant, action, context (intent/step-up/grants) |
| No client tenant trust | `require_tenant` server binding + PDP cross-tenant check |
| Evaluation/execution split | `policy.evaluate()` pure; handlers execute only on ALLOW |
| Multi-party approval | `needs_intent` + quorum (institutional module) |
| Immutable scope + expiry | `intent_scope_ok` + `intent_fresh` context flags |
| No escalation/bypass | Role allowlists; dual-control for role/tenant mgmt; grant-scope checks |
| Reviewed versioned changes | Bundle version surfaced; `GET /api/pdp/policy-version`; git history |
| Compromised-admin containment | Admin alone cannot grant roles/manage tenants (`dual_control`) |
| Explainable | `{allow, reason, policy_version, obligations}` on every decision |
| Fail-closed | Deny on error; 401 before PDP without token; 403 on deny |
| Safe read-only | `read_only` actions need no intent, stay available |
| Simulation/rollback/tests | `POST /api/pdp/simulate` (dryRun), version pinning, `test_pdp.py` (12) |

## 4. Rollout plan (strict mode)

Sandbox wiring passes permissive intent/step-up context where handlers
already enforce maker-checker + step-up themselves. Strict deployments flip
those flags at the `evaluate_request` call sites so the PDP independently
requires approved, scoped, fresh intents + step-up ceremonies. No handler
logic changes needed.

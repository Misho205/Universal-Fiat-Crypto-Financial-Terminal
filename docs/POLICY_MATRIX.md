# Authorization Policy Matrix — Central PDP

Source of truth: `modal_backend/pdp/policy.py` (`POLICY_MATRIX`,
`POLICY_BUNDLE_VERSION=2026.11.02-v1`). This document mirrors it for humans.
On conflict, the code wins; the mismatch is a bug — file it.

Legend: Roles = customer, operator, approver, auditor, compliance, admin,
owner, service-account. Transport mapping: operator token → `operator`,
admin token → `admin`, tokenless dev → `dev-caller` (= operator least
privilege). Intent = approved multi-party approval (maker + distinct checker
quorum). Step-up = explicit `confirm:true` + reason + Idempotency-Key.

## 1. Customer payments (fiat sandbox create/confirm, EVM request/submit)

| Action | Who | Intent | Step-up | Notes |
|---|---|---|---|---|
| `payment.create` | operator, admin, owner | no | no | audit |
| `payment.confirm` | operator, admin, owner | no | no | provider decides, never frontend |
| `payment.read` | operator, approver, auditor, compliance, admin, owner | no | no | read-only, tenant-scoped |

## 2. Institutional payments (reversals)

| Action | Who | Intent | Step-up | Notes |
|---|---|---|---|---|
| `payment.cancel` | operator, admin, owner | YES | YES | + notify-customer; PDP-wired |
| `payment.refund` | operator, admin, owner | YES | YES | + notify-customer; PDP-wired |

## 3. Account restrictions (Financial Rights Engine)

| Action | Who | Intent | Step-up | Notes |
|---|---|---|---|---|
| `restriction.create` | operator, compliance, admin, owner | YES | YES | + engine auth + rights-review |
| `restriction.lift` | compliance, admin, owner | YES | YES | + notify-customer |
| `restriction.read` | operator, approver, auditor, compliance, admin, owner | no | no | read-only |
| `appeal.decide` | approver, compliance, admin, owner | no | YES | + independent-reviewer (≠ authorizer) |

## 4. Smart-contract changes (programmable fiat agreements)

| Action | Who | Intent | Step-up | Notes |
|---|---|---|---|---|
| `agreement.create` | operator, admin, owner | no | no | terms validated + hashed |
| `agreement.activate` | operator, admin, owner | no | no | creator role in body |
| `agreement.execute` | operator, admin, owner | YES | no | + human executor role; PDP-wired |
| `agreement.cancel` | operator, admin, owner | YES | no | PDP-wired |
| `agreement.dispute` | operator, admin, owner | YES | no | freezes execution; PDP-wired |
| `agreement.amend` | admin, owner | YES | YES | + dual consent to exact terms hash; PDP-wired |

## 5. AI tool execution (advisory only by construction)

| Action | Who | Intent | Step-up | Notes |
|---|---|---|---|---|
| `ai.execute` | operator, approver, auditor, compliance, admin, owner | no | no | advisory-only + audit; can never move funds |

## 6. Data access

| Action | Who | Intent | Step-up | Notes |
|---|---|---|---|---|
| `data.read` | operator, approver, auditor, compliance, admin, owner | no | no | dashboards, lists, status |
| `data.export` | auditor, compliance, admin, owner | no | YES | server CSV; audited |

## 7. Role management (highest sensitivity)

| Action | Who | Intent | Step-up | Notes |
|---|---|---|---|---|
| `role.grant` | admin, owner | YES | YES | + dual-control (admin alone denied) |
| `role.revoke` | admin, owner | YES | YES | + dual-control |

## 8. Tenant management

| Action | Who | Intent | Step-up | Notes |
|---|---|---|---|---|
| `tenant.manage` | admin, owner | YES | YES | + dual-control |

## 9. Emergency operations

| Action | Who | Intent | Step-up | Notes |
|---|---|---|---|---|
| `emergency.grant` | admin, owner | fresh grant substitutes | YES | + mandatory retrospective review |

## 10. Audit log access (append-only; nobody rewrites)

| Action | Who | Intent | Step-up | Notes |
|---|---|---|---|---|
| `audit.read` | auditor, compliance, approver, admin, owner | no | no | operator excluded (least privilege) |

## Enforcement points (PEL)

`require_policy()` is wired on: fiat cancel/refund, agreement
execute/cancel/dispute/amend, all `/api/rights/*` mutations, PDP decision
reads. Every denial is written to the tamper-evident audit log AND
`/api/pdp/decisions`. The frontend cannot bypass: evaluation is server-side
before any state change (proven by `test_pdp.py::test_pdp_endpoints_wired...`
— 401 without token, 403 for wrong role).

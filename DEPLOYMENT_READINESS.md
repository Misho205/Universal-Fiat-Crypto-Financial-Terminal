# Deployment Readiness — sandbox vs production gates

Date: 2026-11-02. Backend: 217 passed / 4 skipped (skips: 4 opt-in live
tests, §3). Frontend: vitest 25/25, `next build` green (/, /banking,
/personal, /simulator, /design-system). Backend boot verified
(`uvicorn modal_backend.api:app`, `/health` liveMode OFF, 85 OpenAPI paths).
No auto-deploy performed; no production capabilities added.

## Sandbox demo: READY ✅

- One-command local run per README Quickstart (`.env`, backend :8000,
  terminal :3000); all five modules operable end-to-end by a human tester.
- Failing-closed defaults: no tokens → dev-caller only; no approval → 403;
  no audit → 503 on sensitive paths; AI disabled → 503 on AI routes only.
- Known quirks: `test_tenant_binding` ordering in ad-hoc subsets (full-suite
  order green, pre-existing); trailing-slash 308s on Next routes (final 200).

## Staging (real users / real data): NOT READY ❌

Blockers: R-05 (WORM + separate audit admin), O-01 (replica concurrency),
L-01 (counsel review + DPA), L-02 (MFA/AV verification), L-04 (SIEM),
R-07, R-11 hardening, Postgres-path test parity.

## Production (real money): NOT READY ❌

All staging blockers plus: R-03/R-04 (bindings-only execution), R-08 (strict
PDP), asymmetric signer identity, trusted timestamps (R-09), independent
pentest + code review (R-10), fiscal/KYC/licensing/CASP
(`docs/real-money-roadmap.md`), and closure of every REMAINING_RISKS.md item
or formal risk acceptance by the accountable owner with legal review.

## Skipped-test accounting (not mistaken for verified)

Executed & green: everything except the 4 opt-in live tests below (require
keys/network absent from sandbox — never executed here):
1. live Meta model call (`RUN_META_INTEGRATION` + key),
2. live Meta model token test (same gate),
3. live Sepolia RPC receipt check (`RUN_SEPOLIA_RPC_TEST` + RPC URL),
4. live backend deployment test (`RUN_LIVE_BACKEND_TESTS` + URL).

NOT TESTED at all (no coverage — do not treat as verified): Postgres paths,
Modal replicas, real MFA, production AV, WORM targets, secret rotation,
browser custody, network/OS layers, human processes, real-money rails.

# Break-Glass Emergency Access Policy

Status: sandbox only. Implementation: `modal_backend/breakglass.py`,
`modal_backend/breakglass_api.py`, migration `007_breakglass_ai_disputes.sql`.
Tests: `modal_backend/test_breakglass.py` (9/9).

## 1. Purpose

Allow narrowly scoped emergency intervention (incident response, containment,
read-only investigation) WITHOUT creating unrestricted financial authority.
There is deliberately no emergency path to: balance modification, asset
transfer, wallet signing, payment cancel/refund/execute, role/tenant
management, policy changes, audit deletion, or lifting legal-order
restrictions.

## 2. Session lifecycle

```
request (operator+, MFA, incident_ref + justification + minimal scopes)
  -> pending_approval -> [independent approver] -> active (TTL ≤ 60 min)
  -> expired | revoked | closed (after mandatory retrospective review)
```

- Approval-service outage (attested): preauthorized activation with
  READ-ONLY scopes only, 15-min TTL, mandatory review within 24h.
- Tokens: opaque per-session values; only sha256 digests stored. Expire
  automatically; revocation is always available (requestor, approver, admin).
  Rotation = revoke + new session.
- No self-extension (identity AND credential), no scope changes after
  creation, max 4h total lifetime across extensions.

## 3. Authentication & authorization

- Strong auth: admin/operator bearer + phishing-resistant MFA attestation
  (`webauthn`/`totp`/`hardware-key` + assertion reference). Sandbox records
  the attestation; production MUST verify WebAuthn/TOTP server-side.
- Least privilege: allowlisted scopes only
  (`payment.read, agreement.read, restriction.read, restriction.create
  [fraud holds only], audit.read, audit.verify, data.read`).
- Independent approval for activation (different identity AND credential);
  per-call step-up (confirm + reason) for the single state-changing gateway
  action (`restriction.create`, fraud-prevention only, via the rights engine).
- Legal/regulatory restrictions cannot be bypassed: the gateway offers no
  lift path for legal orders; restriction creation enforces grounds, evidence,
  expiry, and gag rules.

## 4. Audit & notification

Every initiation, approval, action, expiry, revocation, and review is
recorded in the independent audit system (`breakglass.session.*`,
`breakglass.action.*`) with correlation IDs. Security personnel are notified
via audited `breakglass.notify.*` events, visible at
`GET /api/breakglass/notifications` (auditor/compliance/admin).

## 5. Test coverage (see BREAK_GLASS_TEST_REPORT.md)

Unauthorized activation, expired credentials, privilege escalation, self-
extension, cross-tenant access, balance-manipulation attempt (no such
surface), audit-deletion attempt (no such surface + verify intact), approval
outage (preauth read-only), revocation mid-session, retrospective review.

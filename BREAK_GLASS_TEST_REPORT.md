# Break-Glass Test Report

Date: 2026-11-02. File: `modal_backend/test_breakglass.py` — 9/9 pass.
Full backend suite: 207 passed / 4 skipped. Sandbox only (TestClient, fake
tenants, no real systems).

## Results per required case

| # | Case | Result | What it proves |
|---|---|---|---|
| 1 | Unauthorized emergency activation | PASS | 401 without token; 422 without MFA / with out-of-allowlist scopes |
| 2 | Expired emergency credentials | PASS | Post-TTL gateway calls refused; live-state reports `expired` |
| 3 | Privilege escalation | PASS | Out-of-scope and forbidden-by-design actions refused (403) |
| 4 | Self-extension of emergency access | PASS | Requestor/credential self-extend denied; independent extension capped |
| 5 | Cross-tenant access | PASS | Cross-tenant gateway calls and session reads denied |
| 6 | Attempted balance manipulation | PASS | No such scope/action exists (source-scanned); `restriction.lift` absent from allowlist |
| 7 | Attempted audit deletion | PASS | No such action; chain verifies intact after all scenarios |
| 8 | Approval service outage | PASS | Attested outage activates read-only preauth path; state-changing scopes refused without approval |
| 9 | Revocation during an active session | PASS | Revoke terminates immediately; old token refused; rotation documented |

Plus: independent approval (requestor cannot approve), MFA required,
retrospective review (requestor cannot review; closes the session),
security notifications visible to auditor roles.

## Limitations

Sandbox MFA is attested, not cryptographically verified — production must
verify WebAuthn/TOTP server-side. Single-credential sandbox: independence is
identity-level (mirrors institutional emergency review); production needs a
second hardware credential / OIDC claim. No real paging/SIEM integration;
notifications are audit events consumed via API.

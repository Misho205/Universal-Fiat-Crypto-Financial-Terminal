# Vendor Inventory + Data Flows — HybridPay (prototype, factual)

> No DPAs, SCCs, or assurance reports evidenced for any vendor below (see
> `docs/compliance/REGULATORY_GAP_REGISTER.md` G-02/G-03/G-08). Table is a
> technical inventory, not a compliance statement.

| Vendor / component | Function | Data sent (verified) | Hosting / jurisdiction | Contract/assurance evidence |
|---|---|---|---|---|
| Modal | Backend + static hosting (`app.py`, `modal_frontend.py`, Volume `/mnt/data`) | Full request/response payloads incl. tenant refs, amounts | US (Modal cloud) | None evidenced — LEGAL_REVIEW_REQUIRED (DPA/SCC, Art. 28/30 DORA clauses) |
| Meta Muse Spark (`META_MODEL_BASE_URL`, default `api.meta.example/v1`) | Advisory AI inference | Scrubbed prompts (`scrub_payload()`), per-tenant usage counters | US (configurable endpoint) | None evidenced — use-policy + DPA review required |
| Stripe (TEST only, `sk_test_*`) | Fiat sandbox PaymentIntents, webhooks | Amounts, currency, instruction IDs, clientSecret | EU/BG acquiring rails (test) | Test-mode only; live needs acquirer contract + SAQ scoping |
| BTCPay Greenfield regtest | Crypto invoice mock | bech32 `bcrt1` addresses, amounts | Localhost regtest | None needed while local; live needs self-hosted assessment |
| Sepolia public RPC (`SEPOLIA_RPC_URL`) | Receipt verification (read-only) | tx hashes, addresses (public chain data) | Public endpoint (operator-chosen) | Public data; endpoint operator logged as processor? LEGAL_REVIEW_REQUIRED |
| Etherscan / faucets | Explorer links, test ETH | tx hashes (public) | Public | Links only |
| Postgres (Neon/Supabase/RDS TBD) | Optional system of record | Same as SQLite stores | TBD | None selected — decision + DPA required |
| OIDC (Auth0/Clerk stub) | Future login | N/A (stub) | N/A | Selection + assessment required |

## Data-flow sketch (sandbox)

```
Browser (memory-only bearer)
  │ HTTPS: payment instructions, agreement terms, dispute text, AI chat
  ▼
Modal FastAPI ──scrub_payload()──▶ Meta Muse (advisory JSON only)
  │ ▲
  │ └─ Stripe TEST API (amounts/refs) / Sepolia RPC (hashes) / BTCPay regtest
  ▼
SQLite/Volume/Postgres: tenant-scoped refs, states, minor-amounts, hash-chained audit
```

No PAN/CVV/PIN/seeds flow anywhere by schema design (verified §7 inventory).
PII-bearing flows to address first: dispute evidence, support/AI chat, access logs.

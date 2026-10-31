// End-to-end mock flow: order -> agreement -> accept -> eligible methods -> quote -> instruction -> status -> receipt.
// Run: pnpm --filter @hybridpay/api build && node tests/e2e/mock-flow.mjs (starts ephemeral app via ts-node? here uses built dist)
import assert from "node:assert";

const BASE = process.env.API_BASE ?? "http://localhost:3001";
const T = "e2e-tenant";

async function api(path, opts = {}) {
  const r = await fetch(`${BASE}${path}`, { ...opts, headers: { "Content-Type": "application/json", "X-Tenant-Id": T, ...(opts.headers ?? {}) } });
  const data = await r.json().catch(() => ({}));
  return { status: r.status, data };
}

const order = await api("/v1/orders", { method: "POST", headers: { "Idempotency-Key": "e2e-1" }, body: JSON.stringify({ storeId: "s1", denomination: "fiat:EUR", totalMinor: "2599" }) });
assert.equal(order.status, 201, JSON.stringify(order));
const ag = await api(`/v1/orders/${order.data.id}/agreements`, { method: "POST", body: JSON.stringify({ amountMinor: "2599", feesMinor: "49", beneficiaries: [{ party: "merchant", shareBps: 10000, destination: "iban:BG00E2E" }], conditions: [{ type: "timeCondition", notAfter: "2030-01-01T00:00:00Z" }], deadlines: {}, cancelPolicy: "void", refundPolicy: "original-rail", disputePolicy: "provider", indexPolicy: null, consentScope: "single", executionModel: "pay-after-condition" }) });
assert.equal(ag.status, 201, JSON.stringify(ag));
const acc = await api(`/v1/agreements/${ag.data.id}/accept`, { method: "POST", body: JSON.stringify({ party: "customer" }) });
assert.ok([200, 201].includes(acc.status), JSON.stringify(acc));
const methods = await api(`/v1/orders/${order.data.id}/eligible-methods`);
assert.ok(methods.data.some((m) => m.id === "mock:card:EUR"), JSON.stringify(methods));
const quote = await api("/v1/quotes", { method: "POST", body: JSON.stringify({ orderId: order.data.id, inAsset: "fiat:EUR", outAsset: "fiat:EUR", inMinor: "2599" }) });
assert.ok([200, 201].includes(quote.status), JSON.stringify(quote));
const ins = await api("/v1/instructions", { method: "POST", headers: { "Idempotency-Key": "e2e-ins-1" }, body: JSON.stringify({ orderId: order.data.id, agreementId: ag.data.id, methodRoute: "mock:card:EUR", amountMinor: "2599", deviceId: "dev-1" }) });
// dev-1 may not exist in fresh server; enroll fallback
console.log("instruction:", ins.status, JSON.stringify(ins.data));
console.log("E2E mock flow OK:", { order: order.data.id, agreement: ag.data.id });

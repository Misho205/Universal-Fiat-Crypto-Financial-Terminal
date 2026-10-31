import { describe, it, expect, vi, beforeEach } from "vitest";
import { ModalBackendClient, HybridPayClient } from "@hybridpay/sdk";

// Hackathon demo workflow E2E (mocked network): order -> checkout -> fiat simulate -> status -> contract validate.
function mockFetch(routes: Record<string, { status: number; body: unknown }>) {
  return vi.fn(async (url: string, init?: RequestInit) => {
    const u = new URL(url, "http://x");
    const key = `${init?.method ?? "GET"} ${u.pathname}`;
    const hit = routes[key];
    if (!hit) return { ok: false, status: 404, json: async () => ({ detail: "not found" }) };
    return { ok: hit.status < 400, status: hit.status, json: async () => hit.body };
  });
}

beforeEach(() => vi.unstubAllGlobals());

describe("hackathon demo flow", () => {
  it("order -> qr -> fiat sandbox -> status -> contract ok", async () => {
    vi.stubGlobal("fetch", mockFetch({
      "POST /v1/orders": { status: 201, body: { id: "ord-demo" } },
      "POST /v1/orders/ord-demo/checkout-token": { status: 201, body: { token: "tok", qrPayload: "hybridpay://pay/tok" } },
      "POST /api/payments/fiat/simulate": { status: 201, body: { transactionId: "tx-demo", state: "AUTHORIZED", sandbox: true } },
      "GET /api/transactions/tx-demo": { status: 200, body: { transactionId: "tx-demo", state: "AUTHORIZED", sandbox: true } },
      "POST /api/contracts/validate": { status: 200, body: { ok: true, errors: [], versionHash: "abc" } },
    }));
    const nest = new HybridPayClient({ baseUrl: "http://nest", tenantId: "demo-tenant" });
    const modal = new ModalBackendClient({ baseUrl: "http://modal", tenantId: "demo-tenant" });
    const o = await nest.createOrder({ storeId: "s1", denomination: "fiat:EUR", totalMinor: "1000" }, "demo-key-1");
    expect(o.status).toBe(201);
    const tok = await nest.checkoutToken("ord-demo", 1);
    expect((tok.data as { qrPayload: string }).qrPayload).toMatch(/^hybridpay:\/\//);
    const pay = await modal.fiatSimulate({ amountMinor: "1000", instructionId: "demo-ins" }, "demo-key-2");
    expect(pay.data.sandbox).toBe(true);
    const st = await modal.txStatus("tx-demo");
    expect(st.data.state).toBe("AUTHORIZED");
    const c = await modal.validateContract({ amountMinor: "1000" });
    expect(c.data.ok).toBe(true);
  });
  it("duplicate submit uses stable idempotency key (no double charge)", async () => {
    const fn = mockFetch({ "POST /api/payments/fiat/simulate": { status: 201, body: { transactionId: "tx-1", state: "AUTHORIZED", sandbox: true } } });
    vi.stubGlobal("fetch", fn);
    const modal = new ModalBackendClient({ baseUrl: "http://modal", tenantId: "t" });
    const stableKey = "ui-fixed-key";
    await modal.fiatSimulate({ amountMinor: "100", instructionId: "a" }, stableKey);
    await modal.fiatSimulate({ amountMinor: "100", instructionId: "a" }, stableKey);
    const keys = fn.mock.calls.map((c) => (c[1] as RequestInit & { headers: Record<string, string> }).headers["Idempotency-Key"]);
    expect(keys).toEqual([stableKey, stableKey]);
  });
  it("evm sepolia flow: request -> submit -> receipt (mocked, mainnet never used)", async () => {
    vi.stubGlobal("fetch", mockFetch({
      "POST /api/payments/evm/request": { status: 201, body: { paymentId: "evm-1", chainId: 11155111, state: "requested", sandbox: true } },
      "POST /api/payments/evm/evm-1/submit": { status: 200, body: { paymentId: "evm-1", state: "pending", explorer: "https://sepolia.etherscan.io/tx/0x1" } },
      "GET /api/payments/evm/evm-1": { status: 200, body: { paymentId: "evm-1", state: "confirmed", confirmations: 3, confirmationsRequired: 2, businessSettled: false } },
    }));
    const modal = new ModalBackendClient({ baseUrl: "http://modal", tenantId: "t" });
    const r = await modal.evmRequest({ to: `0x${"ab".repeat(20)}`, valueWei: "1000" }, "k");
    expect(r.data.chainId).toBe(11155111);
    const s = await modal.evmSubmit("evm-1", `0x${"11".repeat(32)}`);
    expect(s.data.explorer).toMatch(/sepolia.etherscan.io/);
    const g = await modal.evmStatus("evm-1");
    expect(g.data.state).toBe("confirmed");
    expect(g.data.businessSettled).toBe(false); // chain != settlement
  });
  it("programmable agreement flow: create -> get eligible -> execute (mocked)", async () => {
    vi.stubGlobal("fetch", mockFetch({
      "POST /api/contracts/programmable": { status: 201, body: { agreementId: "pag-1", state: "draft", sandbox: true } },
      "GET /api/contracts/programmable/pag-1": { status: 200, body: { agreementId: "pag-1", state: "eligible_for_execution", eligible: true, chainValid: true } },
      "POST /api/contracts/programmable/pag-1/execute": { status: 200, body: { agreementId: "pag-1", state: "completed", sandbox: true } },
    }));
    const modal = new ModalBackendClient({ baseUrl: "http://modal", tenantId: "t" });
    const c = await modal.pagCreate({ amountMinor: "100" }, "creator", "k");
    expect(c.data.sandbox).toBe(true);
    const g = await modal.pagGet("pag-1");
    expect(g.data.eligible).toBe(true);
    const ex = await modal.pagExecute("pag-1", "finance-op", "k-exec");
    expect((ex.data as { state: string }).state).toBe("completed");
  });
  it("ai assistant + state explainer are advisory-only with validated flags (mocked)", async () => {
    vi.stubGlobal("fetch", mockFetch({
      "POST /api/ai/assistant": { status: 200, body: { advisoryOnly: true, validated: true, kind: "assistant", data: { answer: "a", topic: "general", actions: [], needsHuman: false }, notice: "n" } },
      "POST /api/ai/explain-state": { status: 200, body: { advisoryOnly: true, validated: true, kind: "state-explanation", data: { state: "active", headline: "h", reasons: [], nextSteps: [] }, notice: "n" } },
      "GET /api/ai/usage": { status: 200, body: { calls: 2, fallbacks: 0, promptTokens: 1, completionTokens: 1, sandbox: true } },
    }));
    const modal = new ModalBackendClient({ baseUrl: "http://modal", tenantId: "t" });
    const a = await modal.aiAssistant("what can you do?", {});
    expect(a.data.advisoryOnly).toBe(true);
    expect(a.data.data.needsHuman).toBe(false);
    const s = await modal.aiExplainState({ state: "active" });
    expect(s.data.validated).toBe(true);
    const u = await modal.aiUsage();
    expect(u.data.calls).toBe(2);
  });
});

import { describe, it, expect, vi, beforeEach } from "vitest";
import { HybridPayClient, ModalBackendClient, ApiError, friendlyError, resolveBaseUrl } from "../src/index.js";

function mockFetchOnce(status: number, data: unknown) {
  const fn = vi.fn(async () => ({ ok: status < 400, status, json: async () => data }));
  vi.stubGlobal("fetch", fn);
  return fn;
}

beforeEach(() => vi.unstubAllGlobals());

describe("sdk", () => {
  it("createOrder posts tenant + idempotency headers", async () => {
    const fetchMock = mockFetchOnce(201, { id: "ord-1" });
    const c = new HybridPayClient({ baseUrl: "http://api", tenantId: "t1" });
    const r = await c.createOrder({ storeId: "s1" }, "k1");
    expect(r.status).toBe(201);
    expect(fetchMock).toHaveBeenCalledOnce();
    const [url, opts] = fetchMock.mock.calls[0] as unknown as [string, RequestInit & { headers: Record<string, string> }];
    expect(url).toBe("http://api/v1/orders");
    expect(opts.headers["X-Tenant-Id"]).toBe("t1");
    expect(opts.headers["Idempotency-Key"]).toBe("k1");
  });
  it("getStatus queries instruction by id", async () => {
    const fetchMock = mockFetchOnce(200, { id: "ins-1", state: "AUTHORIZED" });
    const c = new HybridPayClient({ baseUrl: "http://api", tenantId: "t1", token: "tok" });
    const r = await c.getStatus("ins-1");
    expect(r.data.state).toBe("AUTHORIZED");
    const [url, opts] = fetchMock.mock.calls[0] as unknown as [string, RequestInit & { headers: Record<string, string> }];
    expect(url).toBe("http://api/v1/instructions/ins-1");
    expect(opts.headers.Authorization).toBe("Bearer tok");
  });
});

describe("modal backend client", () => {
  it("resolves base URL from explicit value, never embeds secrets", async () => {
    expect(resolveBaseUrl("https://demo.modal.run", "http://localhost:8000")).toBe("https://demo.modal.run");
    const fetchMock = mockFetchOnce(201, { transactionId: "tx-1", state: "AUTHORIZED", sandbox: true });
    const c = new ModalBackendClient({ baseUrl: "https://demo.modal.run", tenantId: "t1", token: "dev-token" });
    const r = await c.fiatSimulate({ amountMinor: "1000", instructionId: "a" }, "idem-1");
    expect(r.data.sandbox).toBe(true);
    const [url, opts] = fetchMock.mock.calls[0] as unknown as [string, RequestInit & { headers: Record<string, string> }];
    expect(url).toBe("https://demo.modal.run/api/payments/fiat/simulate");
    expect(opts.headers["Idempotency-Key"]).toBe("idem-1");
    expect(JSON.stringify(opts)).not.toMatch(/MODEL_API_KEY|STRIPE_SECRET|BTCPAY_API/);
  });
  it("throws ApiError with retryable flag + friendly BG message", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => ({ ok: false, status: 429, json: async () => ({ detail: "slow down" }) })));
    const c = new ModalBackendClient({ baseUrl: "http://x", tenantId: "t1" });
    try {
      await c.fiatSimulate({ amountMinor: "1", instructionId: "a" }, "k");
      expect.unreachable();
    } catch (e) {
      expect(e).toBeInstanceOf(ApiError);
      expect((e as ApiError).retryable).toBe(true);
      expect(friendlyError(e, "bg")).toMatch(/Лимитът/);
    }
  });
});

describe("evm + programmable", () => {
  it("evmRequest posts Sepolia chain + idempotency, never mainnet by default", async () => {
    const fn = mockFetchOnce(201, { paymentId: "evm-1", chainId: 11155111, state: "requested", sandbox: true });
    const c = new ModalBackendClient({ baseUrl: "http://m", tenantId: "t" });
    const r = await c.evmRequest({ to: `0x${"ab".repeat(20)}`, valueWei: "1000" }, "k-evm");
    expect(r.data.chainId).toBe(11155111);
    const [, opts] = fn.mock.calls[0] as unknown as [string, RequestInit & { headers: Record<string, string> }];
    expect(opts.headers["Idempotency-Key"]).toBe("k-evm");
    expect(JSON.stringify(opts)).not.toMatch(/mnemonic|private_?key/i);
  });
  it("pagCreate -> pagGet carry disclosure, execute requires executor (server-enforced)", async () => {
    const fn = mockFetchOnce(201, { agreementId: "pag-1", state: "draft", disclosure: "Not an escrow", sandbox: true });
    const c = new ModalBackendClient({ baseUrl: "http://m", tenantId: "t" });
    const r = await c.pagCreate({ amountMinor: "100" }, "creator", "k-pag");
    expect(r.data.sandbox).toBe(true);
    expect(fn).toHaveBeenCalledOnce();
  });
});

describe("ai", () => {
  it("assistant posts message, returns validated advisory reply", async () => {
    const fn = mockFetchOnce(200, { advisoryOnly: true, validated: true, kind: "assistant",
      data: { answer: "Check Status.", topic: "payments", actions: ["open-status-tab"], needsHuman: false },
      notice: "advisory only" });
    const c = new ModalBackendClient({ baseUrl: "http://m", tenantId: "t" });
    const r = await c.aiAssistant("where is my payment?", {});
    expect(r.data.advisoryOnly).toBe(true);
    const [, opts] = fn.mock.calls[0] as unknown as [string, RequestInit & { headers: Record<string, string> }];
    expect((opts.body as string)).toMatch(/where is my payment/);
  });
  it("explain-crypto/state/usage hit the right paths", async () => {
    const fn = mockFetchOnce(200, { advisoryOnly: true, validated: true, kind: "x", data: {}, notice: "" });
    const c = new ModalBackendClient({ baseUrl: "http://m", tenantId: "t" });
    await c.aiExplainCrypto({ txHash: "0x1" });
    await c.aiExplainState({ state: "active" });
    await c.aiUsage();
    const urls = (fn.mock.calls as unknown as [string][]) .map((cc) => cc[0]);
    expect(urls).toEqual(["http://m/api/ai/explain-crypto", "http://m/api/ai/explain-state", "http://m/api/ai/usage"]);
  });
  it("me + dashboard summary/recent hit role-scoped endpoints", async () => {
    const fn = mockFetchOnce(200, { role: "operator", sandbox: true });
    const c = new ModalBackendClient({ baseUrl: "http://m", tenantId: "t", token: "tok" });
    const me = await c.me();
    expect(me.data.role).toBe("operator");
    const [, opts] = fn.mock.calls[0] as unknown as [string, RequestInit & { headers: Record<string, string> }];
    expect(opts.headers.Authorization).toBe("Bearer tok");
    const fn2 = mockFetchOnce(200, { items: [], sandbox: true });
    await c.dashboardRecent({ kind: "fiat", state: "pending", q: "pay-" });
    const [url2] = fn2.mock.calls[0] as unknown as [string];
    expect(url2).toMatch(/kind=fiat/);
    expect(url2).toMatch(/state=pending/);
  });
});

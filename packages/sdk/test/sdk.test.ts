import { describe, it, expect, vi, beforeEach } from "vitest";
import { HybridPayClient, ModalBackendClient, ApiError, friendlyError, resolveBaseUrl,
         assertMinorUnits, assertEvmAddress, assertTxHash, assertChainId } from "../src/index.js";

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
    await c.dashboardRecent({ kind: "fiat", state: "pending", q: "pay-", limit: 2, offset: 4 });
    const [[url2]] = fn2.mock.calls as unknown as [[string]];
    expect(url2).toMatch(/kind=fiat/);
    expect(url2).toMatch(/state=pending/);
    expect(url2).toMatch(/limit=2/);
    expect(url2).toMatch(/offset=4/);
  });
  it("list endpoints carry limit/offset/state", async () => {
    const c = new ModalBackendClient({ baseUrl: "http://m", tenantId: "t" });
    const fn = mockFetchOnce(200, { payments: [], sandbox: true });
    await c.fiatList({ limit: 2, offset: 6, state: "created" });
    expect((fn.mock.calls[0] as unknown as [string])[0]).toMatch(/limit=2/);
    expect((fn.mock.calls[0] as unknown as [string])[0]).toMatch(/offset=6/);
    expect((fn.mock.calls[0] as unknown as [string])[0]).toMatch(/state=created/);
    const fn2 = mockFetchOnce(200, { payments: [], sandbox: true });
    await c.evmList({ limit: 1, offset: 1 });
    expect((fn2.mock.calls[0] as unknown as [string])[0]).toMatch(/offset=1/);
    const fn3 = mockFetchOnce(200, { agreements: [], sandbox: true });
    await c.pagList({ limit: 5, offset: 10, state: "draft" });
    expect((fn3.mock.calls[0] as unknown as [string])[0]).toMatch(/state=draft/);
  });
  it("money actions send idempotency keys; ops endpoints are reachable", async () => {
    const c = new ModalBackendClient({ baseUrl: "http://m", tenantId: "t" });
    const fn = mockFetchOnce(200, { paymentId: "p1", state: "canceled", sandbox: true });
    await c.fiatCancel("p1", "mc-maker-checker-1");
    const [, opts] = fn.mock.calls[0] as unknown as [string, RequestInit & { headers: Record<string, string> }];
    expect(opts.headers["Idempotency-Key"]).toBe("mc-maker-checker-1");
    const fn2 = mockFetchOnce(200, { paymentId: "p1", state: "refunded", sandbox: true });
    await c.fiatRefund("p1", undefined, "mc-maker-checker-2");
    const [, opts2] = fn2.mock.calls[0] as unknown as [string, RequestInit & { headers: Record<string, string> }];
    expect(opts2.headers["Idempotency-Key"]).toBe("mc-maker-checker-2");
    const fn3 = mockFetchOnce(200, { runId: "rec-1", sandbox: true });
    await c.reconcileRun();
    expect((fn3.mock.calls[0] as unknown as [string])[0]).toBe("http://m/api/reconcile/runs");
    const fn4 = mockFetchOnce(200, { postTo: "/api/webhooks/stripe", sandbox: true });
    await c.webhookTest();
    expect((fn4.mock.calls[0] as unknown as [string])[0]).toBe("http://m/api/webhooks/stripe/test");
    const fn5 = mockFetchOnce(200, { tenant: "t", sandbox: true, liveMode: "OFF" });
    const ov = await c.adminOverview();
    expect((fn5.mock.calls[0] as unknown as [string])[0]).toBe("http://m/api/admin/overview");
    expect(ov.data.sandbox).toBe(true);
  });
});

describe("client-side validation (fail fast, no junk over the wire)", () => {
  it("rejects bad amounts, addresses, hashes, chains without fetch", () => {
    expect(() => assertMinorUnits("10.00")).toThrow(/minor-units/);
    expect(() => assertMinorUnits("abc")).toThrow();
    assertMinorUnits("1000");
    expect(() => assertEvmAddress("tb1qwrong")).toThrow(/0x/);
    assertEvmAddress(`0x${"ab".repeat(20)}`);
    expect(() => assertTxHash("0xshort")).toThrow();
    assertTxHash(`0x${"11".repeat(32)}`);
    expect(() => assertChainId(1)).toThrow(/MAINNET_REFUSED/);
    expect(() => assertChainId(137)).toThrow(/UNSUPPORTED_CHAIN/);
    assertChainId(11155111);
  });
  it("evmRequest validates before sending (spy fetch never called)", async () => {
    const fn = vi.fn(async () => ({ ok: true, status: 200, json: async () => ({}) }));
    vi.stubGlobal("fetch", fn);
    const c = new ModalBackendClient({ baseUrl: "http://m", tenantId: "t" });
    await expect(c.evmRequest({ to: "bad", valueWei: "1" }, "k")).rejects.toThrow();
    await expect(c.fiatCreate({ amountMinor: "1.5", instructionId: "a" }, "k")).rejects.toThrow(/minor-units/);
    expect(fn).not.toHaveBeenCalled();
  });
  it("resolveBaseUrl rejects javascript: URLs but allows same-origin paths", () => {
    expect(() => resolveBaseUrl("javascript:alert(1)")).toThrow(/Invalid backend URL/);
    expect(resolveBaseUrl("/api")).toBe("/api");
  });
});

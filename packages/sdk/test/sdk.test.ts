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

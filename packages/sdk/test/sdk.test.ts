import { describe, it, expect, vi, beforeEach } from "vitest";
import { HybridPayClient } from "../src/index.js";

function mockFetchOnce(status: number, data: unknown) {
  const fn = vi.fn(async () => ({ status, json: async () => data }));
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

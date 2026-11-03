import { describe, it, expect, vi, beforeEach } from "vitest";
import { ModalBackendClient } from "@hybridpay/sdk";

// Auth header propagation: the SDK must send `Authorization: Bearer <token>`
// when signed in and omit it when signed out. The Modal proxy allowlists and
// forwards `authorization`; the FastAPI backend returns 401 otherwise.
function captureFetch(status: number, body: unknown) {
  const fn = vi.fn(async (url: string, init?: RequestInit) => {
    return { ok: status < 400, status, json: async () => body };
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}

beforeEach(() => vi.unstubAllGlobals());

describe("operator auth headers", () => {
  it("sends Bearer + tenant + idempotency headers when signed in", async () => {
    const fn = captureFetch(201, { transactionId: "tx-1", state: "AUTHORIZED", sandbox: true });
    const modal = new ModalBackendClient({ baseUrl: "http://modal", tenantId: "demo-tenant", token: "op-token" });
    await modal.fiatSimulate({ amountMinor: "1000", instructionId: "a", currency: "EUR" }, "k-1");
    const [, init] = fn.mock.calls[0] as [string, RequestInit & { headers: Record<string, string> }];
    expect(init.headers["Authorization"]).toBe("Bearer op-token");
    expect(init.headers["X-Tenant-Id"]).toBe("demo-tenant");
    expect(init.headers["Idempotency-Key"]).toBe("k-1");
  });
  it("omits Authorization when signed out (backend must 401, never bypass)", async () => {
    const fn = captureFetch(401, { detail: "missing bearer token" });
    const modal = new ModalBackendClient({ baseUrl: "http://modal", tenantId: "demo-tenant" });
    await expect(
      modal.fiatSimulate({ amountMinor: "1000", instructionId: "a", currency: "EUR" }, "k-1"),
    ).rejects.toMatchObject({ status: 401 });
    const [, init] = fn.mock.calls[0] as [string, RequestInit & { headers: Record<string, string> }];
    expect("Authorization" in init.headers).toBe(false);
  });
  it("surfaces 403 for authenticated-but-unauthorized (operator on admin path)", async () => {
    captureFetch(403, { detail: "admin role required" });
    const modal = new ModalBackendClient({ baseUrl: "http://modal", tenantId: "demo-tenant", token: "op-token" });
    await expect(modal.fiatCancel("pay-1")).rejects.toMatchObject({ status: 403 });
  });
});

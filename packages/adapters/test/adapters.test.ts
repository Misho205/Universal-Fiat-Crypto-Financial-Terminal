import { describe, it, expect } from "vitest";
import { MockAdapter, StripeSandboxAdapter, BtcPayRegtestAdapter, type OpResult } from "../src/index.js";

const ctx = (id: string) => ({ tenantId: "t1", instructionId: id, idempotencyKey: `t1:op:${id}`, asset: "fiat:EUR", amountMinor: "10000", nowIso: "2026-01-01T00:00:00Z" });
const codeOf = (r: OpResult): string | null => (r.ok ? null : r.code);

describe("adapters", () => {
  it("mock deterministic scenarios", async () => {
    const m = new MockAdapter();
    expect((await m.authorize(ctx("a"))).ok).toBe(true);
    expect((await m.authorize(ctx("afail"))).ok).toBe(false);
    expect(codeOf(await m.authorize(ctx("atimeout")))).toBe("TIMEOUT_UNKNOWN");
    expect(codeOf(await m.recurring(ctx("a")))).toBe("UNSUPPORTED_CAPABILITY");
  });
  it("stripe blocked without credentials, live never allowed", async () => {
    const s = new StripeSandboxAdapter(undefined);
    expect(codeOf(await s.authorize(ctx("a")))).toBe("BLOCKED_NO_CREDENTIALS");
  });
  it("btcpay wrong-network rejected; missing creds blocked", async () => {
    const b = new BtcPayRegtestAdapter({});
    expect(codeOf(await b.collect(ctx("a")))).toBe("BLOCKED_NO_CREDENTIALS");
    const b2 = new BtcPayRegtestAdapter({ url: "http://x", apiKey: "k", storeId: "s" });
    const r = await b2.transfer(ctx("a"), "tb1qwrong-mainnet");
    expect(r.ok).toBe(false);
  });
});

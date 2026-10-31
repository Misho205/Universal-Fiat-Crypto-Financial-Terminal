import { describe, it, expect } from "vitest";
import { parseToMinor, formatFromMinor, canTransition, idempotencyKey, eligibleMethods } from "../src/index.js";

describe("money", () => {
  it("parses and formats EUR exactly", () => {
    expect(parseToMinor("100.00", 2)).toBe(10000n);
    expect(formatFromMinor(10000n, 2)).toBe("100.00");
    expect(formatFromMinor(parseToMinor("0.07", 2) + parseToMinor("0.01", 2), 2)).toBe("0.08");
  });
  it("rejects float abuse", () => {
    expect(() => parseToMinor("10.001", 2)).toThrow();
    expect(() => parseToMinor("abc", 2)).toThrow();
  });
  it("BTC 8 decimals roundtrip", () => {
    expect(formatFromMinor(parseToMinor("0.00000001", 8), 8)).toBe("0.00000001");
  });
});

describe("state machine", () => {
  it("allows PENDING->AUTHORIZED->SETTLED, forbids SETTLED->CANCELLED", () => {
    expect(canTransition("PENDING", "AUTHORIZED")).toBe(true);
    expect(canTransition("AUTHORIZED", "SETTLED")).toBe(true);
    expect(canTransition("SETTLED", "CANCELLED")).toBe(false);
  });
  it("UNKNOWN can recover or fail, never silently succeed", () => {
    expect(canTransition("UNKNOWN", "SETTLED")).toBe(true);
    expect(canTransition("UNKNOWN", "FAILED")).toBe(true);
  });
});

describe("idempotency + eligibility", () => {
  it("stable key, content-sensitive", () => {
    const a = idempotencyKey("t1", "createOrder", { x: 1 });
    const b = idempotencyKey("t1", "createOrder", { x: 1 });
    const c = idempotencyKey("t1", "createOrder", { x: 2 });
    expect(a).toBe(b); expect(a).not.toBe(c);
  });
  it("hides blocked routes and requires approved conversion", () => {
    const routes: Parameters<typeof eligibleMethods>[0] = [
      { id: "mock:card:EUR", paymentAsset: "fiat:EUR", settlementAsset: "fiat:EUR", denominationAssets: ["fiat:EUR"], capabilities: {} as never, status: "MOCK_OK", needsConversionRoute: false },
      { id: "x:btc:unapproved", paymentAsset: "crypto:bitcoin-regtest:native", settlementAsset: "fiat:EUR", denominationAssets: ["fiat:EUR"], capabilities: {} as never, status: "MOCK_OK", needsConversionRoute: true },
    ];
    expect(eligibleMethods(routes, { denomination: "fiat:EUR" }).map((r) => r.id)).toEqual(["mock:card:EUR"]);
  });
});

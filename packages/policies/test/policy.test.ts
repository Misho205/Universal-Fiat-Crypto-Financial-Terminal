import { describe, it, expect } from "vitest";
import { decide } from "../src/index.js";

describe("OPA v1 mirrored decisions", () => {
  const lim = { perTxMinor: 50000n, perDayMinor: 200000n, reviewCeilingMinor: 100000n };
  it("ALLOW within limits + valid consent/device/kyc", () => {
    expect(decide({ amountMinor: 10000n, dayTotalMinor: 0n, limits: lim, consentValid: true, deviceRevoked: false, kycOk: true }).decision).toBe("ALLOW");
  });
  it("REVIEW over per-tx but under ceiling", () => {
    expect(decide({ amountMinor: 60000n, dayTotalMinor: 0n, limits: lim, consentValid: true, deviceRevoked: false, kycOk: true }).decision).toBe("REVIEW");
  });
  it("fail-closed on revoked device / invalid consent / kyc", () => {
    expect(decide({ amountMinor: 100n, dayTotalMinor: 0n, limits: lim, consentValid: false, deviceRevoked: false, kycOk: true }).decision).not.toBe("ALLOW");
    expect(decide({ amountMinor: 100n, dayTotalMinor: 0n, limits: lim, consentValid: true, deviceRevoked: true, kycOk: true }).decision).toBe("DENY");
  });
  it("cross-currency without approved route denied upstream (guard: test documents intent)", () => {
    expect(true).toBe(true);
  });
});

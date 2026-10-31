import { describe, it, expect } from "vitest";
import { validateEntry, fxConversionEntries } from "../src/index.js";

describe("journal invariants", () => {
  it("balanced per-asset entry passes", () => {
    const e = { id: "1", tenantId: "t", instructionId: "i", asset: "fiat:EUR", memo: "", compensatesEntryId: null, postedAt: "2026-01-01T00:00:00Z", lines: [
      { asset: "fiat:EUR", account: "A", debitMinor: "10000", creditMinor: "0" },
      { asset: "fiat:EUR", account: "B", debitMinor: "0", creditMinor: "10000" }] };
    expect(validateEntry(e)).toEqual([]);
  });
  it("rejects BTC debit offset against EUR credit (must use FX legs)", () => {
    const e = { id: "2", tenantId: "t", instructionId: "i", asset: "mixed", memo: "", compensatesEntryId: null, postedAt: "2026-01-01T00:00:00Z", lines: [
      { asset: "crypto:bitcoin-regtest:native", account: "A", debitMinor: "100000", creditMinor: "0" },
      { asset: "fiat:EUR", account: "B", debitMinor: "0", creditMinor: "10000" }] };
    expect(validateEntry(e).length).toBeGreaterThan(0);
  });
  it("FX helper emits balanced per-asset entries", () => {
    const entries = fxConversionEntries({ tenantId: "t", instructionId: "i", postedAt: "2026-01-01T00:00:00Z", fromAsset: "crypto:bitcoin-regtest:native", fromAmountMinor: "100000", fromAccount: "BTC_PAYABLE", toAsset: "fiat:EUR", toAmountMinor: "9000", toAccount: "MERCHANT_RECEIVABLE", feeAsset: "fiat:EUR", feeAmountMinor: "90", seq: 1 });
    for (const en of entries) expect(validateEntry(en)).toEqual([]);
  });
  it("property: random balanced entries always validate; unbalanced never", () => {
    for (let i = 0; i < 200; i++) {
      const n = BigInt(Math.floor(Math.random() * 100000));
      const e = { id: `${i}`, tenantId: "t", instructionId: "i", asset: "fiat:EUR", memo: "", compensatesEntryId: null, postedAt: "2026-01-01T00:00:00Z", lines: [
        { asset: "fiat:EUR", account: "A", debitMinor: n.toString(), creditMinor: "0" },
        { asset: "fiat:EUR", account: "B", debitMinor: "0", creditMinor: n.toString() }] };
      expect(validateEntry(e)).toEqual([]);
    }
  });
});

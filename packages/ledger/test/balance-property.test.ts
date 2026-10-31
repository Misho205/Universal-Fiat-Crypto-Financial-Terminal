import { describe, it, expect } from "vitest";
import { validateEntry, fxConversionEntries } from "../src/index.js";

describe("ledger balance property", () => {
  it("every generated FX conversion validates (200 cases)", () => {
    for (let i = 0; i < 200; i++) {
      const entries = fxConversionEntries({
        tenantId: "t1",
        instructionId: `ins-${i}`,
        postedAt: "2026-01-01T00:00:00Z",
        fromAsset: "crypto:bitcoin-regtest:native",
        fromAmountMinor: String(1000 + i),
        fromAccount: "merchant_btc_payable",
        toAsset: "fiat:EUR",
        toAmountMinor: String(50000 + i * 10),
        toAccount: "merchant_receivable",
        feeAsset: "fiat:EUR",
        feeAmountMinor: String(50 + (i % 7)),
        seq: i,
      });
      expect(entries).toHaveLength(3);
      for (const e of entries) expect(validateEntry(e)).toEqual([]);
    }
  });
  it("rejects cross-asset netting", () => {
    const bad = {
      id: "bad-1", tenantId: "t1", instructionId: "i1", asset: "fiat:EUR",
      memo: "bad", compensatesEntryId: null, postedAt: "2026-01-01T00:00:00Z",
      lines: [
        { asset: "fiat:EUR", account: "a", debitMinor: "100", creditMinor: "0" },
        { asset: "crypto:bitcoin-regtest:native", account: "b", debitMinor: "0", creditMinor: "100" },
      ],
    };
    expect(validateEntry(bad).length).toBeGreaterThan(0);
  });
  it("rejects unbalanced entry", () => {
    const bad = {
      id: "bad-2", tenantId: "t1", instructionId: "i1", asset: "fiat:EUR",
      memo: "bad", compensatesEntryId: null, postedAt: "2026-01-01T00:00:00Z",
      lines: [{ asset: "fiat:EUR", account: "a", debitMinor: "100", creditMinor: "0" }],
    };
    expect(validateEntry(bad).join(" ")).toMatch(/unbalanced/);
  });
});

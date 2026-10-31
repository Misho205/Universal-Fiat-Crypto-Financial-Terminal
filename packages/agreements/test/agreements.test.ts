import { describe, it, expect } from "vitest";
import { validateTerms, indexedAmountMinor, evaluateConditions, type AgreementTerms } from "../src/index.js";

const base: AgreementTerms = {
  version: 1, denominationAsset: "fiat:EUR", amountMinor: "10000", feesMinor: "150",
  beneficiaries: [{ party: "merchant", shareBps: 10000, destination: "iban:BG00TEST" }],
  conditions: [{ type: "timeCondition", notAfter: "2030-01-01T00:00:00Z" }],
  deadlines: { acceptBy: "2030-01-01T00:00:00Z", executeBy: "2030-01-02T00:00:00Z" },
  cancelPolicy: "void-before-capture", refundPolicy: "original-rail", disputePolicy: "provider-dispute",
  indexPolicy: null, consentScope: "single-payment", executionModel: "pay-after-condition",
};

describe("DSL validator (allowlist, no eval)", () => {
  it("accepts valid terms, rejects share mismatch + eval injection", () => {
    expect(validateTerms(base).ok).toBe(true);
    expect(validateTerms({ ...base, beneficiaries: [{ party: "m", shareBps: 5000, destination: "x" }] }).errors.join()).toMatch(/bps/);
    const evil = { ...base, conditions: [{ type: "exec(require('fs'))" } as never] };
    expect(validateTerms(evil).ok).toBe(false);
  });
  it("sends inconsistent caps to REVIEW (error surfaced)", () => {
    const t = { ...base, indexPolicy: { series: "HICP", geography: "BG", basePeriod: "2024", cutoff: "2026-01-01", revisionPolicy: "frozen-vintage", frequency: "monthly", floor: null, perAdjustmentCapBps: 500, cumulativeCapBps: 100, ceilingMinor: null, rounding: "HALF_UP_MINOR" as const } };
    expect(validateTerms(t).ok).toBe(false);
  });
  it("rejects unapproved escrow product", () => {
    expect(validateTerms({ ...base, executionModel: "approved-payout-product" }).ok).toBe(false);
  });
});

describe("index formula + caps + deflation floor", () => {
  const policy = { series: "HICP", geography: "BG", basePeriod: "2024", cutoff: "2026-01-01", revisionPolicy: "frozen-vintage", frequency: "monthly", floor: "NO_DEFLECTION_BELOW_BASE", perAdjustmentCapBps: 200, cumulativeCapBps: 500, ceilingMinor: null, rounding: "HALF_UP_MINOR" as const };
  it("raw = base * eligible / base on LEVELS", () => {
    const r = indexedAmountMinor({ baseAmountMinor: 10000n, baseIndex: 100, eligibleIndex: 105, policy: { ...policy, perAdjustmentCapBps: null, cumulativeCapBps: null, floor: null } });
    expect(r.rawMinor).toBe(10500n);
  });
  it("caps + floor + ceiling enforced", () => {
    const capped = indexedAmountMinor({ baseAmountMinor: 10000n, baseIndex: 100, eligibleIndex: 120, policy });
    expect(capped.cappedMinor).toBe(10200n); // per-adjustment 2%
    const defl = indexedAmountMinor({ baseAmountMinor: 10000n, baseIndex: 100, eligibleIndex: 90, policy });
    expect(defl.cappedMinor).toBe(10000n); // floor
  });
  it("rejects YoY-rate misuse (zero/negative level)", () => {
    expect(() => indexedAmountMinor({ baseAmountMinor: 10000n, baseIndex: 0, eligibleIndex: 2, policy })).toThrow();
  });
});

describe("condition evaluation", () => {
  it("merchant assertion alone insufficient for milestone", () => {
    const t = { ...base, conditions: [{ type: "milestone", milestoneId: "delivery-1", evidenceRequired: true } as const] };
    const r = evaluateConditions(t, [{ source: "merchant-assertion", eventId: "1", timestamp: "2026-01-01T00:00:00Z", expiry: "2030-01-01T00:00:00Z", payload: { milestoneId: "delivery-1" }, nonce: "n" }], "2027-01-01T00:00:00Z", {});
    expect(r.satisfied).toBe(false);
  });
  it("expired evidence rejected (replay protection)", () => {
    const t = { ...base, conditions: [{ type: "externalEvent", source: "carrier", eventKey: "delivered", mustMatch: { parcel: "p1" } } as const] };
    const r = evaluateConditions(t, [{ source: "carrier", eventId: "e1", timestamp: "2026-01-01T00:00:00Z", expiry: "2026-01-02T00:00:00Z", payload: { parcel: "p1" }, nonce: "n" }], "2027-01-01T00:00:00Z", {});
    expect(r.satisfied).toBe(false);
  });
});

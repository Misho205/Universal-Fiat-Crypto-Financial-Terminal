import { describe, it, expect } from "vitest";
import {
  DISPUTE_CATEGORIES,
  DISPUTE_CATEGORY_SLA_DAYS,
  DISPUTE_ALLOWED_MIME,
  disputeStatusHint,
  isValidCategory,
} from "../src/disputes";

describe("disputes", () => {
  it("covers the five required categories with SLA deadlines", () => {
    expect([...DISPUTE_CATEGORIES]).toEqual([
      "unauthorized_payment",
      "incorrect_record",
      "disputed_fee",
      "account_restriction",
      "contractual",
    ]);
    for (const c of DISPUTE_CATEGORIES) {
      expect(DISPUTE_CATEGORY_SLA_DAYS[c]).toBeGreaterThan(0);
    }
    expect(DISPUTE_CATEGORY_SLA_DAYS.account_restriction).toBeLessThanOrEqual(7);
  });

  it("validates categories and explains states accessibly", () => {
    expect(isValidCategory("unauthorized_payment")).toBe(true);
    expect(isValidCategory("free-money")).toBe(false);
    for (const s of ["submitted", "under_review", "escalated", "decided", "remediation", "closed"]) {
      expect(disputeStatusHint(s).length).toBeGreaterThan(5);
    }
  });

  it("allowlist is document/image evidence only", () => {
    expect(DISPUTE_ALLOWED_MIME).toContain("application/pdf");
    expect(DISPUTE_ALLOWED_MIME).not.toContain("application/x-msdownload");
  });
});

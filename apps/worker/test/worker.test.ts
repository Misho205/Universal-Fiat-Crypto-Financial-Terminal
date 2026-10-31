import { describe, it, expect } from "vitest";
import { nextStateAfterTimeout } from "../src/workflows.js";
import { adapterFor } from "../src/activities.js";

describe("worker safety", () => {
  it("timeout with ambiguous query -> UNKNOWN (no unsafe failover)", () => {
    expect(nextStateAfterTimeout("UNKNOWN")).toBe("UNKNOWN");
    expect(nextStateAfterTimeout("AUTHORIZED")).toBe("AUTHORIZED");
  });
  it("adapters resolve per route; stripe without key blocks", async () => {
    const a = adapterFor("stripe:card:EUR");
    const r = await a.authorize({ tenantId: "t", instructionId: "x", idempotencyKey: "k", asset: "fiat:EUR", amountMinor: "1", nowIso: "" });
    expect(r.ok).toBe(false);
  });
});

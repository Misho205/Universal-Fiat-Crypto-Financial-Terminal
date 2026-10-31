import { describe, it, expect } from "vitest";
import { formatMinor, formatWei } from "../src/lib/format";
import { stateTone } from "../src/tokens";
import { dict } from "../src/i18n";

describe("design tokens + formatting (WCAG text-first, never color alone)", () => {
  it("money formats minor units per currency", () => {
    expect(formatMinor("2599", "EUR", "en-GB")).toMatch(/25\.99/);
    expect(formatMinor("2599", "EUR", "en-GB")).toMatch(/EUR|€/);
    expect(formatMinor("100", "HUF", "en-GB")).toMatch(/100/); // zero-exponent
  });
  it("wei formats to ETH with label", () => {
    expect(formatWei("100000000000000000")).toMatch(/0\.1/);
    expect(formatWei("100000000000000000")).toMatch(/ETH/);
  });
  it("every known state maps to a tone (no unmapped silent states)", () => {
    for (const s of ["succeeded", "pending", "failed", "confirmed", "expired", "canceled", "disputed", "draft", "unknown"]) {
      expect(["ok", "warn", "danger", "info", "muted"]).toContain(stateTone(s));
    }
    expect(stateTone("pending")).toBe("warn");
    expect(stateTone("succeeded")).toBe("ok");
  });
  it("i18n parity incl. new workspace keys", () => {
    expect(Object.keys(dict.en).sort()).toEqual(Object.keys(dict.bg).sort());
  });
});

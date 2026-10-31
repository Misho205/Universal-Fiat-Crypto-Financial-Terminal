import { describe, it, expect } from "vitest";
import { dict } from "../src/i18n";

describe("i18n", () => {
  it("bg/en keys parity (UI must support both)", () => {
    expect(Object.keys(dict.en).sort()).toEqual(Object.keys(dict.bg).sort());
    expect(dict.bg.receipt).toMatch(/НЕ е фискален бон/);
    expect(dict.en.receipt).toMatch(/NOT a fiscal receipt/);
  });
});

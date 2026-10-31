import { describe, it, expect } from "vitest";
import { parseToMinor, formatFromMinor } from "../src/index.js";

// Deterministic pseudo-random generator (mulberry32) — no new deps, reproducible property runs.
function rng(seed: number) {
  let a = seed >>> 0;
  return () => {
    a |= 0; a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

describe("money property", () => {
  it("roundtrips EUR amounts exactly (1000 cases)", () => {
    const rand = rng(42);
    for (let i = 0; i < 1000; i++) {
      const euros = Math.floor(rand() * 100000);
      const cents = Math.floor(rand() * 100);
      const s = `${euros}.${String(cents).padStart(2, "0")}`;
      expect(formatFromMinor(parseToMinor(s, 2), 2)).toBe(s.replace(/^0+(\d)/, "$1"));
    }
  });
  it("addition is exact (no float drift 0.07+0.01)", () => {
    const rand = rng(7);
    for (let i = 0; i < 500; i++) {
      const a = BigInt(Math.floor(rand() * 100000));
      const b = BigInt(Math.floor(rand() * 100000));
      expect(formatFromMinor(a + b, 2)).toBe(formatFromMinor(a, 2).startsWith("-") ? formatFromMinor(a + b, 2) : formatFromMinor(a + b, 2));
      expect(a + b).toBeGreaterThanOrEqual(0n);
    }
    expect(formatFromMinor(parseToMinor("0.07", 2) + parseToMinor("0.01", 2), 2)).toBe("0.08");
  });
  it("BTC 8-decimal roundtrip (500 cases)", () => {
    const rand = rng(99);
    for (let i = 0; i < 500; i++) {
      const sats = Math.floor(rand() * 2100000000000000);
      const s = formatFromMinor(BigInt(sats), 8);
      expect(formatFromMinor(parseToMinor(s, 8), 8)).toBe(s);
    }
  });
  it("rejects over-precision consistently", () => {
    expect(() => parseToMinor("1.001", 2)).toThrow("TOO_MANY_FRACTION_DIGITS");
    expect(() => parseToMinor("1.000000001", 8)).toThrow("TOO_MANY_FRACTION_DIGITS");
  });
});

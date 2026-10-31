// Property-style money invariants (no deps, runs with `node --test tests/property/`).
// Mirrors packages/domain/test/property.test.ts but dependency-free for CI without build.
import { describe, it } from "node:test";
import assert from "node:assert";

function parseToMinor(amount, exponent) {
  if (!/^-?\d+(\.\d+)?$/.test(amount)) throw new Error("INVALID_AMOUNT");
  const [i, f = ""] = amount.split(".");
  if (f.length > exponent) throw new Error("TOO_MANY_FRACTION_DIGITS");
  return BigInt((i + f.padEnd(exponent, "0")).replace(/^(-?)0+(\d)/, "$1$2") || "0");
}
function formatFromMinor(minor, exponent) {
  const neg = minor < 0n;
  const abs = neg ? -minor : minor;
  const s = abs.toString().padStart(exponent + 1, "0");
  return `${neg ? "-" : ""}${s.slice(0, s.length - exponent)}${exponent > 0 ? "." + s.slice(s.length - exponent) : ""}`;
}
function mulberry(seed) {
  let a = seed >>> 0;
  return () => {
    a |= 0; a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

describe("property: money roundtrip", () => {
  it("EUR roundtrip 1000 cases", () => {
    const rand = mulberry(42);
    for (let i = 0; i < 1000; i++) {
      const s = `${Math.floor(rand() * 100000)}.${String(Math.floor(rand() * 100)).padStart(2, "0")}`;
      assert.strictEqual(formatFromMinor(parseToMinor(s, 2), 2), s.replace(/^0+(\d)/, "$1"));
    }
  });
  it("0.07+0.01 is exactly 0.08", () => {
    assert.strictEqual(formatFromMinor(parseToMinor("0.07", 2) + parseToMinor("0.01", 2), 2), "0.08");
  });
  it("rejects over-precision", () => {
    assert.throws(() => parseToMinor("1.001", 2));
  });
});

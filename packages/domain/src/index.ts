// Money: exact-decimal arithmetic. Amounts cross API boundary as decimal strings;
// internally as integer minor/atomic units (bigint). No float for money.
export type AssetClass = "fiat" | "crypto";

export interface FiatAsset {
  kind: "fiat";
  code: string; // ISO 4217, e.g. EUR
  exponent: number; // minor units, EUR=2
  jurisdictions: string[]; // e.g. ["BG","EU"]
  limits: { maxPerTxMinor: string; maxPerDayMinor: string };
}

export interface CryptoAsset {
  kind: "crypto";
  symbol: string; // display only, never identity
  chainId: string; // e.g. "bitcoin-regtest"
  native: boolean;
  tokenContract: string | null; // exact contract for tokens; null for native
  decimals: number;
  addressFormat: string; // e.g. "bech32"
  memoRequired: boolean;
  gasAsset: string;
  confirmationsRequired: number;
}

export type Asset = FiatAsset | CryptoAsset;

export function assetId(a: Asset): string {
  return a.kind === "fiat"
    ? `fiat:${a.code}`
    : `crypto:${a.chainId}:${a.native ? "native" : a.tokenContract}`;
}

/** Parse "123.45" to minor units given exponent. Throws on invalid/unsafe input. */
export function parseToMinor(amount: string, exponent: number): bigint {
  if (!/^-?\d+(\.\d+)?$/.test(amount)) throw new Error("INVALID_AMOUNT");
  const [i, f = ""] = amount.split(".");
  if (f.length > exponent) throw new Error("TOO_MANY_FRACTION_DIGITS");
  const padded = (i + f.padEnd(exponent, "0")).replace(/^(-?)0+(\d)/, "$1$2");
  const normalized = padded === "" || padded === "-" ? "0" : padded;
  return BigInt(normalized);
}

export function formatFromMinor(minor: bigint, exponent: number): string {
  const neg = minor < 0n;
  const abs = neg ? -minor : minor;
  const s = abs.toString().padStart(exponent + 1, "0");
  const int = s.slice(0, s.length - exponent);
  const frac = s.slice(s.length - exponent);
  return `${neg ? "-" : ""}${int}${exponent > 0 ? "." + frac : ""}`;
}

export function addMinor(a: bigint, b: bigint): bigint {
  return a + b;
}

/** Capability matrix entry. */
export type Capability =
  | "collect" | "authorize" | "capture" | "cancel" | "refund"
  | "transfer" | "payout" | "recurring" | "conditionalRelease" | "exchange";

export interface MethodRoute {
  id: string; // e.g. "mock:card:EUR" | "stripe:card:EUR" | "btcpay:btc:regtest"
  paymentAsset: string; // assetId
  settlementAsset: string;
  denominationAssets: string[];
  capabilities: Record<Capability, "SUPPORTED" | "UNSUPPORTED_CAPABILITY">;
  status: "MOCK_OK" | "SANDBOX_OK" | "SANDBOX_BLOCKED" | "LIVE_BLOCKED" | "INTERFACE_ONLY";
  needsConversionRoute: boolean;
}

export const CAPABILITIES: Capability[] = ["collect","authorize","capture","cancel","refund","transfer","payout","recurring","conditionalRelease","exchange"];

export function unsupported(): Record<Capability, "SUPPORTED" | "UNSUPPORTED_CAPABILITY"> {
  return Object.fromEntries(CAPABILITIES.map((c) => [c, "UNSUPPORTED_CAPABILITY"])) as Record<Capability, "SUPPORTED" | "UNSUPPORTED_CAPABILITY">;
}

export function eligibleMethods(routes: MethodRoute[], opts: { denomination: string; paymentAsset?: string }): MethodRoute[] {
  return routes.filter((r) => r.denominationAssets.includes(opts.denomination) &&
    (!opts.paymentAsset || r.paymentAsset === opts.paymentAsset) &&
    (r.status === "MOCK_OK" || r.status === "SANDBOX_OK") &&
    (!r.needsConversionRoute || r.id.includes("approved-route")));
}

// Instruction state machine
export type InstructionState = "DRAFT" | "PENDING" | "AUTHORIZED" | "SETTLED" | "CANCELLED" | "FAILED" | "UNKNOWN" | "REFUNDED" | "DISPUTED";
const TRANSITIONS: Record<InstructionState, InstructionState[]> = {
  DRAFT: ["PENDING", "CANCELLED"],
  PENDING: ["AUTHORIZED", "FAILED", "UNKNOWN", "CANCELLED"],
  AUTHORIZED: ["SETTLED", "FAILED", "UNKNOWN", "CANCELLED"],
  UNKNOWN: ["AUTHORIZED", "SETTLED", "FAILED", "CANCELLED"],
  SETTLED: ["REFUNDED", "DISPUTED"],
  FAILED: [],
  CANCELLED: [],
  REFUNDED: [],
  DISPUTED: ["REFUNDED", "SETTLED"],
};
export function canTransition(from: InstructionState, to: InstructionState): boolean {
  return TRANSITIONS[from].includes(to);
}

// Stable idempotency key: tenant + operation + sha256(content)
import { createHash } from "node:crypto";
export function idempotencyKey(tenantId: string, operation: string, content: unknown): string {
  const h = createHash("sha256").update(JSON.stringify(content)).digest("hex");
  return `${tenantId}:${operation}:${h}`;
}

import { createHash, createHmac, timingSafeEqual } from "node:crypto";
import { HttpException } from "@nestjs/common";

// ---- In-memory multi-tenant store (Prisma schema is authoritative for SQL; this enables M1 without DB) ----
export interface Order { id: string; tenantId: string; storeId: string; denomination: string; totalMinor: string; status: string; }
export interface Instruction { id: string; tenantId: string; orderId: string; agreementId: string; methodRoute: string; amountMinor: string; state: string; deviceId: string; idempotencyKey: string; providerRef?: string; }

export const db = {
  orders: new Map<string, Order>(),
  ordersByIdem: new Map<string, Order>(),
  instructions: new Map<string, Instruction>(),
  instrByIdem: new Map<string, Instruction>(),
  devices: new Map<string, { id: string; tenantId: string; revoked: boolean }>(),
  consents: new Map<string, boolean>(),
  dayTotals: new Map<string, bigint>(),
  processedEvents: new Set<string>(),
  audit: [] as unknown[],
};

export function tenantScope(tenantId: string, entityTenant: string): void {
  if (tenantId !== entityTenant) throw new HttpException("TENANT_ISOLATION_VIOLATION", 403);
}

// Simple async mutex per scope for atomic reservations (concurrent-worker safe in single process; DB constraints in SQL).
const locks = new Map<string, Promise<void>>();
export async function withScopeLock<T>(scope: string, fn: () => Promise<T> | T): Promise<T> {
  const prev = locks.get(scope) ?? Promise.resolve();
  let release!: () => void;
  const cur = new Promise<void>((r) => (release = r));
  locks.set(scope, prev.then(() => cur));
  await prev;
  try {
    return await fn();
  } finally {
    release();
    if (locks.get(scope) === cur) locks.delete(scope);
  }
}

// ---- Checkout tokens: short-lived HMAC-signed, tenant+order+version+amount bound ----
const SECRET = process.env.JWT_DEV_SECRET ?? "dev-only-insecure-secret";
export interface CheckoutClaims { tenantId: string; orderId: string; agreementVersion: number; amountMinor: string; exp: number; }
function b64url(b: Buffer): string { return b.toString("base64url"); }
export function signCheckout(c: CheckoutClaims): string {
  const body = b64url(Buffer.from(JSON.stringify(c)));
  const sig = createHmac("sha256", SECRET).update(body).digest("base64url");
  return `${body}.${sig}`;
}
export function verifyCheckout(token: string, nowSec = Math.floor(Date.now() / 1000)): CheckoutClaims {
  const [body, sig] = token.split(".");
  if (!body || !sig) throw Object.assign(new Error("TAMPERED_QR"), { status: 410 });
  const expect = createHmac("sha256", SECRET).update(body).digest();
  const got = Buffer.from(sig, "base64url");
  if (expect.length !== got.length || !timingSafeEqual(expect, got)) throw Object.assign(new Error("TAMPERED_QR"), { status: 410 });
  const claims = JSON.parse(Buffer.from(body, "base64url").toString()) as CheckoutClaims;
  if (claims.exp < nowSec) throw Object.assign(new Error("CHECKOUT_EXPIRED"), { status: 410 });
  return claims;
}
export function fingerprint(obj: unknown): string { return createHash("sha256").update(JSON.stringify(obj)).digest("hex"); }

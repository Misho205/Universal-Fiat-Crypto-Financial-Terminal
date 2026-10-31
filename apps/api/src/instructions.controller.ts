import { Body, Controller, Get, Headers, HttpException, Param, Post } from "@nestjs/common";
import { db, tenantScope, withScopeLock } from "./store";

let iSeq = 1;

function policyCheck(amountMinor: bigint, deviceRevoked: boolean, consent: boolean): "ALLOW" | "REVIEW" | "DENY" {
  if (deviceRevoked) return "DENY";
  if (!consent) return "DENY";
  if (amountMinor <= 50000n) return "ALLOW";
  if (amountMinor <= 100000n) return "REVIEW";
  return "DENY";
}

@Controller("v1")
export class InstructionsController {
  @Post("instructions")
  async create(
    @Headers("x-tenant-id") tenant: string,
    @Headers("idempotency-key") key: string,
    @Body() b: { orderId: string; agreementId: string; methodRoute: string; amountMinor: string; deviceId: string },
  ) {
    if (!tenant || !key) throw new HttpException("missing tenant/idempotency", 400);
    const o = db.orders.get(b.orderId);
    if (!o) throw new HttpException("order not found", 404);
    tenantScope(tenant, o.tenantId);
    const scoped = `${tenant}:${key}:${JSON.stringify(b)}`;
    const existing = db.instrByIdem.get(scoped);
    if (existing) return existing;
    for (const [k] of db.instrByIdem) if (k.startsWith(`${tenant}:${key}:`) && k !== scoped) throw new HttpException("IDEMPOTENCY_CONFLICT", 409);

    const dev = db.devices.get(b.deviceId);
    const revoked = dev ? dev.revoked : false;
    if (dev) tenantScope(tenant, dev.tenantId);
    const consent = db.consents.get(`${tenant}:${b.agreementId}:customer`) ?? true; // dev default true unless explicitly revoked
    const decision = policyCheck(BigInt(b.amountMinor), revoked, consent);
    if (decision === "DENY") throw new HttpException({ decision, reason: "FAIL_CLOSED" }, 403);

    // Atomic reservation + day limit (EUR 200000 minor/day demo).
    const day = new Date().toISOString().slice(0, 10);
    const scope = `${tenant}:${day}:fiat:EUR`;
    await withScopeLock(scope, () => {
      const total = db.dayTotals.get(scope) ?? 0n;
      if (total + BigInt(b.amountMinor) > 200000n) throw new HttpException("DAY_LIMIT", 429);
      db.dayTotals.set(scope, total + BigInt(b.amountMinor));
    });

    const scenario = b.methodRoute.includes("mock") ? (key.endsWith("timeout") ? "UNKNOWN" : "AUTHORIZED") : "PENDING";
    const ins = { id: `ins-${iSeq++}`, tenantId: tenant, orderId: b.orderId, agreementId: b.agreementId, methodRoute: b.methodRoute, amountMinor: b.amountMinor, state: decision === "REVIEW" ? "PENDING" : scenario, deviceId: b.deviceId, idempotencyKey: scoped, providerRef: `mock_ins-${iSeq}` };
    db.instructions.set(ins.id, ins);
    db.instrByIdem.set(scoped, ins);
    return { ...ins, policyDecision: decision };
  }

  @Get("instructions/:id")
  get(@Headers("x-tenant-id") tenant: string, @Param("id") id: string) {
    const ins = db.instructions.get(id);
    if (!ins) throw new HttpException("not found", 404);
    tenantScope(tenant, ins.tenantId);
    return ins;
  }

  @Post("instructions/:id/refund")
  refund(@Headers("x-tenant-id") tenant: string, @Param("id") id: string, @Body() b: { destination: string; approver: string }) {
    const ins = db.instructions.get(id);
    if (!ins) throw new HttpException("not found", 404);
    tenantScope(tenant, ins.tenantId);
    if (!b?.approver || !b?.destination) throw new HttpException("refund requires verified destination + independent approver", 422);
    if (ins.state !== "SETTLED") throw new HttpException("only SETTLED can be refunded (crypto refund = new transfer)", 409);
    ins.state = "REFUNDED";
    return { refunded: true, instructionId: id, destination: b.destination };
  }
}

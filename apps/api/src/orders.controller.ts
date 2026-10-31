import { Body, Controller, Get, Headers, HttpException, Param, Post } from "@nestjs/common";
import { db, tenantScope, withScopeLock } from "./store";

let seq = 1;

@Controller("v1/orders")
export class OrdersController {
  @Post()
  create(@Headers("x-tenant-id") tenant: string, @Headers("idempotency-key") key: string, @Body() body: { storeId: string; denomination: string; totalMinor: string }) {
    if (!tenant || !key) throw new HttpException("missing tenant/idempotency", 400);
    if (!/^\d+$/.test(body?.totalMinor ?? "")) throw new HttpException("INVALID_AMOUNT", 422);
    const scoped = `${tenant}:${key}:${JSON.stringify(body)}`;
    const existing = db.ordersByIdem.get(scoped);
    if (existing) return existing;
    // conflicting reuse: same key, different payload
    for (const [k, v] of db.ordersByIdem) {
      if (k.startsWith(`${tenant}:${key}:`) && k !== scoped) throw new HttpException("IDEMPOTENCY_CONFLICT", 409);
    }
    const order = { id: `ord-${seq++}`, tenantId: tenant, storeId: body.storeId, denomination: body.denomination, totalMinor: body.totalMinor, status: "DRAFT" };
    db.orders.set(order.id, order);
    db.ordersByIdem.set(scoped, order);
    db.audit.push({ tenant, action: "order.create", entity: order.id });
    return order;
  }

  @Get(":id")
  get(@Headers("x-tenant-id") tenant: string, @Param("id") id: string) {
    const o = db.orders.get(id);
    if (!o) throw new HttpException("not found", 404);
    tenantScope(tenant, o.tenantId);
    return o;
  }
}

@Controller("v1/devices")
export class DevicesController {
  @Post("enroll")
  enroll(@Headers("x-tenant-id") tenant: string, @Body() body: { label: string; token: string }) {
    // Short-lived enrollment token "enroll-<tenant>" accepted in dev; prod: OIDC-issued one-time token.
    if (body?.token !== `enroll-${tenant}`) throw new HttpException("INVALID_ENROLLMENT_TOKEN", 401);
    const id = `dev-${Math.random().toString(36).slice(2, 8)}`;
    db.devices.set(id, { id, tenantId: tenant, revoked: false });
    return { deviceId: id, credential: `scoped-${id}` };
  }

  @Post(":id/revoke")
  revoke(@Headers("x-tenant-id") tenant: string, @Param("id") id: string) {
    const d = db.devices.get(id);
    if (!d) throw new HttpException("not found", 404);
    tenantScope(tenant, d.tenantId);
    d.revoked = true;
    return { revoked: true };
  }
}

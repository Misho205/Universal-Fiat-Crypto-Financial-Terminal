import { describe, it, expect, beforeAll } from "vitest";
import request from "supertest";
import type { INestApplication } from "@nestjs/common";
import { createApp } from "../src/main";
import { db, signCheckout, verifyCheckout } from "../src/store";

let app: INestApplication;
const T = "tenant-1";

beforeAll(async () => {
  app = await createApp();
  await app.init();
  db.devices.set("dev-1", { id: "dev-1", tenantId: T, revoked: false });
});

describe("tenancy + idempotency + devices", () => {
  it("creates order idempotently; conflicting reuse -> 409", async () => {
    const s = request(app.getHttpServer());
    const body = { storeId: "s1", denomination: "fiat:EUR", totalMinor: "10000" };
    const r1 = await s.post("/v1/orders").set("X-Tenant-Id", T).set("Idempotency-Key", "k1").send(body).expect(201);
    const r2 = await s.post("/v1/orders").set("X-Tenant-Id", T).set("Idempotency-Key", "k1").send(body).expect(201);
    expect(r1.body.id).toBe(r2.body.id);
    await s.post("/v1/orders").set("X-Tenant-Id", T).set("Idempotency-Key", "k1").send({ ...body, totalMinor: "999" }).expect(409);
  });
  it("enforces tenant isolation", async () => {
    const s = request(app.getHttpServer());
    const r = await s.post("/v1/orders").set("X-Tenant-Id", T).set("Idempotency-Key", "iso1").send({ storeId: "s1", denomination: "fiat:EUR", totalMinor: "100" }).expect(201);
    await s.get(`/v1/orders/${r.body.id}`).set("X-Tenant-Id", "other-tenant").expect(403);
  });
  it("denies revoked device (fail closed)", async () => {
    const s = request(app.getHttpServer());
    db.devices.set("dev-rev", { id: "dev-rev", tenantId: T, revoked: true });
    const o = await s.post("/v1/orders").set("X-Tenant-Id", T).set("Idempotency-Key", "rd1").send({ storeId: "s1", denomination: "fiat:EUR", totalMinor: "100" }).expect(201);
    await s.post("/v1/instructions").set("X-Tenant-Id", T).set("Idempotency-Key", "ri1").send({ orderId: o.body.id, agreementId: "ag-x", methodRoute: "mock:card:EUR", amountMinor: "100", deviceId: "dev-rev" }).expect(403);
  });
  it("webhook dedupe + tampered QR rejected", async () => {
    const s = request(app.getHttpServer());
    await s.post("/v1/webhooks/stripe").set("stripe-signature", "sig").send({ id: "evt_1" }).expect(201);
    const dup = await s.post("/v1/webhooks/stripe").set("stripe-signature", "sig").send({ id: "evt_1" }).expect(201);
    expect(dup.body.deduped).toBe(true);
    const good = signCheckout({ tenantId: T, orderId: "ord-1", agreementVersion: 1, amountMinor: "100", exp: Math.floor(Date.now() / 1000) + 60 });
    expect(verifyCheckout(good).orderId).toBe("ord-1");
    await s.get(`/v1/checkout/${good}tampered`).expect(410);
  });
  it("concurrent reservations respect day limit", async () => {
    const s = request(app.getHttpServer());
    const o = await s.post("/v1/orders").set("X-Tenant-Id", "tenant-cap").set("Idempotency-Key", "cap-ord").send({ storeId: "s1", denomination: "fiat:EUR", totalMinor: "199000" }).expect(201);
    db.devices.set("dev-cap", { id: "dev-cap", tenantId: "tenant-cap", revoked: false });
    const mk = (k: string, amt: string) => s.post("/v1/instructions").set("X-Tenant-Id", "tenant-cap").set("Idempotency-Key", k).send({ orderId: o.body.id, agreementId: "ag-x", methodRoute: "mock:card:EUR", amountMinor: amt, deviceId: "dev-cap" });
    // 5 x 50000 = 250000 > 200000 day limit; at least one must lose the race with 429
    const res = await Promise.all([mk("ck1", "50000"), mk("ck2", "50000"), mk("ck3", "50000"), mk("ck4", "50000"), mk("ck5", "50000")]);
    const statuses = res.map((r) => r.status).sort();
    expect(statuses).toContain(429); // one must lose the race
    expect(statuses).toContain(201);
  });
});

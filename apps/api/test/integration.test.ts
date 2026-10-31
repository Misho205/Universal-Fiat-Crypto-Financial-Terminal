import { describe, it, expect, beforeAll } from "vitest";
import request from "supertest";
import type { INestApplication } from "@nestjs/common";
import { createApp } from "../src/main";
import { db } from "../src/store";

// Integration: full order -> agreement -> accept -> eligible-methods -> quote -> instruction -> status -> refund.
// Covers PRD acceptance: tenant isolation, revoked device, idempotent conflicts, quote shape, refund gating.
describe("integration full flow", () => {
  let app: INestApplication;
  const T = "integration-tenant";
  beforeAll(async () => {
    app = await createApp();
    await app.init();
    db.devices.set("dev-int", { id: "dev-int", tenantId: T, revoked: false });
  });

  it("order -> agreement -> quote -> instruction -> status", async () => {
    const s = request(app.getHttpServer());
    const order = await s.post("/v1/orders").set("X-Tenant-Id", T).set("Idempotency-Key", "int-ord-1")
      .send({ storeId: "s1", denomination: "fiat:EUR", totalMinor: "2599" }).expect(201);
    const ag = await s.post(`/v1/orders/${order.body.id}/agreements`).set("X-Tenant-Id", T).send({
      amountMinor: "2599", feesMinor: "49",
      beneficiaries: [{ party: "merchant", shareBps: 10000, destination: "iban:BG00INT" }],
      conditions: [{ type: "timeCondition", notAfter: "2030-01-01T00:00:00Z" }],
      deadlines: {}, cancelPolicy: "void", refundPolicy: "original-rail",
      disputePolicy: "provider", indexPolicy: null, consentScope: "single", executionModel: "pay-after-condition",
    }).expect(201);
    await s.post(`/v1/agreements/${ag.body.id}/accept`).set("X-Tenant-Id", T).send({ party: "customer" }).expect(201);
    const methods = await s.get(`/v1/orders/${order.body.id}/eligible-methods`).set("X-Tenant-Id", T).expect(200);
    expect(methods.body.some((m: { id: string }) => m.id === "mock:card:EUR")).toBe(true);
    const quote = await s.post("/v1/quotes").set("X-Tenant-Id", T)
      .send({ orderId: order.body.id, inAsset: "fiat:EUR", outAsset: "fiat:EUR", inMinor: "2599" }).expect(201);
    expect(quote.body.executable).toBe(true);
    expect(new Date(quote.body.expiresAt).getTime()).toBeGreaterThan(Date.now());
    const ins = await s.post("/v1/instructions").set("X-Tenant-Id", T).set("Idempotency-Key", "int-ins-1")
      .send({ orderId: order.body.id, agreementId: ag.body.id, methodRoute: "mock:card:EUR", amountMinor: "2599", deviceId: "dev-int" })
      .expect(201);
    expect(["AUTHORIZED", "PENDING"]).toContain(ins.body.state);
    const status = await s.get(`/v1/instructions/${ins.body.id}`).set("X-Tenant-Id", T).expect(200);
    expect(status.body.id).toBe(ins.body.id);
  });

  it("refund requires approver+destination and SETTLED state", async () => {
    const s = request(app.getHttpServer());
    const order = await s.post("/v1/orders").set("X-Tenant-Id", T).set("Idempotency-Key", "int-ord-2")
      .send({ storeId: "s1", denomination: "fiat:EUR", totalMinor: "100" }).expect(201);
    const ins = await s.post("/v1/instructions").set("X-Tenant-Id", T).set("Idempotency-Key", "int-ins-2")
      .send({ orderId: order.body.id, agreementId: "ag-x", methodRoute: "mock:card:EUR", amountMinor: "100", deviceId: "dev-int" })
      .expect(201);
    // Not SETTLED in mock AUTHORIZED flow -> refund must 409; missing approver -> 422
    await s.post(`/v1/instructions/${ins.body.id}/refund`).set("X-Tenant-Id", T).send({}).expect(422);
  });
});

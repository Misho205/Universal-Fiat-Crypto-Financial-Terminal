import { Body, Controller, Get, Headers, HttpException, Post } from "@nestjs/common";
import { db } from "./store";

@Controller("v1")
export class MiscController {
  @Post("webhooks/stripe")
  stripe(@Body() body: unknown, @Headers("stripe-signature") sig: string) {
    if (!sig) throw new HttpException("missing signature", 401);
    const ev = body as { id?: string };
    if (!ev?.id) throw new HttpException("bad event", 422);
    const k = `stripe:${ev.id}`;
    if (db.processedEvents.has(k)) return { deduped: true };
    db.processedEvents.add(k);
    return { received: true };
  }

  @Post("webhooks/btcpay")
  btcpay(@Body() body: unknown, @Headers("btcpay-sig") sig: string) {
    if (!sig) throw new HttpException("missing signature", 401);
    const ev = body as { invoiceId?: string };
    if (!ev?.invoiceId) throw new HttpException("bad event", 422);
    const k = `btcpay:${ev.invoiceId}`;
    if (db.processedEvents.has(k)) return { deduped: true };
    db.processedEvents.add(k);
    return { received: true };
  }

  @Post("reconcile/runs")
  reconcile() {
    // Crash recovery: list UNKNOWN instructions needing query-original.
    const unknown = [...db.instructions.values()].filter((i) => i.state === "UNKNOWN").map((i) => i.id);
    return { started: true, unknownToReconcile: unknown };
  }

  @Get("health")
  health() {
    return { ok: true, liveMode: process.env.LIVE_MODE === "true" ? "ON-BLOCKED" : "OFF" };
  }
}

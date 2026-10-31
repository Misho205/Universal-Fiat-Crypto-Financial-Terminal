import { Body, Controller, Headers, HttpException, Param, Post } from "@nestjs/common";
import { db, tenantScope } from "./store";

let aSeq = 1;

function validateTermsShallow(terms: unknown): string[] {
  const t = terms as Record<string, unknown>;
  const errors: string[] = [];
  if (typeof t?.["amountMinor"] !== "string" || !/^\d+$/.test(t["amountMinor"] as string)) errors.push("amount must be integer minor units");
  const conds = (t?.["conditions"] ?? []) as { type: string }[];
  const allowed = new Set(["timeCondition", "externalEvent", "partyApproval", "approvalThreshold", "milestone", "disputeWindow"]);
  for (const c of conds) if (!allowed.has(c.type)) errors.push(`disallowed condition: ${c.type}`);
  if ((t?.["executionModel"] as string) === "approved-payout-product") errors.push("REVIEW: approved-payout-product needs licensed escrow product");
  return errors;
}

@Controller("v1")
export class AgreementsController {
  @Post("orders/:id/agreements")
  create(@Headers("x-tenant-id") tenant: string, @Param("id") orderId: string, @Body() terms: unknown) {
    const o = db.orders.get(orderId);
    if (!o) throw new HttpException("order not found", 404);
    tenantScope(tenant, o.tenantId);
    const errors = validateTermsShallow(terms);
    if (errors.length) throw new HttpException({ errors }, 422);
    const ag = { id: `ag-${aSeq++}`, version: 1, terms };
    (db as unknown as Record<string, Map<string, unknown>>).agreements ??= new Map();
    (db as unknown as Record<string, Map<string, unknown>>).agreements.set(ag.id, { ...ag, tenantId: tenant, orderId });
    return ag;
  }

  @Post("agreements/:id/accept")
  accept(@Headers("x-tenant-id") tenant: string, @Param("id") id: string, @Body() body: { party: string }) {
    const m = (db as unknown as Record<string, Map<string, { tenantId: string }>>).agreements?.get(id);
    if (!m) throw new HttpException("agreement not found", 404);
    tenantScope(tenant, m.tenantId);
    db.consents.set(`${tenant}:${id}:${body.party}`, true);
    return { accepted: true, agreementId: id, party: body.party };
  }

  @Post("evidence")
  evidence(@Headers("x-tenant-id") tenant: string, @Body() ev: { provider: string; eventId: string; expiry: string; payload?: unknown }) {
    if (!ev?.eventId || !ev?.provider) throw new HttpException("invalid evidence", 422);
    const k = `${ev.provider}:${ev.eventId}`;
    if (db.processedEvents.has(k)) return { deduped: true }; // duplicate webhook safe
    if (ev.expiry && ev.expiry < new Date().toISOString()) throw new HttpException("STALE_EVENT", 410);
    db.processedEvents.add(k);
    return { stored: true };
  }
}

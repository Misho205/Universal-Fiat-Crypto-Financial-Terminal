import { Body, Controller, Get, Headers, HttpException, Param, Post } from "@nestjs/common";
import { db, tenantScope, signCheckout, verifyCheckout } from "./store";

const ROUTES = [
  { id: "mock:card:EUR", paymentAsset: "fiat:EUR", settlementAsset: "fiat:EUR", denominationAssets: ["fiat:EUR"], status: "MOCK_OK", needsConversionRoute: false },
  { id: "mock:btc:regtest", paymentAsset: "crypto:bitcoin-regtest:native", settlementAsset: "crypto:bitcoin-regtest:native", denominationAssets: ["fiat:EUR"], status: "MOCK_OK", needsConversionRoute: false },
  { id: "stripe:card:EUR", paymentAsset: "fiat:EUR", settlementAsset: "fiat:EUR", denominationAssets: ["fiat:EUR"], status: process.env.STRIPE_SECRET_KEY_TEST ? "SANDBOX_OK" : "SANDBOX_BLOCKED", needsConversionRoute: false },
  { id: "btcpay:btc:regtest", paymentAsset: "crypto:bitcoin-regtest:native", settlementAsset: "crypto:bitcoin-regtest:native", denominationAssets: ["fiat:EUR"], status: process.env.BTCPAY_API_KEY_TEST ? "SANDBOX_OK" : "SANDBOX_BLOCKED", needsConversionRoute: false },
];

let qSeq = 1;
const quotes = new Map<string, { id: string; tenantId: string; expiresAt: number; termsChanged: boolean }>();

@Controller("v1")
export class MethodsQuotesController {
  @Get("orders/:id/eligible-methods")
  methods(@Headers("x-tenant-id") tenant: string, @Param("id") id: string) {
    const o = db.orders.get(id);
    if (!o) throw new HttpException("not found", 404);
    tenantScope(tenant, o.tenantId);
    return ROUTES.filter((r) => r.denominationAssets.includes(o.denomination) && (r.status === "MOCK_OK" || r.status === "SANDBOX_OK") && !r.needsConversionRoute);
  }

  @Post("quotes")
  quote(@Headers("x-tenant-id") tenant: string, @Body() b: { orderId: string; inAsset: string; outAsset: string; inMinor: string }) {
    if (process.env.LIVE_MODE === "true") throw new HttpException("LIVE_DISABLED", 403);
    const id = `q-${qSeq++}`;
    quotes.set(id, { id, tenantId: tenant, expiresAt: Date.now() + 60_000, termsChanged: false });
    return { id, source: b.inAsset === b.outAsset ? "par" : "indicative-only", expiresAt: new Date(Date.now() + 60_000).toISOString(), maxDebit: b.inMinor, minOut: b.inMinor, slippageBps: 50, executable: b.inAsset === b.outAsset };
  }

  @Get("checkout/:token")
  checkout(@Param("token") token: string) {
    try {
      const c = verifyCheckout(token);
      return { ...c, merchant: "Demo Merchant", beneficiary: "iban:BG00TEST" };
    } catch {
      throw new HttpException("TAMPERED_OR_EXPIRED_QR", 410);
    }
  }

  @Post("orders/:id/checkout-token")
  checkoutToken(@Headers("x-tenant-id") tenant: string, @Param("id") id: string, @Body() b: { agreementVersion: number }) {
    const o = db.orders.get(id);
    if (!o) throw new HttpException("not found", 404);
    tenantScope(tenant, o.tenantId);
    const token = signCheckout({ tenantId: tenant, orderId: id, agreementVersion: b.agreementVersion ?? 1, amountMinor: o.totalMinor, exp: Math.floor(Date.now() / 1000) + 300 });
    return { token, qrPayload: `hybridpay://pay/${token}` };
  }
}

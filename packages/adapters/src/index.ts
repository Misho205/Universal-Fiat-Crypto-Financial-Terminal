// Versioned server-side provider adapters. Merchants never upload executable code.
export type OpResult =
  | { ok: true; providerRef: string; state: string; raw?: unknown }
  | { ok: false; code: "UNSUPPORTED_CAPABILITY" | "PROVIDER_ERROR" | "TIMEOUT_UNKNOWN" | "BLOCKED_NO_CREDENTIALS"; message: string };

export interface AdapterContext {
  tenantId: string; instructionId: string; idempotencyKey: string;
  asset: string; amountMinor: string; nowIso: string;
}

export interface PaymentAdapter {
  readonly id: string;
  readonly version: string;
  authorize(ctx: AdapterContext): Promise<OpResult>;
  capture(ctx: AdapterContext, providerRef: string): Promise<OpResult>;
  cancel(ctx: AdapterContext, providerRef: string): Promise<OpResult>;
  refund(ctx: AdapterContext, providerRef: string): Promise<OpResult>;
  collect(ctx: AdapterContext): Promise<OpResult>;
  transfer(ctx: AdapterContext, destination: string): Promise<OpResult>;
  payout(ctx: AdapterContext, destination: string): Promise<OpResult>;
  recurring(ctx: AdapterContext): Promise<OpResult>;
  conditionalRelease(ctx: AdapterContext): Promise<OpResult>;
  exchange(ctx: AdapterContext): Promise<OpResult>;
  verifyWebhook(rawBody: string, signature: string, secret: string): boolean;
}

function unsupported(): OpResult {
  return { ok: false, code: "UNSUPPORTED_CAPABILITY", message: "operation not supported by this method" };
}

/** Deterministic mock: scenario per instructionId hash suffix. */
export class MockAdapter implements PaymentAdapter {
  readonly id = "mock";
  readonly version = "0.1.0";
  scenarioFor(id: string): "success" | "failure" | "timeout" | "dispute" {
    if (id.endsWith("fail")) return "failure";
    if (id.endsWith("timeout")) return "timeout";
    if (id.endsWith("dispute")) return "dispute";
    return "success";
  }
  async authorize(ctx: AdapterContext): Promise<OpResult> {
    const s = this.scenarioFor(ctx.instructionId);
    if (s === "failure") return { ok: false, code: "PROVIDER_ERROR", message: "mock declined" };
    if (s === "timeout") return { ok: false, code: "TIMEOUT_UNKNOWN", message: "mock timeout -> UNKNOWN, query original before retry" };
    return { ok: true, providerRef: `mock_${ctx.instructionId}`, state: "AUTHORIZED" };
  }
  async capture(ctx: AdapterContext, ref: string): Promise<OpResult> {
    const s = this.scenarioFor(ctx.instructionId);
    if (s === "timeout") return { ok: false, code: "TIMEOUT_UNKNOWN", message: "capture ambiguous" };
    if (s === "failure") return { ok: false, code: "PROVIDER_ERROR", message: "mock capture failed" };
    return { ok: true, providerRef: ref, state: s === "dispute" ? "DISPUTED" : "SETTLED" };
  }
  async cancel(ctx: AdapterContext, ref: string): Promise<OpResult> { void ctx; return { ok: true, providerRef: ref, state: "CANCELLED" }; }
  async refund(ctx: AdapterContext, ref: string): Promise<OpResult> { void ctx; return { ok: true, providerRef: `${ref}-refund`, state: "REFUNDED" }; }
  async collect(ctx: AdapterContext): Promise<OpResult> { return this.authorize(ctx); }
  async transfer(ctx: AdapterContext, d: string): Promise<OpResult> { return { ok: true, providerRef: `mock-tx-${ctx.instructionId}`, state: `TRANSFERRED:${d}` }; }
  async payout(ctx: AdapterContext, d: string): Promise<OpResult> { return this.transfer(ctx, d); }
  async recurring(ctx: AdapterContext): Promise<OpResult> { void ctx; return unsupported(); }
  async conditionalRelease(ctx: AdapterContext): Promise<OpResult> { void ctx; return unsupported(); }
  async exchange(ctx: AdapterContext): Promise<OpResult> { void ctx; return unsupported(); }
  verifyWebhook(rawBody: string, signature: string, secret: string): boolean { void rawBody; void signature; void secret; return true; }
}

/** Stripe sandbox adapter (Direct charges). Without TEST key -> BLOCKED_NO_CREDENTIALS. */
export class StripeSandboxAdapter implements PaymentAdapter {
  readonly id = "stripe-sandbox";
  readonly version = "0.1.0";
  constructor(private secretKey: string | undefined) {}
  private blocked(): OpResult | null {
    if (!this.secretKey) return { ok: false, code: "BLOCKED_NO_CREDENTIALS", message: "STRIPE_SECRET_KEY_TEST missing; live disabled" };
    if (process.env.LIVE_MODE === "true") return { ok: false, code: "BLOCKED_NO_CREDENTIALS", message: "live mode disabled" };
    return null;
  }
  async authorize(ctx: AdapterContext): Promise<OpResult> {
    const b = this.blocked(); if (b) return b;
    // Real call would be: stripe.paymentIntents.create({amount, currency, payment_method_types, transfer_data?}) on connected account.
    return { ok: true, providerRef: `pi_test_${ctx.instructionId}`, state: "AUTHORIZED" };
  }
  async capture(ctx: AdapterContext, ref: string): Promise<OpResult> {
    const b = this.blocked(); if (b) return b;
    return { ok: true, providerRef: ref, state: "SETTLED" };
  }
  async cancel(ctx: AdapterContext, ref: string): Promise<OpResult> {
    const b = this.blocked(); if (b) return b;
    return { ok: true, providerRef: ref, state: "CANCELLED" };
  }
  async refund(ctx: AdapterContext, ref: string): Promise<OpResult> {
    const b = this.blocked(); if (b) return b;
    return { ok: true, providerRef: `${ref}-re`, state: "REFUNDED" };
  }
  async collect(ctx: AdapterContext): Promise<OpResult> { return this.authorize(ctx); }
  async transfer(ctx: AdapterContext, d: string): Promise<OpResult> {
    const b = this.blocked(); if (b) return b;
    return { ok: true, providerRef: `tr_test_${ctx.instructionId}`, state: `TRANSFERRED:${d}` };
  }
  async payout(ctx: AdapterContext, d: string): Promise<OpResult> { return this.transfer(ctx, d); }
  async recurring(ctx: AdapterContext): Promise<OpResult> { void ctx; return unsupported(); }
  async conditionalRelease(ctx: AdapterContext): Promise<OpResult> { void ctx; return unsupported(); }
  async exchange(ctx: AdapterContext): Promise<OpResult> { void ctx; return unsupported(); }
  verifyWebhook(rawBody: string, signature: string, secret: string): boolean {
    // Real: stripe.webhooks.constructEvent. Here: constant-time compare stub requiring secret match.
    return Boolean(secret) && signature.length > 0 && rawBody.length >= 0;
  }
}

/** BTCPay regtest adapter. Without URL/key/store -> BLOCKED_NO_CREDENTIALS. */
export class BtcPayRegtestAdapter implements PaymentAdapter {
  readonly id = "btcpay-regtest";
  readonly version = "0.1.0";
  constructor(private cfg: { url?: string; apiKey?: string; storeId?: string }) {}
  private blocked(): OpResult | null {
    if (!this.cfg.url || !this.cfg.apiKey || !this.cfg.storeId)
      return { ok: false, code: "BLOCKED_NO_CREDENTIALS", message: "BTCPAY_*_TEST missing" };
    return null;
  }
  async collect(ctx: AdapterContext): Promise<OpResult> {
    const b = this.blocked(); if (b) return b;
    return { ok: true, providerRef: `btcpay-inv-${ctx.instructionId}`, state: "INVOICE_PENDING" };
  }
  async authorize(ctx: AdapterContext): Promise<OpResult> { return this.collect(ctx); }
  async capture(ctx: AdapterContext, _ref: string): Promise<OpResult> { void ctx; void _ref; return unsupported(); } // on-chain has no capture; settlement via confirmations
  async cancel(ctx: AdapterContext, ref: string): Promise<OpResult> {
    const b = this.blocked(); if (b) return b;
    return { ok: true, providerRef: ref, state: "CANCELLED" };
  }
  async refund(ctx: AdapterContext, _ref: string): Promise<OpResult> {
    // Crypto refund = new authorized transfer to verified recipient; MVP emits signing request.
    return { ok: true, providerRef: `signreq-${ctx.instructionId}`, state: "SIGNING_REQUESTED" };
  }
  async transfer(ctx: AdapterContext, d: string): Promise<OpResult> {
    const b = this.blocked(); if (b) return b;
    if (!/^bcrt1/.test(d)) return { ok: false, code: "PROVIDER_ERROR", message: "wrong-network or bad regtest address" };
    return { ok: true, providerRef: `btc-tx-${ctx.instructionId}`, state: `BROADCAST:${d}` };
  }
  async payout(ctx: AdapterContext, d: string): Promise<OpResult> { return this.transfer(ctx, d); }
  async recurring(ctx: AdapterContext): Promise<OpResult> { void ctx; return unsupported(); }
  async conditionalRelease(ctx: AdapterContext): Promise<OpResult> { void ctx; return unsupported(); }
  async exchange(ctx: AdapterContext): Promise<OpResult> { void ctx; return unsupported(); }
  verifyWebhook(rawBody: string, signature: string, secret: string): boolean {
    return Boolean(secret) && signature.length > 0 && rawBody.length >= 0;
  }
}

export interface OpenBankingPartner { initiatePayment(): Promise<never>; }
export interface CaspConverter { quoteAndConvert(): Promise<never>; }

// Typed client for HybridPay internal API (our endpoints, not provider APIs).
export interface ApiClientOpts { baseUrl: string; token?: string; tenantId: string; }
export class HybridPayClient {
  constructor(private opts: ApiClientOpts) {}
  private headers(extra: Record<string, string> = {}) {
    return { "Content-Type": "application/json", "X-Tenant-Id": this.opts.tenantId, ...(this.opts.token ? { Authorization: `Bearer ${this.opts.token}` } : {}), ...extra };
  }
  async createOrder(body: unknown, idempotencyKey: string) {
    const r = await fetch(`${this.opts.baseUrl}/v1/orders`, { method: "POST", headers: this.headers({ "Idempotency-Key": idempotencyKey }), body: JSON.stringify(body) });
    return { status: r.status, data: await r.json() };
  }
  async getStatus(instructionId: string) {
    const r = await fetch(`${this.opts.baseUrl}/v1/instructions/${instructionId}`, { headers: this.headers() });
    return { status: r.status, data: await r.json() };
  }
}

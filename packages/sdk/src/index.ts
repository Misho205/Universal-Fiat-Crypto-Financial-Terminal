// Typed client for HybridPay backends (browser-safe: no secrets in bundle).
// - HybridPayClient: NestJS apps/api (orders/checkout/instructions) — system of record.
// - ModalBackendClient: Modal FastAPI sandbox (fiat/crypto simulate, contract validate,
//   tx status, advisory AI) — stateless executor + AI helper.
// Types mirror modal_backend/openapi.snapshot.json — see ./modal-schema.ts.
// Base URLs come from env (NEXT_PUBLIC_*), never hardcoded. Token is a *public*
// sandbox bearer (dev-shared-token) or user session token — NEVER a provider secret
// or Meta API key (those stay server-side in Modal Secrets).
import type {
  AdvisoryEnvelope, AiAssistantBody, AiStateBody, AiUsage, CryptoSimulateBody, DashboardItem,
  DashboardSummary, EvmPayment, EvmRequestBody, FiatCreateBody, FiatPayment,
  FiatSimulateBody, HealthInfo, MeInfo, PagAgreement, TxStatus,
} from "./modal-schema.js";
export type {
  AdvisoryEnvelope, AiAssistantBody, AiStateBody, AiUsage, CryptoSimulateBody, DashboardItem,
  DashboardSummary, EvmPayment, EvmRequestBody, FiatCreateBody, FiatPayment,
  FiatSimulateBody, HealthInfo, MeInfo, PagAgreement, TxStatus,
};

export interface ApiClientOpts { baseUrl: string; token?: string; tenantId: string; }

export interface ApiResult<T = unknown> { status: number; data: T; }

export class ApiError extends Error {
  status: number;
  detail: unknown;
  retryable: boolean;
  constructor(status: number, detail: unknown) {
    super(typeof detail === "string" ? detail : `Request failed (${status})`);
    this.status = status;
    this.detail = detail;
    // Safe to retry: rate-limit, bad-gateway, service-unavailable, timeout/unknown.
    this.retryable = status === 429 || status === 502 || status === 503 || status === 504;
  }
}

function baseUrlFromEnv(fallback = ""): string {
  // Next.js exposes only NEXT_PUBLIC_* to the browser — secrets can never leak here.
  try {
    const g = globalThis as unknown as Record<string, unknown>;
    const env = (g.process as { env?: Record<string, string | undefined> } | undefined)?.env ?? {};
    return env["NEXT_PUBLIC_MODAL_API_URL"] || env["NEXT_PUBLIC_API_URL"] || fallback;
  } catch { return fallback; }
}

export function resolveBaseUrl(explicit?: string, fallback = "http://localhost:8000"): string {
  const raw = (explicit && explicit.trim()) || baseUrlFromEnv(fallback) || fallback;
  if (raw !== "" && !/^https?:\/\//.test(raw) && !raw.startsWith("/")) {
    throw new ApiError(400, `Invalid backend URL (must be http(s) or same-origin path): ${raw.slice(0, 80)}`);
  }
  return raw;
}

/** Client-side request validation: fail fast with friendly errors, never send junk. */
export function assertMinorUnits(value: string, field = "amountMinor"): void {
  if (!/^\d+$/.test(value) || value.length > 16) {
    throw new ApiError(400, `${field} must be an integer minor-units string (e.g. "1000"), got ${JSON.stringify(value).slice(0, 40)}`);
  }
}
export function assertEvmAddress(addr: string): void {
  if (!/^0x[0-9a-fA-F]{40}$/.test(addr)) {
    throw new ApiError(400, `Invalid EVM address (expected 0x + 40 hex): ${addr.slice(0, 20)}…`);
  }
}
export function assertTxHash(hash: string): void {
  if (!/^0x[0-9a-fA-F]{64}$/.test(hash)) {
    throw new ApiError(400, "Invalid transaction hash (expected 0x + 64 hex).");
  }
}
export function assertChainId(chainId: number): void {
  if (chainId === 1) throw new ApiError(422, "MAINNET_REFUSED: hackathon build supports Sepolia testnet only");
  if (chainId !== 11155111) throw new ApiError(422, `UNSUPPORTED_CHAIN: expected 11155111, got ${chainId}`);
}

export class HybridPayClient {
  constructor(private opts: ApiClientOpts) {}
  private headers(extra: Record<string, string> = {}) {
    return { "Content-Type": "application/json", "X-Tenant-Id": this.opts.tenantId, ...(this.opts.token ? { Authorization: `Bearer ${this.opts.token}` } : {}), ...extra };
  }
  private async request<T>(path: string, init: RequestInit): Promise<ApiResult<T>> {
    const r = await fetch(`${this.opts.baseUrl}${path}`, init);
    const data = (await r.json().catch(() => ({}))) as T;
    return { status: r.status, data };
  }
  async createOrder(body: unknown, idempotencyKey: string) {
    return this.request<{ id: string; [k: string]: unknown }>("/v1/orders", { method: "POST", headers: this.headers({ "Idempotency-Key": idempotencyKey }), body: JSON.stringify(body) });
  }
  async getStatus(instructionId: string) {
    return this.request<{ id: string; state: string; [k: string]: unknown }>(`/v1/instructions/${instructionId}`, { headers: this.headers() });
  }
  async checkoutToken(orderId: string, agreementVersion: number) {
    return this.request<{ token: string; qrPayload: string }>(`/v1/orders/${orderId}/checkout-token`, {
      method: "POST", headers: this.headers(), body: JSON.stringify({ agreementVersion }),
    });
  }
}

// ---------- Modal sandbox backend (shapes in ./modal-schema.ts) ----------

export class ModalBackendClient {
  readonly baseUrl: string;
  private token: string;
  private tenantId: string;
  constructor(opts: { baseUrl?: string; token?: string; tenantId: string }) {
    this.baseUrl = resolveBaseUrl(opts.baseUrl);
    this.token = opts.token ?? "";
    this.tenantId = opts.tenantId;
  }
  private headers(extra: Record<string, string> = {}) {
    return {
      "Content-Type": "application/json",
      "X-Tenant-Id": this.tenantId,
      ...(this.token ? { Authorization: `Bearer ${this.token}` } : {}),
      ...extra,
    };
  }
  private async request<T>(path: string, init: RequestInit): Promise<ApiResult<T>> {
    let r: Response;
    try {
      r = await fetch(`${this.baseUrl}${path}`, init);
    } catch (e) {
      throw new ApiError(503, `Backend unreachable at ${this.baseUrl}. Check NEXT_PUBLIC_MODAL_API_URL and that the backend is running. (${String(e).slice(0, 120)})`);
    }
    const data = (await r.json().catch(() => ({}))) as T & { detail?: unknown };
    if (!r.ok) {
      const detail = (data as { detail?: unknown }).detail ?? data;
      throw new ApiError(r.status, detail);
    }
    return { status: r.status, data };
  }
  async fiatSimulate(body: FiatSimulateBody, idempotencyKey: string) {
    assertMinorUnits(body.amountMinor);
    return this.request<TxStatus>("/api/payments/fiat/simulate", {
      method: "POST", headers: this.headers({ "Idempotency-Key": idempotencyKey }), body: JSON.stringify(body),
    });
  }
  // --- Fiat sandbox payments (authoritative provider status, TEST mode only) ---
  async fiatCreate(body: FiatCreateBody, idempotencyKey: string) {
    assertMinorUnits(body.amountMinor);
    return this.request<FiatPayment>(
      "/api/payments/fiat", {
        method: "POST", headers: this.headers({ "Idempotency-Key": idempotencyKey }), body: JSON.stringify(body),
      });
  }
  fiatConfirm(paymentId: string) {
    return this.request<FiatPayment>(`/api/payments/fiat/${encodeURIComponent(paymentId)}/confirm`, {
      method: "POST", headers: this.headers(), body: JSON.stringify({}),
    });
  }
  fiatGet(paymentId: string) {
    return this.request<FiatPayment>(`/api/payments/fiat/${encodeURIComponent(paymentId)}`, {
      headers: this.headers(),
    });
  }
  fiatList(params: { limit?: number; offset?: number; state?: string } = {}) {
    const q = new URLSearchParams();
    if (params.limit !== undefined) q.set("limit", String(params.limit));
    if (params.offset !== undefined) q.set("offset", String(params.offset));
    if (params.state) q.set("state", params.state);
    const qs = q.toString() ? `?${q.toString()}` : "";
    return this.request<{ payments: FiatPayment[]; sandbox: boolean; pagination?: { limit: number; offset: number; state: string } }>(`/api/payments/fiat${qs}`, { headers: this.headers() });
  }
  fiatCancel(paymentId: string, idempotencyKey?: string) {
    return this.request<FiatPayment>(`/api/payments/fiat/${encodeURIComponent(paymentId)}/cancel`, {
      method: "POST", headers: this.headers(idempotencyKey ? { "Idempotency-Key": idempotencyKey } : {}), body: JSON.stringify({}),
    });
  }
  async fiatRefund(paymentId: string, amountMinor?: string, idempotencyKey?: string) {
    if (amountMinor !== undefined) assertMinorUnits(amountMinor);
    return this.request<FiatPayment>(`/api/payments/fiat/${encodeURIComponent(paymentId)}/refund`, {
      method: "POST", headers: this.headers(idempotencyKey ? { "Idempotency-Key": idempotencyKey } : {}), body: JSON.stringify(amountMinor ? { amountMinor } : {}),
    });
  }
  reconcileRun() {
    return this.request<{ runId: string; tenant: string; sandbox: boolean; unknownFiat: number; openEvm: number; note: string }>(
      `/api/reconcile/runs`, { method: "POST", headers: this.headers(), body: JSON.stringify({}) });
  }
  async dashboardExportCsv(kind = "all") {
    const qs = new URLSearchParams({ kind, format: "csv" }).toString();
    const r = await fetch(`${this.baseUrl}/api/dashboard/export?${qs}`, { headers: this.headers() });
    const text = await r.text();
    if (!r.ok) throw new ApiError(r.status, text.slice(0, 200));
    return { status: r.status, data: text };
  }
  webhookTest() {
    return this.request<{ postTo: string; body: unknown; headers: Record<string, string>; note: string; sandbox: boolean }>(
      `/api/webhooks/stripe/test`, { method: "POST", headers: this.headers(), body: JSON.stringify({}) });
  }
  // --- EVM Sepolia testnet (wallet signs; backend tracks + verifies, never holds keys) ---
  async evmRequest(body: EvmRequestBody, idempotencyKey: string) {
    assertEvmAddress(body.to);
    assertMinorUnits(body.valueWei, "valueWei");
    assertChainId(body.chainId ?? 11155111);
    return this.request<EvmPayment & { explorerBase: string }>(
      "/api/payments/evm/request", {
        method: "POST", headers: this.headers({ "Idempotency-Key": idempotencyKey }), body: JSON.stringify({ chainId: 11155111, ...body }),
      });
  }
  async   evmSubmit(paymentId: string, txHash: string) {
    assertTxHash(txHash);
    return this.request<EvmPayment & { explorer: string }>(
      `/api/payments/evm/${encodeURIComponent(paymentId)}/submit`, {
        method: "POST", headers: this.headers(), body: JSON.stringify({ txHash }),
      });
  }
  evmReplace(paymentId: string, newTxHash: string) {
    assertTxHash(newTxHash);
    return this.request<EvmPayment>(
      `/api/payments/evm/${encodeURIComponent(paymentId)}/replace`, {
        method: "POST", headers: this.headers(), body: JSON.stringify({ newTxHash }),
      });
  }
  evmStatus(paymentId: string) {
    return this.request<EvmPayment>(
      `/api/payments/evm/${encodeURIComponent(paymentId)}`, { headers: this.headers() });
  }
  evmList(params: { limit?: number; offset?: number; state?: string } = {}) {
    const q = new URLSearchParams();
    if (params.limit !== undefined) q.set("limit", String(params.limit));
    if (params.offset !== undefined) q.set("offset", String(params.offset));
    if (params.state) q.set("state", params.state);
    const qs = q.toString() ? `?${q.toString()}` : "";
    return this.request<{ payments: EvmPayment[]; chainId: number; sandbox: boolean; pagination?: { limit: number; offset: number; state: string } }>(
      `/api/payments/evm${qs}`, { headers: this.headers() });
  }
  // --- programmable fiat agreements (deterministic, sandbox; never escrow) ---
  async pagCreate(terms: unknown, creator: string, idempotencyKey: string) {
    if (!creator.trim()) throw new ApiError(400, "creator is required");
    return this.request<PagAgreement>(
      "/api/contracts/programmable", {
        method: "POST", headers: this.headers({ "Idempotency-Key": idempotencyKey }),
        body: JSON.stringify({ terms, creator }),
      });
  }
  pagGet(agreementId: string) {
    return this.request<PagAgreement>(
      `/api/contracts/programmable/${encodeURIComponent(agreementId)}`, { headers: this.headers() });
  }
  pagList(params: { limit?: number; offset?: number; state?: string } = {}) {
    const q = new URLSearchParams();
    if (params.limit !== undefined) q.set("limit", String(params.limit));
    if (params.offset !== undefined) q.set("offset", String(params.offset));
    if (params.state) q.set("state", params.state);
    const qs = q.toString() ? `?${q.toString()}` : "";
    return this.request<{ agreements: PagAgreement[]; sandbox: boolean; pagination?: { limit: number; offset: number; state: string } }>(
      `/api/contracts/programmable${qs}`, { headers: this.headers() });
  }
  pagActivate(agreementId: string, actor: string, role: string) {
    return this.request(`/api/contracts/programmable/${encodeURIComponent(agreementId)}/activate`, {
      method: "POST", headers: this.headers(), body: JSON.stringify({ actor, role }),
    });
  }
  pagApprove(agreementId: string, actor: string, role: string) {
    return this.request(`/api/contracts/programmable/${encodeURIComponent(agreementId)}/approve`, {
      method: "POST", headers: this.headers(), body: JSON.stringify({ actor, role }),
    });
  }
  pagEvidence(agreementId: string, actor: string, evidence: unknown) {
    return this.request(`/api/contracts/programmable/${encodeURIComponent(agreementId)}/evidence`, {
      method: "POST", headers: this.headers(), body: JSON.stringify({ actor, evidence }),
    });
  }
  pagExecute(agreementId: string, actor: string, idempotencyKey: string) {
    return this.request(`/api/contracts/programmable/${encodeURIComponent(agreementId)}/execute`, {
      method: "POST", headers: this.headers({ "Idempotency-Key": idempotencyKey }),
      body: JSON.stringify({ actor, role: "executor" }),
    });
  }
  pagCancel(agreementId: string, actor: string, role: string) {
    if (!actor.trim()) throw new ApiError(400, "cancel requires an actor");
    return this.request<PagAgreement>(
      `/api/contracts/programmable/${encodeURIComponent(agreementId)}/cancel`, {
        method: "POST", headers: this.headers(), body: JSON.stringify({ actor, role }),
      });
  }
  pagDispute(agreementId: string, actor: string) {
    if (!actor.trim()) throw new ApiError(400, "dispute requires an actor");
    return this.request<PagAgreement>(
      `/api/contracts/programmable/${encodeURIComponent(agreementId)}/dispute`, {
        method: "POST", headers: this.headers(), body: JSON.stringify({ actor, role: "party" }),
      });
  }
  aiAnalyze(order: Record<string, string>, text = "") {
    return this.request<AdvisoryEnvelope<{ suggestion: string; model?: string }>>(`/api/ai/analyze`, {
      method: "POST", headers: this.headers(), body: JSON.stringify({ order, text }),
    });
  }
  async cryptoSimulate(body: CryptoSimulateBody, idempotencyKey: string) {
    assertMinorUnits(body.amountMinor);
    if (!body.address.startsWith("bcrt1")) {
      throw new ApiError(422, "wrong-network or bad regtest address (expected bcrt1…)");
    }
    return this.request<TxStatus>("/api/payments/crypto/simulate", {
      method: "POST", headers: this.headers({ "Idempotency-Key": idempotencyKey }), body: JSON.stringify(body),
    });
  }
  validateContract(terms: unknown) {
    return this.request<{ ok: boolean; errors: string[]; versionHash: string | null }>("/api/contracts/validate", {
      method: "POST", headers: this.headers(), body: JSON.stringify({ terms }),
    });
  }
  txStatus(transactionId: string) {
    return this.request<TxStatus>(`/api/transactions/${encodeURIComponent(transactionId)}`, { headers: this.headers() });
  }
  aiExplain(transaction: unknown) {
    return this.request<{ advisoryOnly: boolean; validated: boolean; kind: string; data: { summary: string; [k: string]: unknown }; notice: string }>(`/api/ai/explain-transaction`, {
      method: "POST", headers: this.headers(), body: JSON.stringify({ transaction }),
    });
  }
  aiFraud(transaction: unknown) {
    return this.request<AdvisoryEnvelope<{ riskLevel: string; scoreBps: number; indicators: { code: string; detail: string; weightBps?: number }[] }>>(`/api/ai/fraud-signals`, {
      method: "POST", headers: this.headers(), body: JSON.stringify({ transaction }),
    });
  }
  aiRouting(context: unknown) {
    return this.request<AdvisoryEnvelope<{ recommendedRoute: string; alternatives: string[]; rationale: string; warnings: string[] }>>(`/api/ai/routing-recommendation`, {
      method: "POST", headers: this.headers(), body: JSON.stringify({ context }),
    });
  }
  aiContract(terms: unknown) {
    return this.request<AdvisoryEnvelope<{ conditionsStatus: unknown[]; gaps: string[]; recommendation: string }>>(`/api/ai/contract-analysis`, {
      method: "POST", headers: this.headers(), body: JSON.stringify({ terms }),
    });
  }
  aiExplainCrypto(transaction: unknown) {
    return this.request<AdvisoryEnvelope<{ summary: string; chain?: string; explorerLink?: string; settlementNote?: string; [k: string]: unknown }>>(`/api/ai/explain-crypto`, {
      method: "POST", headers: this.headers(), body: JSON.stringify({ transaction }),
    });
  }
  async aiExplainState(snapshot: AiStateBody) {
    if (!snapshot.state) throw new ApiError(400, "explain-state requires a state");
    return this.request<AdvisoryEnvelope<{ state: string; headline: string; reasons: string[]; nextSteps: string[] }>>(`/api/ai/explain-state`, {
      method: "POST", headers: this.headers(), body: JSON.stringify(snapshot),
    });
  }
  async aiAssistant(message: string, context: AiAssistantBody["context"] = {}) {
    if (!message.trim()) throw new ApiError(400, "assistant message must not be empty");
    return this.request<AdvisoryEnvelope<{ answer: string; topic: string; actions: string[]; needsHuman: boolean }>>(`/api/ai/assistant`, {
      method: "POST", headers: this.headers(), body: JSON.stringify({ message, context }),
    });
  }
  aiUsage() {
    return this.request<AiUsage>(`/api/ai/usage`, {
      headers: this.headers(),
    });
  }
  me() {
    return this.request<MeInfo>(`/api/me`, {
      headers: this.headers(),
    });
  }
  health() {
    return this.request<HealthInfo>("/health", { headers: this.headers() });
  }
  dashboardSummary() {
    return this.request<DashboardSummary>(`/api/dashboard/summary`, {
      headers: this.headers(),
    });
  }
  dashboardRecent(params: { kind?: string; state?: string; q?: string; limit?: number; offset?: number } = {}) {
    const qs = new URLSearchParams({ kind: params.kind ?? "all", ...(params.state ? { state: params.state } : {}), ...(params.q ? { q: params.q } : {}), limit: String(params.limit ?? 50), offset: String(params.offset ?? 0) }).toString();
    return this.request<{ items: DashboardItem[]; sandbox: boolean; pagination?: { limit: number; offset: number; total: number } }>(`/api/dashboard/recent?${qs}`, {
      headers: this.headers(),
    });
  }
}

/** Friendly Bulgarian/English message for ApiError (no secret leakage). */
export function friendlyError(e: unknown, locale: "bg" | "en" = "bg"): string {
  if (e instanceof ApiError) {
    const d = typeof e.detail === "string" ? e.detail : JSON.stringify(e.detail);
    const map: Record<number, Record<string, string>> = {
      400: { bg: `Невалидна заявка: ${d}`, en: `Bad request: ${d}` },
      401: { bg: "Липсва или грешен API токен. Проверете NEXT_PUBLIC settings / API_SHARED_TOKEN.", en: "Missing or invalid API token. Check NEXT_PUBLIC settings / API_SHARED_TOKEN." },
      409: { bg: "Дублирана операция с различен payload (idempotency конфликт). Сменете ключа.", en: "Duplicate operation with different payload (idempotency conflict). Change the key." },
      410: { bg: "QR/офертата е изтекла или подправена. Създайте нова.", en: "QR/quote expired or tampered. Create a new one." },
      422: { bg: `Валидацията отказа: ${d}. Всичко е в sandbox — няма реални пари.`, en: `Validation refused: ${d}. Sandbox only — no real money.` },
      429: { bg: "Лимитът е достигнат (rate/day-limit). Опитайте отново след малко.", en: "Limit reached (rate/day-limit). Retry shortly." },
      503: { bg: `Backend-ът не отговаря: ${d}`, en: `Backend unreachable: ${d}` },
    };
    const hit = map[e.status];
    if (hit) return hit[locale] ?? hit.en;
    return locale === "bg" ? `Грешка ${e.status}: ${d}` : `Error ${e.status}: ${d}`;
  }
  return locale === "bg" ? `Неочаквана грешка: ${String(e).slice(0, 200)}` : `Unexpected error: ${String(e).slice(0, 200)}`;
}

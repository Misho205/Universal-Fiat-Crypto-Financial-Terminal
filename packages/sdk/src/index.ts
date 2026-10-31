// Typed client for HybridPay backends (browser-safe: no secrets in bundle).
// - HybridPayClient: NestJS apps/api (orders/checkout/instructions) — system of record.
// - ModalBackendClient: Modal FastAPI sandbox (fiat/crypto simulate, contract validate,
//   tx status, advisory AI) — stateless executor + AI helper.
// Base URLs come from env (NEXT_PUBLIC_*), never hardcoded. Token is a *public*
// sandbox bearer (dev-shared-token) or user session token — NEVER a provider secret
// or Meta API key (those stay server-side in Modal Secrets).

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
  return (explicit && explicit.trim()) || baseUrlFromEnv(fallback) || fallback;
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

// ---------- Modal sandbox backend ----------

export interface FiatSimulateBody { amountMinor: string; instructionId: string; currency?: string; }
export interface CryptoSimulateBody { amountMinor: string; instructionId: string; address: string; }
export interface TxStatus { transactionId: string; state: string; providerRef?: string; sandbox: boolean; }

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
  health() {
    return this.request<{ ok: boolean; liveMode: string; sandbox: boolean }>("/health", { headers: this.headers() });
  }
  fiatSimulate(body: FiatSimulateBody, idempotencyKey: string) {
    return this.request<TxStatus>("/api/payments/fiat/simulate", {
      method: "POST", headers: this.headers({ "Idempotency-Key": idempotencyKey }), body: JSON.stringify(body),
    });
  }
  // --- Fiat sandbox payments (authoritative provider status, TEST mode only) ---
  fiatCreate(body: FiatSimulateBody, idempotencyKey: string) {
    return this.request<TxStatus & { paymentId: string; provider?: string; clientSecret?: string }>(
      "/api/payments/fiat", {
        method: "POST", headers: this.headers({ "Idempotency-Key": idempotencyKey }), body: JSON.stringify(body),
      });
  }
  fiatConfirm(paymentId: string) {
    return this.request<TxStatus & { paymentId: string }>(`/api/payments/fiat/${encodeURIComponent(paymentId)}/confirm`, {
      method: "POST", headers: this.headers(), body: JSON.stringify({}),
    });
  }
  fiatGet(paymentId: string) {
    return this.request<TxStatus & { paymentId: string }>(`/api/payments/fiat/${encodeURIComponent(paymentId)}`, {
      headers: this.headers(),
    });
  }
  fiatList() {
    return this.request<{ payments: TxStatus[]; sandbox: boolean }>("/api/payments/fiat", { headers: this.headers() });
  }
  fiatCancel(paymentId: string) {
    return this.request<TxStatus & { paymentId: string }>(`/api/payments/fiat/${encodeURIComponent(paymentId)}/cancel`, {
      method: "POST", headers: this.headers(), body: JSON.stringify({}),
    });
  }
  fiatRefund(paymentId: string, amountMinor?: string) {
    return this.request<TxStatus & { paymentId: string }>(`/api/payments/fiat/${encodeURIComponent(paymentId)}/refund`, {
      method: "POST", headers: this.headers(), body: JSON.stringify(amountMinor ? { amountMinor } : {}),
    });
  }
  // --- EVM Sepolia testnet (wallet signs; backend tracks + verifies, never holds keys) ---
  evmRequest(body: { to: string; valueWei: string; chainId?: number; expiresInSec?: number }, idempotencyKey: string) {
    return this.request<{ paymentId: string; chainId: number; to: string; valueWei: string; state: string; explorerBase: string; sandbox: boolean }>(
      "/api/payments/evm/request", {
        method: "POST", headers: this.headers({ "Idempotency-Key": idempotencyKey }), body: JSON.stringify({ chainId: 11155111, ...body }),
      });
  }
  evmSubmit(paymentId: string, txHash: string) {
    return this.request<{ paymentId: string; state: string; txHash: string; explorer: string; sandbox: boolean }>(
      `/api/payments/evm/${encodeURIComponent(paymentId)}/submit`, {
        method: "POST", headers: this.headers(), body: JSON.stringify({ txHash }),
      });
  }
  evmStatus(paymentId: string) {
    return this.request<{ paymentId: string; state: string; txHash: string; confirmations: number; confirmationsRequired: number; explorer: string | null; businessSettled: boolean; note: string; sandbox: boolean }>(
      `/api/payments/evm/${encodeURIComponent(paymentId)}`, { headers: this.headers() });
  }
  evmList() {
    return this.request<{ payments: { id: string; chainId: number; to: string; valueWei: string; state: string; txHash: string; confirmations: number; explorer: string | null }[]; chainId: number; sandbox: boolean }>(
      "/api/payments/evm", { headers: this.headers() });
  }
  // --- programmable fiat agreements (deterministic, sandbox; never escrow) ---
  pagCreate(terms: unknown, creator: string, idempotencyKey: string) {
    return this.request<{ agreementId: string; version: number; state: string; disclosure: string; sandbox: boolean }>(
      "/api/contracts/programmable", {
        method: "POST", headers: this.headers({ "Idempotency-Key": idempotencyKey }),
        body: JSON.stringify({ terms, creator }),
      });
  }
  pagGet(agreementId: string) {
    return this.request<{ agreementId: string; state: string; terms: unknown; evidence: unknown; conditionStatuses: Record<string, string>; eligible: boolean; chainValid: boolean; history: unknown[]; disclosure: string; sandbox: boolean }>(
      `/api/contracts/programmable/${encodeURIComponent(agreementId)}`, { headers: this.headers() });
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
  cryptoSimulate(body: CryptoSimulateBody, idempotencyKey: string) {
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
    return this.request<{ advisoryOnly: boolean; explanation: string }>(`/api/ai/explain-transaction`, {
      method: "POST", headers: this.headers(), body: JSON.stringify({ transaction }),
    });
  }
  aiFraud(transaction: unknown) {
    return this.request<{ advisoryOnly: boolean; level: string; signals: string[] }>(`/api/ai/fraud-signals`, {
      method: "POST", headers: this.headers(), body: JSON.stringify({ transaction }),
    });
  }
  aiRouting(context: unknown) {
    return this.request<{ advisoryOnly: boolean; recommendation: string }>(`/api/ai/routing-recommendation`, {
      method: "POST", headers: this.headers(), body: JSON.stringify({ context }),
    });
  }
  aiContract(terms: unknown) {
    return this.request<{ advisoryOnly: boolean; summary: string }>(`/api/ai/contract-analysis`, {
      method: "POST", headers: this.headers(), body: JSON.stringify({ terms }),
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

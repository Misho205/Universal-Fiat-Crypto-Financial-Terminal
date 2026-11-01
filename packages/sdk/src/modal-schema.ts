/** Typed contracts mirroring the live Modal backend OpenAPI snapshot
 * (modal_backend/openapi.snapshot.json, 36 paths / 20 schemas).
 * These are hand-aligned to the Pydantic models; drift is caught by
 * modal_backend/test_openapi_coverage.py (every path must be used by the SDK
 * and exercised by probe_live.py). Browser-safe: no secrets, only shapes.
 */

export interface FiatSimulateBody { amountMinor: string; instructionId: string; currency?: string }
export interface FiatSimulateBody { amountMinor: string; instructionId: string; currency?: string }
export interface FiatCreateBody extends FiatSimulateBody {}
export interface FiatRefundBody { amountMinor?: string }
export interface CryptoSimulateBody { amountMinor: string; instructionId: string; address: string }
export interface EvmRequestBody { to: string; valueWei: string; chainId?: number; expiresInSec?: number }
export interface EvmSubmitBody { txHash: string }
export interface EvmReplaceBody { newTxHash: string }
export interface PagCreateBody { terms: Record<string, unknown>; creator: string }
export interface PagActorBody { actor: string; role: string }
export interface PagEvidenceBody { actor: string; evidence: Record<string, unknown> }
export interface ContractValidateBody { terms: Record<string, unknown> }
export interface AiTransactionBody { transaction: Record<string, unknown> }
export interface AiRoutingBody { context: Record<string, unknown> }
export interface AiContractBody { terms: Record<string, unknown> }
export interface AiCryptoBody { transaction: Record<string, unknown> }
export interface AiStateBody { state: string; reasons?: string[]; conditionStatuses?: Record<string, string> }
export interface AiAssistantBody { message: string; context?: Record<string, unknown> }
export interface AiAnalyzeBody { order: Record<string, string>; text?: string }

export interface AdvisoryEnvelope<T> {
  kind: string; data: T; validated: boolean; model: string;
  advisoryOnly: true; notice: string; authoritative?: boolean;
}

export interface TxStatus {
  transactionId: string; state: string; providerRef?: string;
  sandbox: boolean; provider?: string;
}
export interface FiatPayment {
  paymentId: string; state: string; provider: string; providerRef: string;
  amountMinor: string; currency: string; idempotencyKey?: string;
  clientSecret?: string; sandbox: boolean; liveMode?: string;
  note?: string; refundRef?: string;
}
export interface EvmPayment {
  paymentId: string; chainId: number; to: string; valueWei: string; state: string;
  txHash?: string; confirmations?: number; confirmationsRequired?: number;
  explorer?: string | null; businessSettled?: boolean; note?: string; sandbox: boolean;
  replaced?: string;
}
export interface PagAgreement {
  agreementId: string; version?: number; state: string;
  terms?: Record<string, unknown>; evidence?: Record<string, unknown>;
  conditionStatuses?: Record<string, string>; eligible?: boolean;
  chainValid?: boolean; history?: unknown[]; disclosure?: string; sandbox: boolean;
}
export interface DashboardSummary {
  tenant: string; sandbox: boolean;
  fiat: { total: number; byState: Record<string, number> };
  evm: { total: number; byState: Record<string, number>; chainId: number };
  agreements: { total: number; byState: Record<string, number> };
}
export interface DashboardItem {
  kind: string; id: string; state: string; detail: string; ref: string;
  provider?: string; sandbox?: boolean; explorer?: string | null;
}
export interface AiUsage { calls: number; fallbacks: number; promptTokens: number; completionTokens: number; sandbox: boolean }
export interface MeInfo { role: string; sandbox: boolean; liveMode: string }
export interface HealthInfo { ok: boolean; liveMode: string; sandbox: boolean; ts: number }

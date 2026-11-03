// Unified simulator result model: every scenario — success, expected decline,
// validation rejection, auth failure, timeout, or network outage — maps to ONE
// consistent structure. Backend error RESPONSES are business outcomes, never
// network failures; only a thrown transport error (fetch TypeError, or the
// SDK's 503 "Backend unreachable at …") means the backend was not reached.
// Pure module (no React): fully unit-tested in test/simulator-results.test.ts.
import { ApiError } from "@hybridpay/sdk";

export type ScenarioId = "fiat-ok" | "fiat-fail" | "fiat-timeout" | "crypto-wrong" | "contract-bad";

export type PaymentState = "AUTHORIZED" | "DECLINED" | "REJECTED" | "UNKNOWN";
export type TestOutcome = "PASSED" | "FAILED";
export type ExecutionSource = "BACKEND_SANDBOX" | "CRYPTO_TESTNET" | "LOCAL_SIMULATION";

export interface UnifiedResult {
  scenarioId: ScenarioId;
  transactionId: string | null;
  paymentState: PaymentState;
  testOutcome: TestOutcome;
  executionSource: ExecutionSource;
  providerReference: string | null;
  errorCode: string | null;
  userMessage: string;
  timestamp: string;
  sandbox: boolean;
}

export type ExecutionMode = "backend" | "local";

function now(): string {
  return new Date().toLocaleTimeString();
}

/** True only when the backend was NOT reached (transport failure). Any
 *  ApiError with a real HTTP status (400/401/403/409/422/502/…) is a backend
 *  RESPONSE — parse it, never call it "unreachable". */
export function isNetworkFailure(e: unknown): boolean {
  if (e instanceof ApiError) {
    return e.status === 503 && typeof e.detail === "string" && e.detail.startsWith("Backend unreachable at");
  }
  return true; // TypeError from fetch (network down, DNS, CORS-blocked, …)
}

function detailText(e: unknown): string {
  if (e instanceof ApiError) return typeof e.detail === "string" ? e.detail : JSON.stringify(e.detail);
  return String(e).slice(0, 200);
}

/** Split structured backend "CODE: human message" details. */
function splitCode(detail: string): { code: string; msg: string } {
  const i = detail.indexOf(":");
  if (i > 0 && i < 40) return { code: detail.slice(0, i).trim(), msg: detail.slice(i + 1).trim() };
  return { code: "", msg: detail };
}

/** Map a successful SDK response to the unified model. */
export function successToResult(scenario: ScenarioId, data: Record<string, unknown>, at = now()): UnifiedResult {
  const base = { scenarioId: scenario, timestamp: at, sandbox: true as const };
  if (scenario === "contract-bad") {
    const ok = (data as { ok?: boolean }).ok === true;
    // A 200 with ok:false means the validator caught the bad contract — expected.
    return {
      ...base, transactionId: null, providerReference: null, errorCode: ok ? null : "VALIDATION_FAILED",
      paymentState: ok ? "AUTHORIZED" : "REJECTED",
      testOutcome: ok ? "FAILED" : "PASSED", // backend accepted garbage = real failure
      executionSource: "BACKEND_SANDBOX",
      userMessage: ok
        ? "UNEXPECTED: backend accepted an invalid contract (should not happen)."
        : `Validator rejected the contract as expected: ${JSON.stringify(data).slice(0, 300)}`,
    };
  }
  if (scenario === "crypto-wrong") {
    // Reaching here means the backend ACCEPTED a wrong-network address.
    return {
      ...base, transactionId: (data as { transactionId?: string }).transactionId ?? null,
      providerReference: (data as { providerRef?: string }).providerRef ?? null, errorCode: "UNEXPECTED_ACCEPT",
      paymentState: "AUTHORIZED", testOutcome: "FAILED", executionSource: "CRYPTO_TESTNET",
      userMessage: "UNEXPECTED: backend accepted a wrong-network address (should not happen).",
    };
  }
  return {
    ...base, transactionId: (data as { transactionId?: string }).transactionId ?? null,
    providerReference: (data as { providerRef?: string; provider_ref?: string }).providerRef
      ?? (data as { provider_ref?: string }).provider_ref ?? null,
    errorCode: null, paymentState: "AUTHORIZED", testOutcome: "PASSED", executionSource: "BACKEND_SANDBOX",
    userMessage: `Sandbox payment authorized: ${JSON.stringify(data).slice(0, 300)}`,
  };
}

/** Map a backend ERROR RESPONSE (or client-side validation throw) to the model.
 *  Expected declines/rejections are PASSED business outcomes. */
export function errorToResult(scenario: ScenarioId, e: unknown, at = now()): UnifiedResult {
  const base = {
    scenarioId: scenario, timestamp: at, sandbox: true as const,
    transactionId: null as string | null, providerReference: null as string | null,
  };
  if (!(e instanceof ApiError)) {
    return {
      ...base, paymentState: "UNKNOWN", testOutcome: "FAILED", executionSource: "BACKEND_SANDBOX",
      errorCode: "NETWORK_UNREACHABLE",
      userMessage: "Backend unreachable (network failure — no response received). Check connectivity, cold start, or a VPN/ad-blocker interfering with the backend origin; CORS failures surface the same way — verify the frontend origin is allow-listed. Nothing was executed; no local result was substituted.",
    };
  }
  const detail = detailText(e);
  const { code } = splitCode(detail);
  switch (e.status) {
    case 401:
      return {
        ...base, paymentState: "UNKNOWN", testOutcome: "FAILED", executionSource: "BACKEND_SANDBOX",
        errorCode: detail.includes("missing bearer token") ? "AUTH_MISSING" : "AUTH_INVALID",
        userMessage: detail.includes("missing bearer token")
          ? "Not signed in (HTTP 401). Paste the operator token from the hybridpay-test Modal Secret and press Sign in — this is an authentication step, not a backend outage."
          : "Token rejected or expired (HTTP 401). Sign in again with the current operator token from the hybridpay-test Modal Secret.",
      };
    case 403:
      return {
        ...base, paymentState: "UNKNOWN", testOutcome: "FAILED", executionSource: "BACKEND_SANDBOX",
        errorCode: "AUTHZ_FORBIDDEN",
        userMessage: `Forbidden (HTTP 403): ${detail}. The signed-in role lacks this capability — an admin token or approved intent may be required.`,
      };
    case 409:
      return {
        ...base, paymentState: "UNKNOWN", testOutcome: "FAILED", executionSource: "BACKEND_SANDBOX",
        errorCode: "IDEMPOTENCY_CONFLICT",
        userMessage: `Idempotency conflict (HTTP 409): ${detail}. The same key was reused with a different payload — change the key for a new payment, reuse it byte-for-byte to replay safely.`,
      };
    case 502:
      return {
        ...base, paymentState: "UNKNOWN", testOutcome: code === "TIMEOUT_UNKNOWN" ? "PASSED" : "FAILED",
        executionSource: "BACKEND_SANDBOX",
        errorCode: code || "BAD_GATEWAY",
        userMessage: code === "TIMEOUT_UNKNOWN"
          ? `Ambiguous timeout — expected sandbox outcome (HTTP 502 ${detail}). Do NOT create a new payment; query the original transaction status or retry with the SAME idempotency key.`
          : `Backend gateway error (HTTP 502): ${detail}.`,
      };
    case 422:
      if (code === "PROVIDER_ERROR") {
        return {
          ...base, paymentState: "DECLINED", testOutcome: "PASSED", executionSource: "BACKEND_SANDBOX",
          errorCode: code,
          userMessage: `Provider declined the payment — expected sandbox outcome (HTTP 422 ${detail}). The backend WAS reached; this is a valid business result, not an outage.`,
        };
      }
      return {
        ...base, paymentState: "REJECTED", testOutcome: "PASSED", executionSource: "BACKEND_SANDBOX",
        errorCode: code || "VALIDATION_FAILED",
        userMessage: `Request rejected as expected (HTTP 422 ${detail}).`,
      };
    case 400:
      return {
        ...base, paymentState: "REJECTED",
        testOutcome: e.detail === undefined || detail.startsWith("Invalid ") || detail.includes("must be") ? "PASSED" : "FAILED",
        executionSource: detail.includes("Backend unreachable") ? "BACKEND_SANDBOX" : "LOCAL_SIMULATION",
        errorCode: code || "CLIENT_VALIDATION",
        userMessage: `Invalid request (HTTP 400 ${detail}). Rejected before any money movement.`,
      };
    default:
      if (e.status === 503 && detail.startsWith("Backend unreachable at")) {
        return {
          ...base, paymentState: "UNKNOWN", testOutcome: "FAILED", executionSource: "BACKEND_SANDBOX",
          errorCode: "NETWORK_UNREACHABLE",
          userMessage: `Backend unreachable (no response from the backend origin). Check connectivity/cold start/VPN; CORS failures surface identically — verify the frontend origin is allow-listed. Nothing was executed; no local result was substituted.`,
        };
      }
      return {
        ...base, paymentState: "UNKNOWN", testOutcome: "FAILED", executionSource: "BACKEND_SANDBOX",
        errorCode: code || `HTTP_${e.status}`,
        userMessage: `Backend error (HTTP ${e.status}): ${detail}.`,
      };
  }
}

/** Deterministic local demo outcomes — used ONLY in explicit Local demo mode,
 *  always labeled LOCAL_SIMULATION, never mixed with backend results. */
export function localDemoResult(scenario: ScenarioId, at = now()): UnifiedResult {
  const table: Record<ScenarioId, { paymentState: PaymentState; userMessage: string }> = {
    "fiat-ok": { paymentState: "AUTHORIZED", userMessage: "Local demo: authorized (no backend involved)." },
    "fiat-fail": { paymentState: "DECLINED", userMessage: "Local demo: declined as expected (no backend involved)." },
    "fiat-timeout": { paymentState: "UNKNOWN", userMessage: "Local demo: ambiguous timeout — in backend mode, query the original instead of retrying." },
    "crypto-wrong": { paymentState: "REJECTED", userMessage: "Local demo: wrong-network address rejected." },
    "contract-bad": { paymentState: "REJECTED", userMessage: "Local demo: validator errors as expected." },
  };
  return {
    scenarioId: scenario, transactionId: null, providerReference: null, errorCode: null,
    paymentState: table[scenario].paymentState, testOutcome: "PASSED",
    executionSource: "LOCAL_SIMULATION", userMessage: table[scenario].userMessage,
    timestamp: at, sandbox: true,
  };
}

/** Card headline: test outcome first, payment state second, source explicit. */
export function headline(r: UnifiedResult): string {
  if (r.errorCode === "NETWORK_UNREACHABLE" || r.errorCode === "AUTH_MISSING" || r.errorCode === "AUTH_INVALID") {
    const what = r.errorCode === "NETWORK_UNREACHABLE" ? "Backend unreachable" : "Authentication required";
    return `Scenario ${r.testOutcome} — ${what}`;
  }
  return `Scenario ${r.testOutcome} — Payment ${r.paymentState}`;
}

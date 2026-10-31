// Temporal activities: the ONLY place provider APIs are called (never inside DB tx, never from terminal).
// Retry policy: on TIMEOUT_UNKNOWN, query the original operation before retry; never fail over to another
// provider while the original transfer might still execute (see PaymentWorkflow).
import { MockAdapter, StripeSandboxAdapter, BtcPayRegtestAdapter, type AdapterContext } from "@hybridpay/adapters";

export function adapterFor(route: string) {
  if (route.startsWith("stripe:")) return new StripeSandboxAdapter(process.env.STRIPE_SECRET_KEY_TEST);
  if (route.startsWith("btcpay:") || route.startsWith("mock:btc")) return new BtcPayRegtestAdapter({ url: process.env.BTCPAY_URL_TEST, apiKey: process.env.BTCPAY_API_KEY_TEST, storeId: process.env.BTCPAY_STORE_ID_TEST });
  return new MockAdapter();
}

export async function authorizeActivity(params: { route: string; ctx: AdapterContext }): Promise<{ providerRef?: string; state: string }> {
  const r = await adapterFor(params.route).authorize(params.ctx);
  if (!r.ok) {
    if (r.code === "TIMEOUT_UNKNOWN") throw Object.assign(new Error("RETRY_QUERY_ORIGINAL"), { retryable: true, originalRef: "pending" });
    throw new Error(`${r.code}: ${r.message}`);
  }
  return { providerRef: r.providerRef, state: r.state };
}

export async function captureActivity(params: { route: string; ctx: AdapterContext; providerRef: string }): Promise<{ state: string }> {
  const r = await adapterFor(params.route).capture(params.ctx, params.providerRef);
  if (!r.ok) {
    if (r.code === "TIMEOUT_UNKNOWN") throw Object.assign(new Error("RETRY_QUERY_ORIGINAL"), { retryable: true });
    throw new Error(`${r.code}: ${r.message}`);
  }
  return { state: r.state };
}

export async function queryOriginalActivity(params: { route: string; providerRef: string }): Promise<{ state: string }> {
  // Provider-specific status query (PaymentIntent retrieve / BTCPay invoice get). Stub returns UNKNOWN to force reconcile path in tests.
  void params;
  return { state: "UNKNOWN" };
}

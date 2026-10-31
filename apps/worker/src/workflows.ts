// PaymentWorkflow (documented; registered with Temporal in main.ts when TEMPORAL_ADDRESS set).
// Pseudo-definition kept framework-light so unit tests can assert the safety rules without a live server:
//
// 1. authorizeActivity (idempotencyKey scoped)
// 2. on TIMEOUT_UNKNOWN -> queryOriginalActivity(ref) -> if UNKNOWN, set instruction UNKNOWN and STOP (reconcile run decides; NO provider failover)
// 3. captureActivity within expiry (auth-capture model) else cancel on expiry race
// 4. duplicate/out-of-order webhook events ignored via inbox(eventId); stale events rejected
export const PAYMENT_WORKFLOW = "PaymentWorkflow";
export const RECONCILE_WORKFLOW = "ReconcileWorkflow";

export function nextStateAfterTimeout(queryState: string): "UNKNOWN" | "AUTHORIZED" | "SETTLED" | "FAILED" {
  if (queryState === "AUTHORIZED" || queryState === "SETTLED" || queryState === "FAILED") return queryState;
  return "UNKNOWN"; // fail to safe, reconcile later; never auto-failover
}

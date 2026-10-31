// Embedded policy evaluator mirroring rego/policy_v1.rego (for dev/test without OPA sidecar).
export type Decision = "ALLOW" | "REVIEW" | "DENY";
export interface PolicyInput {
  amountMinor: bigint; dayTotalMinor: bigint;
  limits: { perTxMinor: bigint; perDayMinor: bigint; reviewCeilingMinor: bigint };
  consentValid: boolean; deviceRevoked: boolean; kycOk: boolean;
}
export const POLICY_VERSION = "v1";
export function decide(input: PolicyInput): { decision: Decision; reason: string } {
  if (!input.consentValid || input.deviceRevoked || !input.kycOk) {
    if (input.deviceRevoked) return { decision: "DENY", reason: "DEVICE_REVOKED" };
    if (!input.consentValid) {
      return input.amountMinor <= input.limits.reviewCeilingMinor
        ? { decision: "REVIEW", reason: "CONSENT_INVALID" }
        : { decision: "DENY", reason: "CONSENT_INVALID" };
    }
    return { decision: "DENY", reason: "KYC_FAIL_CLOSED" };
  }
  if (input.amountMinor <= input.limits.perTxMinor && input.dayTotalMinor + input.amountMinor <= input.limits.perDayMinor)
    return { decision: "ALLOW", reason: "OK" };
  if (input.amountMinor <= input.limits.reviewCeilingMinor) return { decision: "REVIEW", reason: "AMOUNT_OR_LIMIT" };
  return { decision: "DENY", reason: "FAIL_CLOSED" };
}

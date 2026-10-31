// Typed allowlisted DSL for conditional-payment agreements. No eval.
import { createHash } from "node:crypto";

export type Condition =
  | { type: "timeCondition"; notBefore?: string; notAfter: string }
  | { type: "externalEvent"; source: string; eventKey: string; mustMatch: Record<string, string> }
  | { type: "partyApproval"; party: string; minApprovals?: number }
  | { type: "approvalThreshold"; approvers: string[]; threshold: number }
  | { type: "milestone"; milestoneId: string; evidenceRequired: boolean }
  | { type: "disputeWindow"; expiresAt: string };

export interface AgreementTerms {
  version: number;
  denominationAsset: string; // e.g. fiat:EUR
  amountMinor: string; // integer string
  feesMinor: string;
  beneficiaries: { party: string; shareBps: number; destination: string }[];
  conditions: Condition[];
  deadlines: { acceptBy: string; executeBy: string };
  cancelPolicy: string;
  refundPolicy: string;
  disputePolicy: string;
  indexPolicy: IndexPolicy | null;
  consentScope: string;
  executionModel: "pay-after-condition" | "auth-capture" | "approved-payout-product";
}

export interface IndexPolicy {
  series: string; geography: string; basePeriod: string; cutoff: string;
  revisionPolicy: string; frequency: string;
  floor: string | null; perAdjustmentCapBps: number | null; cumulativeCapBps: number | null;
  ceilingMinor: string | null; rounding: "HALF_UP_MINOR";
}

const ALLOWED = new Set(["timeCondition","externalEvent","partyApproval","approvalThreshold","milestone","disputeWindow"]);

export interface Evidence {
  source: string; eventId: string; timestamp: string; expiry: string; payload: Record<string, string>; nonce: string;
}

export function validateTerms(t: AgreementTerms): { ok: boolean; errors: string[] } {
  const errors: string[] = [];
  if (!/^-?\d+$/.test(t.amountMinor)) errors.push("amount must be integer minor units");
  if (!/^-?\d+$/.test(t.feesMinor)) errors.push("fees must be integer minor units");
  const total = t.beneficiaries.reduce((s, b) => s + b.shareBps, 0);
  if (total !== 10000) errors.push("beneficiary shares must sum to 10000 bps");
  for (const c of t.conditions) {
    if (!ALLOWED.has(c.type)) errors.push(`disallowed condition: ${(c as {type:string}).type}`);
    if (c.type === "approvalThreshold" && (c.threshold < 1 || c.threshold > c.approvers.length))
      errors.push("threshold out of range");
    if (c.type === "timeCondition" && c.notBefore && c.notBefore >= c.notAfter)
      errors.push("timeCondition window invalid");
  }
  if (t.executionModel === "approved-payout-product") errors.push("REVIEW: approved-payout-product requires licensed escrow product (not available in MVP)");
  if (t.indexPolicy) {
    const p = t.indexPolicy;
    if (p.perAdjustmentCapBps != null && p.cumulativeCapBps != null && p.perAdjustmentCapBps > p.cumulativeCapBps)
      errors.push("REVIEW: per-adjustment cap exceeds cumulative cap (inconsistent -> REVIEW)");
  }
  return { ok: errors.length === 0, errors };
}

export function versionHash(t: AgreementTerms): string {
  return createHash("sha256").update(JSON.stringify(t)).digest("hex");
}

/** Index formula: raw = base * eligible / baseIdx. Inputs are index LEVELS (not YoY rates). */
export function indexedAmountMinor(o: {
  baseAmountMinor: bigint; baseIndex: number; eligibleIndex: number; policy: IndexPolicy;
}): { rawMinor: bigint; cappedMinor: bigint; appliedCap: string | null } {
  if (!(o.baseIndex > 0 && o.eligibleIndex > 0)) throw new Error("INVALID_INDEX_LEVEL");
  // integer math: raw = base * eligible / base, rounded half-up
  const raw = (o.baseAmountMinor * BigInt(Math.round(o.eligibleIndex * 1e6)) + BigInt(Math.round(o.baseIndex * 1e6)) / 2n) / BigInt(Math.round(o.baseIndex * 1e6));
  let capped = raw;
  let appliedCap: string | null = null;
  const { policy } = o;
  // deflation floor: never go below base unless floor explicitly allows
  if (raw < o.baseAmountMinor && policy.floor === "NO_DEFLECTION_BELOW_BASE") { capped = o.baseAmountMinor; appliedCap = "floor"; }
  if (policy.perAdjustmentCapBps != null) {
    const maxUp = o.baseAmountMinor + (o.baseAmountMinor * BigInt(policy.perAdjustmentCapBps)) / 10000n;
    if (capped > maxUp) { capped = maxUp; appliedCap = "per-adjustment-cap"; }
  }
  if (policy.cumulativeCapBps != null) {
    const maxUp = o.baseAmountMinor + (o.baseAmountMinor * BigInt(policy.cumulativeCapBps)) / 10000n;
    if (capped > maxUp) { capped = maxUp; appliedCap = "cumulative-cap"; }
  }
  if (policy.ceilingMinor != null && capped > BigInt(policy.ceilingMinor)) { capped = BigInt(policy.ceilingMinor); appliedCap = "ceiling"; }
  return { rawMinor: raw, cappedMinor: capped, appliedCap };
}

/** Evaluate conditions against evidence set. Merchant assertion alone never conclusive for milestone/externalEvent. */
export function evaluateConditions(terms: AgreementTerms, evidence: Evidence[], nowIso: string, approvals: Record<string, string[]>): { satisfied: boolean; reasons: string[] } {
  const reasons: string[] = [];
  const byKey = new Map(evidence.filter((e) => e.expiry > nowIso).map((e) => [`${e.source}:${e.eventId}`, e]));
  void byKey;
  for (const c of terms.conditions) {
    if (c.type === "timeCondition") {
      if (nowIso < (c.notBefore ?? "") || nowIso > c.notAfter) { reasons.push("timeCondition not met"); return { satisfied: false, reasons }; }
    } else if (c.type === "externalEvent") {
      const hit = evidence.some((e) => e.expiry > nowIso && e.source === c.source &&
        Object.entries(c.mustMatch).every(([k, v]) => e.payload[k] === v));
      if (!hit) { reasons.push(`externalEvent ${c.source}/${c.eventKey} missing (merchant assertion insufficient)`); return { satisfied: false, reasons }; }
    } else if (c.type === "partyApproval" || c.type === "approvalThreshold") {
      const approvers = c.type === "partyApproval" ? [c.party] : c.approvers;
      const need = c.type === "partyApproval" ? (c.minApprovals ?? 1) : c.threshold;
      const got = approvers.filter((a) => (approvals[a] ?? []).length > 0).length;
      if (got < need) { reasons.push("approvals insufficient"); return { satisfied: false, reasons }; }
    } else if (c.type === "milestone") {
      const hit = evidence.some((e) => e.expiry > nowIso && e.payload["milestoneId"] === c.milestoneId && e.source !== "merchant-assertion");
      if (!hit) { reasons.push("milestone needs non-merchant evidence"); return { satisfied: false, reasons }; }
    } else if (c.type === "disputeWindow") {
      if (nowIso <= c.expiresAt) { reasons.push("dispute window still open"); return { satisfied: false, reasons }; }
    }
  }
  return { satisfied: true, reasons };
}

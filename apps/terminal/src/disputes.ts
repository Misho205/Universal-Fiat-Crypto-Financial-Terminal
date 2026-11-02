export const DISPUTE_CATEGORIES = [
  "unauthorized_payment",
  "incorrect_record",
  "disputed_fee",
  "account_restriction",
  "contractual",
] as const;

export type DisputeCategory = (typeof DISPUTE_CATEGORIES)[number];

export const DISPUTE_CATEGORY_LABELS: Record<DisputeCategory, string> = {
  unauthorized_payment: "Unauthorized payment",
  incorrect_record: "Incorrect record",
  disputed_fee: "Disputed fee",
  account_restriction: "Account restriction",
  contractual: "Contractual disagreement",
};

export const DISPUTE_CATEGORY_SLA_DAYS: Record<DisputeCategory, number> = {
  unauthorized_payment: 15,
  incorrect_record: 30,
  disputed_fee: 30,
  account_restriction: 7,
  contractual: 30,
};

export const DISPUTE_ALLOWED_MIME = [
  "application/pdf",
  "image/png",
  "image/jpeg",
  "text/plain",
  "text/csv",
];

export function disputeStatusHint(state: string): string {
  const map: Record<string, string> = {
    submitted: "Received — waiting for a human reviewer.",
    under_review: "A reviewer is examining your case.",
    escalated: "Escalated to an independent reviewer.",
    decided: "Decided — see the reasoned outcome.",
    remediation: "Approved remediation is being applied (refunds need explicit approval, never automatic).",
    closed: "Closed. The audit trail is retained.",
  };
  return map[state] ?? state;
}

export function isValidCategory(c: string): c is DisputeCategory {
  return (DISPUTE_CATEGORIES as readonly string[]).includes(c);
}

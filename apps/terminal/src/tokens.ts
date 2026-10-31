/** TS mirror of the CSS-variable design tokens (single source: globals.css :root). */
export const tokens = {
  radius: { md: 10, lg: 14, xl: 20, pill: 999 },
  spacing: [0, 4, 8, 12, 16, 24, 32, 48],
  fontSize: { xs: 12, sm: 14, md: 16, lg: 20, xl: 24, hero: 32 },
} as const;

/** Canonical transaction/agreement state → tone mapping (color + text label, never color alone). */
export type StateTone = "ok" | "warn" | "danger" | "info" | "muted";
const STATE_TONE: Record<string, StateTone> = {
  succeeded: "ok", completed: "ok", confirmed: "ok", settled: "ok", refunded: "ok",
  active: "ok", eligible_for_execution: "ok",
  pending: "warn", requested: "warn", conditions_pending: "warn", unknown: "warn",
  review: "warn", disputed: "warn",
  failed: "danger", expired: "danger", canceled: "danger", blocked: "danger", invalid: "danger",
  created: "info", draft: "info",
};
export function stateTone(state: string): StateTone {
  return STATE_TONE[state.toLowerCase()] ?? "muted";
}

"use client";
import * as React from "react";
import type { ModalBackendClient } from "@hybridpay/sdk";
import { Alert, EmptyState, Skeleton } from "./ui/feedback";
import { Button } from "./ui/button";
import { CardTitle } from "./ui/card";
import { Dialog } from "./ui/dialog";
import { Field, Input } from "./ui/field";

export interface DashboardData {
  fiat: { total: number; byState: Record<string, number> };
  evm: { total: number; byState: Record<string, number>; chainId: number };
  agreements: { total: number; byState: Record<string, number> };
}

export function useDashboard(modal: ModalBackendClient, tenant: string, token: string) {
  const [summary, setSummary] = React.useState<DashboardData | null>(null);
  const [busy, setBusy] = React.useState(false);
  const [err, setErr] = React.useState("");
  const refresh = React.useCallback(async () => {
    setBusy(true); setErr("");
    try {
      const s = await modal.dashboardSummary();
      setSummary(s.data as unknown as DashboardData);
    } catch (e) { setErr(String(e)); }
    finally { setBusy(false); }
  }, [modal]);
  React.useEffect(() => { refresh(); }, [tenant, token, refresh]);
  return { summary, busy, err, refresh };
}

export function StatCard({ label, value, sub }: { label: string; value: string | number; sub?: string }) {
  return (
    <div className="rounded-2xl border border-line bg-surface p-4 shadow-card">
      <p className="text-xs font-semibold uppercase tracking-wide text-muted">{label}</p>
      <p className="num mt-1 text-3xl font-extrabold">{value}</p>
      {sub && <p className="muted mt-1 text-xs">{sub}</p>}
    </div>
  );
}

/** Operational alerts derived deterministically from real counts — never invented. */
export function AlertsList({ summary }: { summary: DashboardData | null }) {
  if (!summary) return <Skeleton className="h-16" />;
  const alerts: { tone: "warn" | "danger" | "info"; text: string }[] = [];
  const stuck = (summary.fiat.byState["unknown"] ?? 0) + (summary.evm.byState["pending"] ?? 0);
  const failed = (summary.fiat.byState["failed"] ?? 0);
  const disputed = (summary.agreements.byState["disputed"] ?? 0);
  if (failed > 0) alerts.push({ tone: "danger", text: `${failed} failed fiat payment(s) need review — open Transactions.` });
  if (disputed > 0) alerts.push({ tone: "warn", text: `${disputed} disputed agreement(s) freeze execution — open Agreements.` });
  if (stuck > 0) alerts.push({ tone: "warn", text: `${stuck} ambiguous/pending item(s) — use Check receipt / confirm, never fail over blindly.` });
  if (!alerts.length) alerts.push({ tone: "info", text: "No operational alerts. All tracked items are in terminal or healthy states." });
  return (
    <div className="space-y-2" role="status" aria-label="operational alerts">
      {alerts.map((a, i) => <Alert key={i} tone={a.tone}>{a.text}</Alert>)}
    </div>
  );
}

/**
 * Maker-checker gate for sensitive actions. Maker and checker must be
 * different named actors; the checker step additionally uses the admin
 * bearer token server-side. The Operations view records the decision as a
 * backend approval intent (`POST /api/approvals/intents` → `…/approve`)
 * before executing, so the two-person rule is auditable — and in strict
 * mode (`INSTITUTIONAL_STRICT=1`) the backend refuses execution without it.
 */
export function MakerCheckerDialog({ open, onClose, onApprove, action, target, locale }: {
  open: boolean; onClose: () => void; onApprove: (maker: string, checker: string, reason: string) => void;
  action: string; target: string; locale: "bg" | "en";
}) {
  const [maker, setMaker] = React.useState("");
  const [checker, setChecker] = React.useState("");
  const [reason, setReason] = React.useState("");
  const [err, setErr] = React.useState("");
  React.useEffect(() => { if (open) { setMaker(""); setChecker(""); setReason(""); setErr(""); } }, [open ]);
  const valid = maker.trim() && checker.trim() && reason.trim() && maker.trim() !== checker.trim();
  return (
    <Dialog open={open} onClose={onClose} title={`${locale === "bg" ? "Потвърди" : "Confirm"}: ${action}`}>
      <p className="muted mb-3 text-sm">
        {locale === "bg"
          ? `Maker-checker за ${target}. Въведете различни maker и checker + причина. Изпълнението иска и admin токен.`
          : `Maker-checker for ${target}. Enter distinct maker and checker + reason. Execution also needs the admin token.`}
      </p>
      <Field label="Maker (initiator)" htmlFor="mc-maker"><Input id="mc-maker" value={maker} onChange={(e) => setMaker(e.target.value)} autoComplete="off" /></Field>
      <Field label="Checker (approver, different person)" htmlFor="mc-checker"><Input id="mc-checker" value={checker} onChange={(e) => setChecker(e.target.value)} autoComplete="off" /></Field>
      <Field label={locale === "bg" ? "Причина" : "Reason"} htmlFor="mc-reason"><Input id="mc-reason" value={reason} onChange={(e) => setReason(e.target.value)} autoComplete="off" /></Field>
      {err && <Alert tone="danger" className="mb-2">{err}</Alert>}
      <div className="flex justify-end gap-2">
        <Button variant="secondary" onClick={onClose}>{locale === "bg" ? "Отказ" : "Cancel"}</Button>
        <Button variant="danger" data-autofocus onClick={() => {
          if (!valid) { setErr(locale === "bg" ? "Нужни са различни maker/checker и причина." : "Distinct maker/checker and a reason are required."); return; }
          onApprove(maker.trim(), checker.trim(), reason.trim());
          onClose();
        }}>{locale === "bg" ? "Одобри и изпълни" : "Approve & execute"}</Button>
      </div>
    </Dialog>
  );
}

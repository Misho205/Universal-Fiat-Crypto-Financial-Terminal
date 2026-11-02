"use client";
import * as React from "react";
import { ModalBackendClient, friendlyError } from "@hybridpay/sdk";
import type { Locale } from "./i18n";
import { Alert, EmptyState } from "./components/ui/feedback";
import { Button } from "./components/ui/button";
import { Field, Input, Select, Textarea } from "./components/ui/field";
import { SectionCard } from "./components/workspace";
import { StatusBadge } from "./components/ui/badge";
import {
  DISPUTE_CATEGORIES,
  DISPUTE_CATEGORY_LABELS,
  DISPUTE_CATEGORY_SLA_DAYS,
  disputeStatusHint,
  isValidCategory,
} from "./disputes";

type CaseSummary = { id: string; category: string; state: string; decision: string; slaDue: number };

/* ---------- Customer side: file + track (Personal Workspace) ---------- */
export function CustomerDisputesPanel({ modal, locale }: { modal: ModalBackendClient; locale: Locale }) {
  const [customer, setCustomer] = React.useState("");
  const [category, setCategory] = React.useState<string>("unauthorized_payment");
  const [description, setDescription] = React.useState("");
  const [link, setLink] = React.useState("");
  const [cases, setCases] = React.useState<CaseSummary[]>([]);
  const [detail, setDetail] = React.useState<{ id: string; outcome: string; state: string } | null>(null);
  const [msg, setMsg] = React.useState("");
  const [err, setErr] = React.useState("");
  const [busy, setBusy] = React.useState(false);

  async function refresh() {
    if (!customer.trim()) { setCases([]); return; }
    try {
      const r = await modal.disputeList({ customer: customer.trim(), limit: 50 });
      setCases((r.data as { cases: CaseSummary[] }).cases);
      setErr("");
    } catch (e) { setErr(friendlyError(e, locale)); }
  }

  async function file() {
    if (busy || !customer.trim() || !description.trim() || !link.trim()) return;
    if (!isValidCategory(category)) { setErr("Unknown category"); return; }
    setBusy(true); setErr(""); setMsg("");
    try {
      const r = await modal.disputeCreate({
        customer: customer.trim(), category, description: description.trim(),
        transactionId: link.trim(),
      });
      const d = r.data as { caseId: string; slaDue: number };
      setMsg(`Case ${d.caseId} filed. Review due within ${DISPUTE_CATEGORY_SLA_DAYS[category as keyof typeof DISPUTE_CATEGORY_SLA_DAYS]} days. Filing creates no automatic refund.`);
      setDescription(""); setLink("");
      await refresh();
    } catch (e) { setErr(friendlyError(e, locale)); } finally { setBusy(false); }
  }

  async function open(id: string) {
    try {
      const r = await modal.disputeGet(id);
      const d = r.data as { id: string; outcome: string; state: string };
      setDetail({ id: d.id, outcome: d.outcome ?? "", state: d.state });
    } catch (e) { setErr(friendlyError(e, locale)); }
  }

  return (
    <div>
      <p style={{ color: "#475569", fontSize: 14 }}>
        {locale === "bg" ? "Подайте спор за плащане, такса, ограничение или договор. Всяка жалба се разглежда от човек — AI оценките не решават."
          : "File a dispute about a payment, fee, restriction, or agreement. Every case gets human review — AI scores never decide."}
        {" "}Sandbox only — no real money.
      </p>
      <div className="mb-3 flex flex-wrap items-end gap-2">
        <Field label="Your customer ID"><Input value={customer} onChange={(e) => setCustomer(e.target.value)} autoComplete="off" /></Field>
        <Button onClick={refresh}>Track my cases</Button>
      </div>
      {err && <Alert tone="danger">{err}</Alert>}
      {msg && <Alert tone="ok">{msg}</Alert>}
      <SectionCard title="File a dispute" hint="Link one transaction, restriction, or agreement. Abuse limits apply.">
        <div className="flex flex-wrap items-end gap-2">
          <Field label="Category">
            <Select value={category} onChange={(e) => setCategory(e.target.value)}>
              {DISPUTE_CATEGORIES.map((c) => <option key={c} value={c}>{DISPUTE_CATEGORY_LABELS[c]}</option>)}
            </Select>
          </Field>
          <Field label="Linked payment / case reference"><Input value={link} onChange={(e) => setLink(e.target.value)} placeholder="pay-… / rst-… / pag-…" /></Field>
        </div>
        <Field label="What happened?"><Textarea value={description} onChange={(e) => setDescription(e.target.value)} rows={3} /></Field>
        <Button onClick={file} disabled={busy}>{busy ? "Filing…" : "File dispute"}</Button>
      </SectionCard>
      <SectionCard title="My cases" hint="Status updates appear here with reasoned outcomes.">
        {cases.length === 0 ? <EmptyState title="No cases yet" /> : (
          <ul className="flex flex-col gap-2">
            {cases.map((c) => (
              <li key={c.id} className="flex flex-wrap items-center gap-2 rounded-[10px] border border-line p-2">
                <code className="text-xs">{c.id}</code>
                <StatusBadge state={c.state} />
                <span className="text-sm">{DISPUTE_CATEGORY_LABELS[c.category as keyof typeof DISPUTE_CATEGORY_LABELS] ?? c.category}</span>
                <Button onClick={() => open(c.id)}>Details</Button>
              </li>
            ))}
          </ul>
        )}
        {detail && (
          <div className="mt-2 rounded-[10px] border border-line p-3" aria-live="polite">
            <strong>{detail.id}</strong> — <StatusBadge state={detail.state} />
            <p className="mt-1 text-sm">{disputeStatusHint(detail.state)}</p>
            {detail.outcome && <p className="mt-1 text-sm"><strong>Outcome:</strong> {detail.outcome}</p>}
          </div>
        )}
      </SectionCard>
    </div>
  );
}

/* ---------- Institutional side: review queue (Banking Workspace, role-restricted) ---------- */
export function StaffDisputesPanel({ modal, locale, isAdmin }: { modal: ModalBackendClient; locale: Locale; isAdmin: boolean }) {
  const [cases, setCases] = React.useState<CaseSummary[]>([]);
  const [filter, setFilter] = React.useState("");
  const [reviewer, setReviewer] = React.useState("");
  const [reason, setReason] = React.useState("");
  const [decision, setDecision] = React.useState("upheld");
  const [err, setErr] = React.useState("");
  const [msg, setMsg] = React.useState("");

  async function load() {
    try {
      const r = await modal.disputeList({ state: filter || undefined, limit: 100 });
      setCases((r.data as { cases: CaseSummary[] }).cases);
      setErr("");
    } catch (e) { setErr(friendlyError(e, locale)); }
  }
  React.useEffect(() => { load(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  async function decide(id: string) {
    if (!reviewer.trim() || !reason.trim() || !isAdmin) return;
    setErr(""); setMsg("");
    try {
      await modal.disputeReview(id, reviewer.trim());
      const r = await modal.disputeDecide(id, {
        decision, reason: reason.trim(), reviewer: reviewer.trim(),
        humanBasis: "Staff review of linked records (non-AI basis).",
      });
      setMsg(`Case ${id}: ${(r.data as { decision: string }).decision}. Refunds (if any) need a separate explicit approval — never automatic.`);
      await load();
    } catch (e) { setErr(friendlyError(e, locale)); }
  }

  return (
    <div>
      {!isAdmin && <Alert tone="danger">Reviewing and deciding needs an admin token. Reading the queue works with an operator token.</Alert>}
      {err && <Alert tone="danger">{err}</Alert>}
      {msg && <Alert tone="ok">{msg}</Alert>}
      <div className="mb-3 flex flex-wrap items-end gap-2">
        <Field label="Reviewer identity"><Input value={reviewer} onChange={(e) => setReviewer(e.target.value)} placeholder="rev-…" /></Field>
        <Field label="Decision reason"><Input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="written reason (required)" /></Field>
        <Field label="State filter">
          <Select value={filter} onChange={(e) => setFilter(e.target.value)}>
            <option value="">all</option>
            {["submitted", "under_review", "escalated", "decided", "remediation", "closed"].map((s) => <option key={s} value={s}>{s}</option>)}
          </Select>
        </Field>
        <Button onClick={load}>Reload queue</Button>
      </div>
      {cases.length === 0 ? <EmptyState title="No disputes in queue" /> : (
        <ul className="flex flex-col gap-2">
          {cases.map((c) => (
            <li key={c.id} className="flex flex-wrap items-center gap-2 rounded-[10px] border border-line p-2">
              <code className="text-xs">{c.id}</code>
              <StatusBadge state={c.state} />
              <span className="text-sm">{c.category}</span>
              {c.decision && <StatusBadge state={c.decision} />}
              <Field label="Decision">
                <Select value={decision} onChange={(e) => setDecision(e.target.value)}>
                  <option value="upheld">upheld</option>
                  <option value="partially_upheld">partially upheld</option>
                  <option value="rejected">rejected</option>
                </Select>
              </Field>
              <Button onClick={() => decide(c.id)} disabled={!isAdmin}>Review + decide</Button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

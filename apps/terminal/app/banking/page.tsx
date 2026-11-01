"use client";
import { Landmark, ShieldAlert } from "lucide-react";
import Link from "next/link";
import * as React from "react";
import { friendlyError, type ModalBackendClient } from "@hybridpay/sdk";
import AgreementsPanel from "../../src/AgreementsPanel";
import AssistantPanel from "../../src/AssistantPanel";
import { AlertsList, MakerCheckerDialog, StatCard, useDashboard, type DashboardData } from "../../src/components/banking-shared";
import { FiatPayForm } from "../../src/components/fiat-pay-form";
import { Shell } from "../../src/components/shell";
import { useSession } from "../../src/components/session";
import { TxTable, type TxItem } from "../../src/components/tx-table";
import { Alert, EmptyState, Skeleton } from "../../src/components/ui/feedback";
import { Button } from "../../src/components/ui/button";
import { Card, CardTitle } from "../../src/components/ui/card";
import { StateBarChart } from "../../src/components/ui/chart";
import { Field, Input, Select } from "../../src/components/ui/field";
import { StatusBadge, SandboxBadge } from "../../src/components/ui/badge";
import { Tabs } from "../../src/components/ui/tabs";
import { usePolling } from "../../src/lib/polling";

type View = "overview" | "ops" | "contracts" | "risk" | "admin" | "analytics" | "assistant";

export default function BankingPage() {
  const [locale] = React.useState<"bg" | "en">("en");
  const s = useSession();
  const isAdmin = s.role === "admin";
  const [view, setView] = React.useState<View>("overview");
  const { summary, busy, err, refresh } = useDashboard(s.modal, s.tenant, s.token);
  const t = (bg: string, en: string) => en;

  return (
    <Shell locale={locale} role={s.role}>
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <h1 className="flex items-center gap-2 text-2xl font-extrabold"><Landmark aria-hidden /> {t("Банков работен плот", "Banking Workspace")}</h1>
        <span className="rounded-full bg-[rgb(var(--warn-bg))] px-2.5 py-0.5 text-xs font-bold text-[rgb(var(--warn))]">SANDBOX · ADMIN</span>
      </div>
      {!isAdmin && (
        <Alert tone="warn" className="mb-4">
          {t("Пълен достъп изисква admin токен (cancel/refund/dispute/execute са заключени). Четенето работи с operator.",
             "Full access requires an admin token (cancel/refund/dispute/execute are locked). Reading works with operator.")}
          <SignInRow onSign={(v) => s.signIn(v)} label={t("Вход с admin токен", "Sign in with admin token")} />
        </Alert>
      )}

      <Tabs label="banking views" value={view} onChange={(v) => setView(v as View)} tabs={[
        { id: "overview", label: t("1 Обзор", "1 Overview") },
        { id: "ops", label: t("2 Операции", "2 Operations") },
        { id: "contracts", label: t("3 Договори", "3 Contracts") },
        { id: "risk", label: t("4 Риск", "4 Risk") },
        { id: "admin", label: t("5 Администрация", "5 Admin") },
        { id: "analytics", label: t("6 Анализи", "6 Analytics") },
        { id: "assistant", label: t("✨ Асистент", "✨ Assistant") },
      ]} />

      <div className="mt-4 flex flex-wrap items-end gap-2">
        <Field label={t("Тенант", "Tenant")}>
          <Input value={s.tenant} onChange={(e) => s.setTenant(e.target.value)} autoComplete="off" />
        </Field>
        <Button onClick={refresh} disabled={busy}>{busy ? t("Зарежда…", "Loading…") : t("Обнови", "Refresh")}</Button>
        {err && <Alert tone="danger">{err}</Alert>}
      </div>

      {view === "overview" && <Overview summary={summary} busy={busy} modal={s.modal} locale={locale} />}
      {view === "ops" && <OpsView modal={s.modal} tenant={s.tenant} token={s.token} isAdmin={isAdmin} locale={locale} onChanged={refresh} />}
      {view === "contracts" && (
        <Card>
          <CardTitle>{t("Програмируеми договори", "Programmable contracts")}</CardTitle>
          <p className="muted mb-2 text-sm">{t("Не е ескроу: без резервиране/държане/гарантиране на средства.", "Not escrow: no reservation/holding/guarantee of funds.")}</p>
          <AgreementsPanel modal={s.modal} locale={locale} />
        </Card>
      )}
      {view === "risk" && <RiskView modal={s.modal} locale={locale} isAdmin={isAdmin} />}
      {view === "admin" && <AdminView modal={s.modal} tenant={s.tenant} role={s.role} isAdmin={isAdmin} onSign={(v) => s.signIn(v)} onLogout={s.logout} locale={locale} />}
      {view === "analytics" && <AnalyticsView modal={s.modal} locale={locale} />}
      {view === "assistant" && (
        <Card>
          <AssistantPanel modal={s.modal} locale={locale} />
        </Card>
      )}
    </Shell>
  );
}

function SignInRow({ onSign, label }: { onSign: (v: string) => void; label: string }) {
  const [v, setV] = React.useState("");
  return (
    <span className="mt-2 flex gap-2">
      <input type="password" value={v} onChange={(e) => setV(e.target.value)} placeholder={label} aria-label={label}
        className="rounded-[10px] border border-line bg-surface px-3 py-2" />
      <Button size="sm" onClick={() => { onSign(v); setV(""); }}>{label}</Button>
    </span>
  );
}

/* ---------- 1. Overview ---------- */
function Overview({ summary, busy, modal, locale }: { summary: DashboardData | null; busy: boolean; modal: ModalBackendClient; locale: "bg" | "en" }) {
  const [usage, setUsage] = React.useState("");
  React.useEffect(() => {
    modal.aiUsage().then(
      (r) => { const d = r.data as { calls: number; fallbacks: number }; setUsage(`AI calls: ${d.calls}, fallbacks: ${d.fallbacks}`); },
      () => setUsage("AI usage unavailable"),
    );
  }, [modal]);
  const chartData = (m?: Record<string, number>) => Object.entries(m ?? {}).map(([name, value]) => ({ name, value }));
  return (
    <div className="mt-4 space-y-4">
      <CardTitle>{locale === "bg" ? "Активност и състояние" : "Activity & status"}</CardTitle>
      {busy && !summary ? <div className="grid grid-cols-2 gap-4 md:grid-cols-4"><Skeleton className="h-24" /><Skeleton className="h-24" /><Skeleton className="h-24" /><Skeleton className="h-24" /></div>
        : summary ? (
          <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
            <StatCard label="Fiat" value={summary.fiat.total} sub={Object.entries(summary.fiat.byState).map(([k, v]) => `${k}:${v}`).join(" · ") || "—"} />
            <StatCard label="EVM Sepolia" value={summary.evm.total} sub={`chain ${summary.evm.chainId}`} />
            <StatCard label={locale === "bg" ? "Договори" : "Agreements"} value={summary.agreements.total} sub={Object.entries(summary.agreements.byState).map(([k, v]) => `${k}:${v}`).join(" · ") || "—"} />
            <StatCard label="AI" value={usage.split(",")[0]?.replace("AI calls: ", "") ?? "—"} sub={usage} />
          </div>
        ) : <EmptyState title={locale === "bg" ? "Натиснете Обнови" : "Press Refresh"} />}
      <Card>
        <CardTitle>{locale === "bg" ? "Оперативни аларми" : "Operational alerts"}</CardTitle>
        <AlertsList summary={summary} />
      </Card>
      {summary && summary.fiat.total > 0 && (
        <Card>
          <CardTitle>{locale === "bg" ? "Обем по състояние (фиат)" : "Volume by state (fiat)"}</CardTitle>
          <StateBarChart label="Fiat payments by state" data={chartData(summary.fiat.byState)} />
        </Card>
      )}
    </div>
  );
}

/* ---------- 2. Payment Operations ---------- */
function OpsView({ modal, tenant, token, isAdmin, locale, onChanged }: {
  modal: ModalBackendClient; tenant: string; token: string; isAdmin: boolean; locale: "bg" | "en";
  onChanged: () => void;
}) {
  const [kind, setKind] = React.useState("all");
  const [stateF, setStateF] = React.useState("");
  const [q, setQ] = React.useState("");
  const [page, setPage] = React.useState(0);
  const PAGE_SIZE = 20;
  const [items, setItems] = React.useState<{ kind: string; id: string; state: string; detail: string; ref: string; explorer?: string | null }[]>([]);
  const [total, setTotal] = React.useState(0);
  const [busy, setBusy] = React.useState(false);
  const [err, setErr] = React.useState("");
  const [selected, setSelected] = React.useState<null | { kind: string; id: string }>(null);
  const [autoTrack, setAutoTrack] = React.useState(true);
  const [mc, setMc] = React.useState<null | { paymentId: string; action: "cancel" | "refund" }>(null);
  const [reconOut, setReconOut] = React.useState("");

  async function load(nextPage = page) {
    setBusy(true); setErr("");
    try {
      const r = await modal.dashboardRecent({ kind, state: stateF || undefined, q: q || undefined, limit: PAGE_SIZE, offset: nextPage * PAGE_SIZE });
      const d = r.data as { items: typeof items; pagination?: { total: number } };
      setItems(d.items);
      setTotal(d.pagination?.total ?? d.items.length);
    } catch (e) { setErr(friendly(e)); }
    finally { setBusy(false); }
  }
  function friendly(e: unknown) { return e instanceof Error ? e.message.slice(0, 200) : String(e).slice(0, 200); }
  React.useEffect(() => { load(0); }, [tenant, token]);
  React.useEffect(() => { setSelected(null); }, [tenant]);

  // Live detail with safe polling: backoff, abort on unmount/change, stops on terminal states.
  const polled = usePolling(async () => {
    if (!selected) return null;
    if (selected.kind === "fiat") return (await modal.fiatGet(selected.id)).data as unknown as Record<string, unknown>;
    if (selected.kind === "evm") return (await modal.evmStatus(selected.id)).data as unknown as Record<string, unknown>;
    const d = (await modal.pagGet(selected.id)).data as { state: string; eligible: boolean; conditionStatuses: unknown; disclosure?: string };
    return { state: d.state, eligible: d.eligible, conditionStatuses: d.conditionStatuses } as unknown as Record<string, unknown>;
  }, {
    enabled: !!selected && autoTrack,
    isTerminal: (v) => !!v && typeof v.state === "string" &&
      ["succeeded", "failed", "canceled", "refunded", "confirmed", "expired", "completed"].includes(v.state as string),
  });

  async function makerApprove(maker: string, checker: string, reason: string) {
    if (!mc) return;
    setErr("");
    try {
      // Maker-checker is enforced in the UI (two distinct actors + reason);
      // the backend additionally requires an admin token. Cancel/refund are
      // idempotent: the idempotency key makes safe retries possible.
      void reason;
      const key = `mc-${maker}-${checker}-${Date.now()}`;
      if (mc.action === "cancel") await modal.fiatCancel(mc.paymentId, key);
      else await modal.fiatRefund(mc.paymentId, undefined, key);
      load(); onChanged();
    } catch (e) { setErr(friendly(e)); }
    finally { setMc(null); }
  }

  const unknowns = items.filter((i) => i.state === "unknown");
  return (
    <div className="mt-4 space-y-4">
      <FiatPayInline modal={modal} locale={locale} onChanged={() => { load(); onChanged(); }} />
      <Card>
        <CardTitle>{locale === "bg" ? "Търсене и филтри" : "Search & filters"}</CardTitle>
        <div className="flex flex-wrap gap-2">
          <Field label="Kind"><Select value={kind} onChange={(e) => setKind(e.target.value)}>{["all", "fiat", "evm", "agreement"].map((k) => <option key={k} value={k}>{k}</option>)}</Select></Field>
          <Field label="State"><input value={stateF} onChange={(e) => setStateF(e.target.value)} placeholder="pending…" className="rounded-[10px] border border-line bg-surface px-3 py-2" /></Field>
          <Field label="Search"><input value={q} onChange={(e) => setQ(e.target.value)} placeholder="id / ref…" className="rounded-[10px] border border-line bg-surface px-3 py-2" /></Field>
          <button onClick={() => { setPage(0); load(0); }} disabled={busy} className="self-end rounded-[10px] bg-brand-600 px-4 py-2 text-sm font-semibold text-white">Search</button>
        </div>
        {err && <Alert tone="danger" className="mt-2">{err}</Alert>}
        <div className="mt-2 flex flex-wrap items-center gap-2 text-sm">
          <button disabled={busy || page === 0} onClick={() => { const p = Math.max(0, page - 1); setPage(p); load(p); }} className="rounded-lg border border-line px-3 py-1 font-semibold">← Prev</button>
          <span className="text-muted">Page {page + 1}{total ? ` · ${total} records` : ""}</span>
          <button disabled={busy || items.length < PAGE_SIZE} onClick={() => { const p = page + 1; setPage(p); load(p); }} className="rounded-lg border border-line px-3 py-1 font-semibold">Next →</button>
        </div>
        <div className="mt-3">
          {/* Row-level Cancel/Refund intentionally disabled: all money actions go
              through the maker-checker dialog below (distinct maker+checker), even for admins. */}
          <TxTable items={items} modal={modal} isAdmin={false} locale={locale} onChanged={() => { load(); onChanged(); }}
            onView={(i) => setSelected({ kind: i.kind, id: i.id })} />
          <p className="muted mt-1 text-xs">{locale === "bg" ? "Cancel/Refund са admin и минават през maker-checker по-долу." : "Cancel/Refund are admin-only and go through maker-checker below."}</p>
          {isAdmin && items.some((i) => i.kind === "fiat" && ["pending", "unknown", "succeeded"].includes(i.state)) && (
            <div className="mt-2 flex flex-wrap gap-2">
              {items.filter((i) => i.kind === "fiat" && (i.state === "pending" || i.state === "unknown")).slice(0, 5).map((i) => (
                <button key={i.id} onClick={() => setMc({ paymentId: i.id, action: "cancel" })}
                  className="rounded-lg border border-line px-2 py-1 text-xs font-semibold">Cancel {i.id}</button>
              ))}
              {items.filter((i) => i.kind === "fiat" && i.state === "succeeded").slice(0, 5).map((i) => (
                <button key={i.id} onClick={() => setMc({ paymentId: i.id, action: "refund" })}
                  className="rounded-lg border border-line px-2 py-1 text-xs font-semibold">Refund {i.id}</button>
              ))}
            </div>
          )}
        </div>
        {selected && (
          <div className="mt-2 rounded-xl border border-line p-3">
            <div className="mb-1 flex flex-wrap items-center gap-2">
              <strong className="text-sm">{locale === "bg" ? "Детайл" : "Detail"}: <code className="num">{selected.id}</code></strong>
              <label className="ml-auto flex items-center gap-1 text-xs">
                <input type="checkbox" checked={autoTrack} onChange={(e) => setAutoTrack(e.target.checked)} />
                {locale === "bg" ? "живо проследяване" : "live tracking"}
              </label>
              <button className="text-xs underline" onClick={() => setSelected(null)}>{locale === "bg" ? "затвори" : "close"}</button>
            </div>
            {polled.error && <Alert tone="danger">{polled.error} <button className="underline" onClick={polled.reset}>{locale === "bg" ? "Опитай отново" : "Retry"}</button></Alert>}
            {!polled.data && !polled.error && <p className="muted text-sm" aria-live="polite">{locale === "bg" ? "Зарежда…" : "Loading…"}</p>}
            {polled.data && (
              <>
                <div className="mb-1 flex flex-wrap items-center gap-2 text-sm">
                  <StatusBadge state={String(polled.data.state ?? "?")} />
                  {(polled.data as { provider?: string }).provider && <span className="rounded bg-[rgb(var(--line))] px-1.5 py-0.5 text-[11px] font-semibold">{String((polled.data as { provider?: string }).provider)}</span>}
                  <SandboxBadge />
                  {(polled.data as { idempotencyKey?: string }).idempotencyKey && (
                    <span className="text-xs text-muted" title={locale === "bg" ? "Ключ против дублиране" : "Duplicate-protection key"}>
                      idem: <code>{String((polled.data as { idempotencyKey?: string }).idempotencyKey).slice(0, 24)}…</code>
                    </span>
                  )}
                </div>
                <pre className="ok">{JSON.stringify(polled.data, null, 2).slice(0, 2000)}</pre>
              </>
            )}
          </div>
        )}
      </Card>
      <MakerCheckerDialog open={!!mc} onClose={() => setMc(null)} onApprove={makerApprove}
        action={mc?.action ?? ""} target={mc?.paymentId ?? ""} locale={locale} />
      <Card>
        <CardTitle>Reconciliation status</CardTitle>
        {unknowns.length === 0
          ? <p className="muted text-sm">No UNKNOWN instructions awaiting reconcile.</p>
          : <Alert tone="warn">{`${unknowns.length} UNKNOWN — query the original before retry (no failover).`}</Alert>}
        <div className="mt-2 flex flex-wrap gap-2">
          <Button variant="secondary" disabled={busy} onClick={async () => {
            setBusy(true); setErr(""); setReconOut("");
            try {
              const r = await modal.reconcileRun();
              const d = r.data as { runId: string; unknownFiat: number; openEvm: number; note: string };
              setReconOut(`Reconcile ${d.runId}: ${d.unknownFiat} unknown fiat, ${d.openEvm} open EVM. ${d.note}`);
              load(page); onChanged();
            } catch (e) { setErr(friendly(e)); }
            finally { setBusy(false); }
          }}>Run reconcile sweep</Button>
          <Button variant="secondary" disabled={busy} onClick={async () => {
            try {
              const r = await modal.dashboardExportCsv(kind);
              const blob = new Blob([r.data], { type: "text/csv" });
              const a = document.createElement("a");
              a.href = URL.createObjectURL(blob);
              a.download = "hybridpay-server-report.csv";
              a.click();
              URL.revokeObjectURL(a.href);
            } catch (e) { setErr(friendly(e)); }
          }}>Download server CSV</Button>
        </div>
        {reconOut && <pre className="ok mt-2">{reconOut}</pre>}
      </Card>
    </div>
  );
}

function FiatPayInline({ modal, locale, onChanged }: { modal: ModalBackendClient; locale: "bg" | "en"; onChanged: () => void }) {
  const [amt, setAmt] = React.useState("1000");
  const [busy, setBusy] = React.useState(false);
  const [out, setOut] = React.useState("");
  return (
    <Card>
      <CardTitle>{locale === "bg" ? "Ново фиатно плащане (sandbox)" : "New fiat payment (sandbox)"}</CardTitle>
      <div className="flex flex-wrap items-end gap-2">
        <Field label="EUR minor"><Input value={amt} onChange={(e) => setAmt(e.target.value)} inputMode="numeric" /></Field>
        <Button disabled={busy} onClick={async () => {
          setBusy(true);
          try {
            const c = await modal.fiatCreate({ amountMinor: amt, instructionId: `bank-${Date.now()}`, currency: "EUR" }, `bank-${Date.now()}`);
            const pid = (c.data as { paymentId: string }).paymentId;
            const cf = await modal.fiatConfirm(pid);
            setOut(`${pid} → ${(cf.data as { state: string }).state}`);
            onChanged();
          } catch (e) { setOut(friendlyError(e, locale)); }
          finally { setBusy(false); }
        }}>{locale === "bg" ? "Създай и потвърди" : "Create & confirm"}</Button>
      </div>
      {out && <pre className="ok mt-2">{out}</pre>}
    </Card>
  );
}

/* ---------- 4. Risk & Compliance ---------- */
function RiskView({ modal, locale, isAdmin }: { modal: ModalBackendClient; locale: "bg" | "en"; isAdmin: boolean }) {
  const [items, setItems] = React.useState<TxItem[]>([]);
  const [out, setOut] = React.useState("");
  const [busy, setBusy] = React.useState<string | null>(null);
  React.useEffect(() => {
    modal.dashboardRecent({ limit: 50 }).then(
      (r) => setItems((r.data as { items: TxItem[] }).items),
      () => setItems([]),
    );
  }, [modal]);
  const queue = items.filter((i) => ["failed", "disputed", "unknown"].includes(i.state));
  async function review(id: string, kind: string) {
    setBusy(id);
    try {
      if (kind === "fiat") {
        const g = await modal.fiatGet(id);
        const d = g.data as { state: string };
        const f = await modal.aiFraud({ id, state: d.state });
        const fd = f.data as { advisoryOnly: boolean; validated: boolean; notice: string; data: { riskLevel: string; scoreBps: number; indicators: { code: string; detail: string }[] } };
        setOut(`${id}: ${fd.data.riskLevel} (${fd.data.scoreBps}bps) [${fd.validated ? "validated" : "stub"}]\n${fd.data.indicators.map((x) => `• ${x.code}: ${x.detail}`).join("\n")}\n${fd.notice}`);
      } else {
        setOut(`${id}: kind=${kind} — review the detail view; fraud signals cover fiat metadata.`);
      }
    } catch (e) { setOut(String(e)); }
    finally { setBusy(null); }
  }
  async function escalate(id: string) {
    setBusy(id);
    try {
      // Escalation of an agreement = Dispute action (freezes execution, actor recorded).
      // Fiat items escalate via cancel/refund paths in Operations.
      setOut(locale === "bg"
        ? `${id}: за ескалация отворете Agreements → Dispute като admin (actor се записва в одит историята).`
        : `${id}: to escalate, open Agreements → Dispute as admin (actor is recorded in audit history).`);
    } finally { setBusy(null); }
  }
  return (
    <Card>
      <CardTitle><ShieldAlert className="mr-1 inline" size={18} aria-hidden />{locale === "bg" ? "Риск и съответствие (съветвателно)" : "Risk & compliance (advisory)"}</CardTitle>
      <p className="muted mb-2 text-sm">{locale === "bg"
        ? "AI индикаторите НЕ са сертифицирана детекция на измами. Човек решава. Ескалацията е dispute (admin) с actor в одит историята."
        : "AI indicators are NOT certified fraud detection. A human decides. Escalation is dispute (admin) with actor in audit history."}</p>
      {queue.length === 0 && <EmptyState title={locale === "bg" ? "Няма чакащи за преглед" : "Review queue empty"} body={locale === "bg" ? "failed/disputed/unknown ще се появят тук." : "failed/disputed/unknown items will appear here."} />}
      <ul className="space-y-2">
        {queue.map((i) => (
          <li key={i.id} className="flex flex-wrap items-center gap-2 rounded-lg border border-line p-2">
            <code className="num text-xs">{i.id}</code>
            <span className="text-xs">[{i.kind}] {i.state}</span>
            <Button size="sm" variant="secondary" disabled={busy === i.id} onClick={() => review(i.id, i.kind)}>{locale === "bg" ? "Преглед" : "Review"}</Button>
            {i.kind === "agreement" && <Button size="sm" variant="danger" disabled={!isAdmin || busy === i.id} onClick={() => escalate(i.id)}>Escalate</Button>}
          </li>
        ))}
      </ul>
      {out && <pre className="ok mt-3">{out}</pre>}
    </Card>
  );
}

/* ---------- 5. Institutional Administration ---------- */
function AdminView({ modal, tenant, role, isAdmin, onSign, onLogout, locale }: {
  modal: ModalBackendClient; tenant: string; role: string; isAdmin: boolean;
  onSign: (v: string) => void; onLogout: () => void; locale: "bg" | "en";
}) {
  const [health, setHealth] = React.useState("");
  const [tok, setTok] = React.useState("");
  React.useEffect(() => {
    modal.health().then((r) => setHealth(JSON.stringify(r.data)), (e) => setHealth(String(e)));
  }, [modal]);
  const matrix: [string, string, string][] = [
    ["Read: dashboard, history, agreements, AI", "operator", "admin"],
    ["Create fiat/EVM payments, confirm, submit", "operator", "admin"],
    ["Cancel fiat, refund, agreement execute/cancel/dispute", "— (403)", "admin"],
    ["Webhooks", "service token + HMAC signature", "service token + HMAC signature"],
  ];
  return (
    <div className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-2">
      <Card>
        <CardTitle>{locale === "bg" ? "Организация и тенант" : "Organization & tenant"}</CardTitle>
        <p className="text-sm">{locale === "bg" ? "Тенант" : "Tenant"}: <code>{tenant}</code></p>
        <p className="text-sm">{locale === "bg" ? "Роля" : "Role"}: <code>{role}</code> {isAdmin ? "(admin)" : "(operator)"}</p>
        <p className="text-sm">Backend health: <code>{health}</code></p>
        <div className="mt-2 flex gap-2">
          <input type="password" value={tok} onChange={(e) => setTok(e.target.value)} placeholder="admin token" aria-label="admin token"
            className="rounded-[10px] border border-line bg-surface px-3 py-2" />
          <Button size="sm" onClick={() => { onSign(tok); setTok(""); }}>{locale === "bg" ? "Вход" : "Sign in"}</Button>
          <Button size="sm" variant="secondary" onClick={onLogout}>{locale === "bg" ? "Изход" : "Log out"}</Button>
        </div>
      </Card>
      <Card>
        <CardTitle>RBAC</CardTitle>
        <table className="w-full text-left text-sm">
          <thead><tr><th className="border-b border-line px-2 py-1">Capability</th><th className="border-b border-line px-2 py-1">operator</th><th className="border-b border-line px-2 py-1">admin</th></tr></thead>
          <tbody>{matrix.map((m) => <tr key={m[0]}><td className="border-b border-line px-2 py-1">{m[0]}</td><td className="border-b border-line px-2 py-1">{m[1]}</td><td className="border-b border-line px-2 py-1">{m[2]}</td></tr>)}</tbody>
        </table>
      </Card>
      <Card>
        <CardTitle>{locale === "bg" ? "Потребители и места" : "Users & seats"}</CardTitle>
        <Alert tone="warn">{locale === "bg"
          ? "Няма backend endpoint за потребители/места в sandbox build-а — управлението на достъп е чрез Modal Secrets (API_SHARED_TOKEN / API_ADMIN_TOKEN) и X-Tenant-Id. Заявен API: user invites + seat limits."
          : "No users/seats endpoint in the sandbox backend — access is managed via Modal Secrets (API_SHARED_TOKEN / API_ADMIN_TOKEN) and X-Tenant-Id. Requested API: user invites + seat limits."}</Alert>
      </Card>
      <Card>
        <CardTitle>{locale === "bg" ? "API интеграция и сигурност" : "API integration & security"}</CardTitle>
        <ul className="list-disc space-y-1 pl-5 text-sm">
          <li>Modal Secret: <code>hybridpay-test</code> (стойностите никога не излизат в браузъра)</li>
          <li>Bearer в паметта; CORS allowlist; HMAC webhooks; rate limit {locale === "bg" ? "за AI" : "for AI"}</li>
          <li>Live: <code>OFF</code> (fail-closed без approval файл + live ключове)</li>
          <li><Link className="underline" href="/design-system">{locale === "bg" ? "Дизайн система" : "Design system"}</Link> · <code>docs/modal-deploy-checklist.md</code></li>
        </ul>
      </Card>
    </div>
  );
}

/* ---------- 6. Analytics ---------- */
function AnalyticsView({ modal, locale }: { modal: ModalBackendClient; locale: "bg" | "en" }) {
  const [items, setItems] = React.useState<TxItem[]>([]);
  const [busy, setBusy] = React.useState(false);
  React.useEffect(() => {
    setBusy(true);
    modal.dashboardRecent({ limit: 100 }).then(
      (r) => setItems((r.data as { items: TxItem[] }).items),
      () => setItems([]),
    ).finally(() => setBusy(false));
  }, [modal]);
  const byKind: Record<string, number> = {};
  const byCurr: Record<string, number> = {};
  for (const i of items) {
    byKind[i.kind] = (byKind[i.kind] ?? 0) + 1;
    const m = i.detail.match(/([A-Z]{3})/);
    const c = m ? m[1] : (i.kind === "evm" ? "ETH" : "—");
    byCurr[c] = (byCurr[c] ?? 0) + 1;
  }
  function downloadCsv() {
    const rows = [["kind", "id", "state", "detail", "ref"],
      ...items.map((i) => [i.kind, i.id, i.state, `"${i.detail.replace(/"/g, '""')}"`, i.ref || ""])];
    const blob = new Blob([rows.map((r) => r.join(",")).join("\n")], { type: "text/csv" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "hybridpay-report.csv";
    a.click();
    URL.revokeObjectURL(a.href);
  }
  return (
    <div className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-2">
      <Card>
        <CardTitle>{locale === "bg" ? "Обеми по метод" : "Volume by method"}</CardTitle>
        {busy ? <p>{locale === "bg" ? "Зарежда…" : "Loading…"}</p>
          : items.length ? <StateBarChart label="Payments by kind" data={Object.entries(byKind).map(([name, value]) => ({ name, value }))} />
          : <EmptyState title={locale === "bg" ? "Няма данни" : "No data"} body={locale === "bg" ? "Създайте sandbox плащане, за да се появят метрики. Не се измислят." : "Create a sandbox payment for metrics to appear. Nothing is invented."} />}
      </Card>
      <Card>
        <CardTitle>{locale === "bg" ? "Разпределение по валута" : "Currency distribution"}</CardTitle>
        {items.length ? <StateBarChart label="Payments by currency" data={Object.entries(byCurr).map(([name, value]) => ({ name, value }))} />
          : <EmptyState title={locale === "bg" ? "Няма данни" : "No data"} />}
      </Card>
      <Card>
        <CardTitle>{locale === "bg" ? "Производителност" : "Performance"}</CardTitle>
        <p className="muted text-sm">{locale === "bg"
          ? "p95 <500ms все още се измерва (цел M5) — тук се показват само реални броеве, не измислени латентности."
          : "p95 <500ms is still to be measured (M5 target) — only real counts are shown, no invented latencies."}</p>
        <p className="num mt-2 text-3xl font-extrabold">{items.length}</p>
        <p className="muted text-xs">{locale === "bg" ? "проследени записа" : "tracked records"}</p>
      </Card>
      <Card>
        <CardTitle>Export</CardTitle>
        <p className="muted mb-2 text-sm">CSV of the actually loaded records (client-side export) or the full server history.</p>
        <div className="flex flex-wrap gap-2">
          <Button variant="secondary" disabled={!items.length} onClick={downloadCsv}>
            {`Download CSV (${items.length})`}
          </Button>
          <Button variant="secondary" onClick={async () => {
            const r = await modal.dashboardExportCsv("all");
            const blob = new Blob([r.data], { type: "text/csv" });
            const a = document.createElement("a");
            a.href = URL.createObjectURL(blob);
            a.download = "hybridpay-server-report.csv";
            a.click();
            URL.revokeObjectURL(a.href);
          }}>Download full server CSV</Button>
        </div>
      </Card>
    </div>
  );
}

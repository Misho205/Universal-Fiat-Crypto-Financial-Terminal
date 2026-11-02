"use client";
import { Activity, ArrowLeftRight, BarChart3, Bot, FileCheck2, Settings2, ShieldAlert, Stamp } from "lucide-react";
import Link from "next/link";
import * as React from "react";
import { friendlyError, type ModalBackendClient } from "@hybridpay/sdk";
import AgreementsPanel from "../../src/AgreementsPanel";
import AssistantPanel from "../../src/AssistantPanel";
import { AlertsList, MakerCheckerDialog, useDashboard, type DashboardData } from "../../src/components/banking-shared";
import { Shell } from "../../src/components/shell";
import { useSession } from "../../src/components/session";
import { TxTable, type TxItem } from "../../src/components/tx-table";
import { Alert, EmptyState, Skeleton } from "../../src/components/ui/feedback";
import { Button } from "../../src/components/ui/button";
import { StateBarChart } from "../../src/components/ui/chart";
import { Field, Input, Select } from "../../src/components/ui/field";
import { SandboxBadge, StatusBadge } from "../../src/components/ui/badge";
import { usePolling } from "../../src/lib/polling";
import { AccessGate, EnvBadge, KpiCard, KpiGrid, SectionCard, SectionNav, StatusTimeline, TenantRoleStrip, WorkspaceHeader } from "../../src/components/workspace";

type View = "overview" | "ops" | "contracts" | "approvals" | "risk" | "admin" | "analytics" | "assistant";

const SECTIONS = [
  { id: "overview", label: "Overview", icon: Activity },
  { id: "ops", label: "Operations", icon: ArrowLeftRight },
  { id: "contracts", label: "Contracts", icon: FileCheck2 },
  { id: "approvals", label: "Approvals", icon: Stamp, adminOnly: true },
  { id: "risk", label: "Risk & Compliance", icon: ShieldAlert },
  { id: "admin", label: "Administration", icon: Settings2, adminOnly: true },
  { id: "analytics", label: "Analytics", icon: BarChart3 },
  { id: "assistant", label: "Assistant", icon: Bot },
];

export default function BankingPage() {
  const [locale] = React.useState<"bg" | "en">("en");
  const s = useSession();
  const isAdmin = s.role === "admin";
  const [view, setView] = React.useState<View>("overview");
  const { summary, busy, err, refresh } = useDashboard(s.modal, s.tenant, s.token);
  const t = (bg: string, en: string) => en;

  return (
    <Shell locale={locale} role={s.role}>
      <WorkspaceHeader
        eyebrow={t("Институционален терминал", "Institutional terminal")}
        title={t("Банков работен плот", "Banking Workspace")}
        description={t("Операции, договори, одобрения и одит — само четене за operator, паричните действия искат admin + maker-checker.",
          "Operations, contracts, approvals and audit — read-only for operators; money actions need admin plus maker-checker.")}
        badge={<span className="flex gap-2"><EnvBadge tone="sandbox">SANDBOX</EnvBadge><EnvBadge tone="admin">ADMIN GATED</EnvBadge></span>}
        status={{ tenant: s.tenant, role: s.role, backend: "modal sandbox" }}
      />
      <AccessGate isAdmin={isAdmin} signIn={(v) => s.signIn(v)}
        label={t("Пълен достъп изисква admin токен — cancel/refund/dispute/execute са заключени. Четенето работи с operator.",
          "Full access requires an admin token — cancel/refund/dispute/execute are locked. Reading works with an operator token.")} />

      <SectionNav label="Banking sections" sections={SECTIONS} value={view}
        onChange={(v) => setView(v as View)} lockedAdmin={!isAdmin} />

      <TenantRoleStrip tenant={s.tenant} role={s.role} isAdmin={isAdmin} />
      <div className="mb-3 flex flex-wrap items-end gap-2">
        <Field label={t("Тенант", "Tenant")}>
          <Input value={s.tenant} onChange={(e) => s.setTenant(e.target.value)} autoComplete="off" />
        </Field>
        <Button onClick={refresh} disabled={busy}>{busy ? t("Зарежда…", "Loading…") : t("Обнови", "Refresh")}</Button>
        {err && <Alert tone="danger">{err}</Alert>}
      </div>

      {view === "overview" && <Overview summary={summary} busy={busy} modal={s.modal} locale={locale} />}
      {view === "ops" && <OpsView modal={s.modal} tenant={s.tenant} token={s.token} isAdmin={isAdmin} locale={locale} onChanged={refresh} />}
      {view === "contracts" && (
        <SectionCard title={t("Програмируеми договори", "Programmable contracts")}
          hint={t("Не е ескроу: без резервиране/държане/гарантиране на средства.", "Not escrow: no reservation, holding or guarantee of funds.")}>
          <AgreementsPanel modal={s.modal} locale={locale} />
        </SectionCard>
      )}
      {view === "approvals" && <ApprovalsView modal={s.modal} locale={locale} isAdmin={isAdmin} />}
      {view === "risk" && <RiskView modal={s.modal} locale={locale} isAdmin={isAdmin} />}
      {view === "admin" && <AdminView modal={s.modal} tenant={s.tenant} role={s.role} isAdmin={isAdmin} onSign={(v) => s.signIn(v)} onLogout={s.logout} locale={locale} />}
      {view === "analytics" && <AnalyticsView modal={s.modal} locale={locale} />}
      {view === "assistant" && (
        <SectionCard title={locale === "bg" ? "Асистент (съветвателно)" : "Assistant (advisory)"}
          hint={locale === "bg" ? "Само обяснения — никога не мести средства." : "Explanations only — never moves funds."}>
          <AssistantPanel modal={s.modal} locale={locale} />
        </SectionCard>
      )}
    </Shell>
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
    <div>
      {busy && !summary ? <div className="kpi-grid"><Skeleton className="h-24" /><Skeleton className="h-24" /><Skeleton className="h-24" /><Skeleton className="h-24" /></div>
        : summary ? (
          <KpiGrid>
            <KpiCard label="Fiat payments" value={summary.fiat.total} sub={Object.entries(summary.fiat.byState).map(([k, v]) => `${k}:${v}`).join(" · ") || "—"} />
            <KpiCard label="EVM Sepolia" value={summary.evm.total} sub={`chain ${summary.evm.chainId}`} tone="info" />
            <KpiCard label={locale === "bg" ? "Договори" : "Agreements"} value={summary.agreements.total} sub={Object.entries(summary.agreements.byState).map(([k, v]) => `${k}:${v}`).join(" · ") || "—"} tone="ok" />
            <KpiCard label="AI advisory" value={usage.split(",")[0]?.replace("AI calls: ", "") ?? "—"} sub={usage} />
          </KpiGrid>
        ) : <EmptyState title={locale === "bg" ? "Натиснете Обнови" : "Press Refresh"} />}
      <SectionCard title={locale === "bg" ? "Оперативни аларми" : "Operational alerts"}
        hint={locale === "bg" ? "Детерминистични, от реални броеве — нищо не се измисля." : "Deterministic, from real counts — nothing is invented."}>
        <AlertsList summary={summary} />
      </SectionCard>
      {summary && summary.fiat.total > 0 && (
        <SectionCard title={locale === "bg" ? "Обем по състояние (фиат)" : "Volume by state (fiat)"}>
          <StateBarChart label="Fiat payments by state" data={chartData(summary.fiat.byState)} />
        </SectionCard>
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
      // Institutional path: maker-checker intent first (maker + distinct checker +
      // step-up confirm), then the money call. In strict mode the backend refuses
      // direct calls without an approved intent; in standard mode this still
      // records the two-person decision in the tamper-evident audit trail.
      const action = mc.action === "cancel" ? "fiat.cancel" : "fiat.refund";
      let amount = "0";
      try {
        const g = await modal.fiatGet(mc.paymentId);
        amount = String((g.data as { amountMinor?: string }).amountMinor ?? "0");
      } catch { /* receipt lookup is best-effort for the intent amount */ }
      const stamp = Date.now();
      const created = await modal.approvalCreate(
        { action, targetId: mc.paymentId, amountMinor: amount, maker, reason }, `mc-${stamp}`);
      const intentId = (created.data as { intentId: string }).intentId;
      await modal.approvalApprove(intentId, { checker, confirm: true, reason }, `mc-${stamp}-ap`);
      const key = `mc-${maker}-${checker}-${stamp}`;
      if (mc.action === "cancel") await modal.fiatCancel(mc.paymentId, key);
      else await modal.fiatRefund(mc.paymentId, undefined, key);
      load(); onChanged();
    } catch (e) { setErr(friendly(e)); }
    finally { setMc(null); }
  }

  const unknowns = items.filter((i) => i.state === "unknown");
  return (
    <div>
      <FiatPayInline modal={modal} locale={locale} onChanged={() => { load(); onChanged(); }} />
      <SectionCard title={locale === "bg" ? "Транзакции" : "Transactions"}
        hint={locale === "bg" ? "Търсене, филтри и детайл с живо проследяване." : "Search, filters and detail with live tracking."}>
        <div className="ws-toolbar" role="search">
          <Field label="Kind"><Select value={kind} onChange={(e) => setKind(e.target.value)}>{["all", "fiat", "evm", "agreement"].map((k) => <option key={k} value={k}>{k}</option>)}</Select></Field>
          <Field label="State"><input value={stateF} onChange={(e) => setStateF(e.target.value)} placeholder="pending…" aria-label="Filter by state" /></Field>
          <Field label="Search"><input value={q} onChange={(e) => setQ(e.target.value)} placeholder="id / ref…" aria-label="Search by id or reference" /></Field>
          <button onClick={() => { setPage(0); load(0); }} disabled={busy} className="toolbar-btn rounded-[10px] bg-brand-600 px-4 py-2 text-sm font-semibold text-white">Search</button>
        </div>
        {err && <Alert tone="danger">{err}</Alert>}
        <div className="mb-2 flex flex-wrap items-center gap-2 text-sm">
          <button disabled={busy || page === 0} onClick={() => { const p = Math.max(0, page - 1); setPage(p); load(p); }} className="rounded-lg border border-line px-3 py-1 font-semibold">← Prev</button>
          <span className="text-muted">Page {page + 1}{total ? ` · ${total} records` : ""}</span>
          <button disabled={busy || items.length < PAGE_SIZE} onClick={() => { const p = page + 1; setPage(p); load(p); }} className="rounded-lg border border-line px-3 py-1 font-semibold">Next →</button>
        </div>
        <div className="mt-1">
          {/* Row-level Cancel/Refund intentionally disabled: all money actions go
              through the maker-checker dialog below (distinct maker+checker), even for admins. */}
          <TxTable items={items} modal={modal} isAdmin={false} locale={locale} onChanged={() => { load(); onChanged(); }}
            onView={(i) => setSelected({ kind: i.kind, id: i.id })} />
          <p className="muted mt-1 text-xs">{locale === "bg" ? "Cancel/Refund са admin и минават през maker-checker (intent + двама души)." : "Cancel/Refund are admin-only and go through maker-checker (intent + two people)."}</p>
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
                <StatusTimeline state={String(polled.data.state ?? "?")} />
                <pre className="ok">{JSON.stringify(polled.data, null, 2).slice(0, 2000)}</pre>
              </>
            )}
          </div>
        )}
      </SectionCard>
      <MakerCheckerDialog open={!!mc} onClose={() => setMc(null)} onApprove={makerApprove}
        action={mc?.action ?? ""} target={mc?.paymentId ?? ""} locale={locale} />
      <SectionCard title="Reconciliation status"
        hint="Triage only — re-query receipts/webhooks to resolve UNKNOWN; confirmed ≠ settled.">
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
      </SectionCard>
    </div>
  );
}

function FiatPayInline({ modal, locale, onChanged }: { modal: ModalBackendClient; locale: "bg" | "en"; onChanged: () => void }) {
  const [amt, setAmt] = React.useState("1000");
  const [busy, setBusy] = React.useState(false);
  const [out, setOut] = React.useState("");
  return (
    <SectionCard title={locale === "bg" ? "Ново фиатно плащане (sandbox)" : "New fiat payment (sandbox)"}
      hint={locale === "bg" ? "Създаване + потвърдяване през провайдъра; статусът е авторитетен." : "Create + confirm via the provider; status is authoritative."}>
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
    </SectionCard>
  );
}

/* ---------- 4. Approvals (institutional maker-checker) ---------- */
function ApprovalsView({ modal, locale, isAdmin }: { modal: ModalBackendClient; locale: "bg" | "en"; isAdmin: boolean }) {
  const [intents, setIntents] = React.useState<{ id: string; action: string; targetId?: string; state: string; maker?: string; quorum?: number; approvals?: unknown[] }[]>([]);
  const [err, setErr] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [detail, setDetail] = React.useState<null | { id: string; action: string; targetId: string; amountMinor: string; maker: string; reason: string; state: string; approvals: { checker: string; reason: string; at: number }[]; quorum: number }>(null);
  const [checker, setChecker] = React.useState("");
  const [reason, setReason] = React.useState("");

  async function load() {
    setBusy(true); setErr("");
    try {
      const r = await modal.approvalList();
      setIntents(((r.data as { intents: typeof intents }).intents) ?? []);
    } catch (e) { setErr(e instanceof Error ? e.message.slice(0, 200) : String(e)); }
    finally { setBusy(false); }
  }
  React.useEffect(() => { load(); }, []);
  async function open(id: string) {
    try {
      const r = await modal.approvalGet(id);
      setDetail(r.data as typeof detail);
    } catch (e) { setErr(e instanceof Error ? e.message.slice(0, 200) : String(e)); }
  }
  async function approve() {
    if (!detail || !checker.trim() || !reason.trim()) { setErr("Checker and reason are required."); return; }
    try {
      await modal.approvalApprove(detail.id, { checker: checker.trim(), confirm: true, reason: reason.trim() }, `ui-ap-${Date.now()}`);
      setChecker(""); setReason("");
      await open(detail.id); await load();
    } catch (e) { setErr(e instanceof Error ? e.message.slice(0, 200) : String(e)); }
  }
  return (
    <div>
      <SectionCard title={locale === "bg" ? "Одобрения (maker-checker)" : "Approvals (maker-checker)"}
        hint={locale === "bg"
          ? "Maker създава intent, checker (различен човек) одобрява със step-up. Самодобрението е забранено; високорисковите суми искат кворум."
          : "A maker creates an intent; a different checker approves with step-up. Self-approval is denied; high-risk amounts need a quorum."}
        actions={<Button variant="secondary" size="sm" disabled={busy} onClick={load}>{busy ? "…" : "Refresh"}</Button>}>
        {err && <Alert tone="danger">{err}</Alert>}
        {intents.length === 0 && <EmptyState title="No approval intents" body="Create one from Operations (Cancel/Refund) or via the API." />}
        <ul className="space-y-2">
          {intents.map((i) => (
            <li key={i.id} className="flex flex-wrap items-center gap-2 rounded-lg border border-line p-2">
              <code className="num text-xs">{i.id}</code>
              <span className="text-xs">{i.action}{i.targetId ? ` · ${i.targetId}` : ""}</span>
              <StatusBadge state={i.state} />
              <button className="ml-auto text-xs underline" onClick={() => open(i.id)}>Open</button>
            </li>
          ))}
        </ul>
      </SectionCard>
      {detail && (
        <SectionCard title={`Intent ${detail.id}`}
          hint={`${detail.action} · target ${detail.targetId || "—"} · amount ${detail.amountMinor} minor · quorum ${detail.quorum}`}>
          <dl className="detail-grid">
            <dt>Maker</dt><dd><code>{detail.maker}</code></dd>
            <dt>Reason</dt><dd>{detail.reason}</dd>
            <dt>State</dt><dd><StatusBadge state={detail.state} /></dd>
            <dt>Approvals</dt><dd>{detail.approvals.length ? detail.approvals.map((a) => `${a.checker} (${a.reason})`).join("; ") : "none yet"}</dd>
          </dl>
          {isAdmin && detail.state === "pending" && (
            <div className="mt-2 flex flex-wrap items-end gap-2">
              <Field label="Checker (different person)"><Input value={checker} onChange={(e) => setChecker(e.target.value)} autoComplete="off" /></Field>
              <Field label="Reason"><Input value={reason} onChange={(e) => setReason(e.target.value)} autoComplete="off" /></Field>
              <Button size="sm" onClick={approve}>Approve with step-up</Button>
            </div>
          )}
          {!isAdmin && <p className="muted text-xs">Approving needs the admin token (step-up factor).</p>}
        </SectionCard>
      )}
    </div>
  );
}

/* ---------- 5. Risk & Compliance ---------- */
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
        const fd = f.data as { advisoryOnly: boolean; validated: boolean; notice: string; policyDecision?: { requiresHumanReview: boolean }; data: { riskLevel: string; scoreBps: number; indicators: { code: string; detail: string }[] } };
        setOut(`${id}: ${fd.data.riskLevel} (${fd.data.scoreBps}bps) [${fd.validated ? "validated" : "stub"}] · human review: ${String(fd.policyDecision?.requiresHumanReview ?? true)}\n${fd.data.indicators.map((x) => `• ${x.code}: ${x.detail}`).join("\n")}\n${fd.notice}`);
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
    <SectionCard title={locale === "bg" ? "Риск и съответствие (съветвателно)" : "Risk & compliance (advisory)"}
      hint={locale === "bg"
        ? "AI индикаторите НЕ са сертифицирана детекция на измами. Човек решава. Ескалацията е dispute (admin) с actor в одит историята."
        : "AI indicators are NOT certified fraud detection. A human decides. Escalation is dispute (admin) with actor in audit history."}>
      <ShieldAlert className="sr-only" aria-hidden />
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
    </SectionCard>
  );
}

/* ---------- 6. Institutional Administration ---------- */
function AdminView({ modal, tenant, role, isAdmin, onSign, onLogout, locale }: {
  modal: ModalBackendClient; tenant: string; role: string; isAdmin: boolean;
  onSign: (v: string) => void; onLogout: () => void; locale: "bg" | "en";
}) {
  const [health, setHealth] = React.useState("");
  const [ready, setReady] = React.useState("");
  const [tok, setTok] = React.useState("");
  const [ov, setOv] = React.useState<null | { rolesConfigured: { operator: boolean; admin: boolean }; tenantBinding: { shared: boolean; admin: boolean }; aiRateLimitPerMin: number; totals: { fiat: number; evm: number; agreements: number }; usersSeats: { note: string } }>(null);
  const [ovErr, setOvErr] = React.useState("");
  const [killOut, setKillOut] = React.useState("");
  const [auditOut, setAuditOut] = React.useState("");
  React.useEffect(() => {
    modal.health().then((r) => setHealth(JSON.stringify(r.data)), (e) => setHealth(String(e)));
    modal.ready().then((r) => setReady(JSON.stringify(r.data)), (e) => setReady(String(e)));
  }, [modal]);
  React.useEffect(() => {
    if (!isAdmin) { setOv(null); return; }
    modal.adminOverview().then(
      (r) => { setOv(r.data as typeof ov); setOvErr(""); },
      (e) => { setOv(null); setOvErr(e instanceof Error ? e.message.slice(0, 160) : String(e).slice(0, 160)); },
    );
  }, [modal, isAdmin]);
  const matrix: [string, string, string][] = [
    ["Read: dashboard, history, agreements, AI", "operator", "admin"],
    ["Create fiat/EVM payments, confirm, submit", "operator", "admin"],
    ["Cancel fiat, refund, agreement execute/cancel/dispute", "— (403)", "admin + approved intent*"],
    ["Approve intents (checker, step-up)", "— (403)", "admin, distinct from maker"],
    ["AI kill-switch, elevation, emergency, audit", "— (403)", "admin"],
    ["Webhooks", "service token + HMAC signature", "service token + HMAC signature"],
  ];
  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
      <SectionCard title={locale === "bg" ? "Организация и тенант" : "Organization & tenant"}>
        <p className="text-sm">{locale === "bg" ? "Тенант" : "Tenant"}: <code>{tenant}</code></p>
        <p className="text-sm">{locale === "bg" ? "Роля" : "Role"}: <code>{role}</code> {isAdmin ? "(admin)" : "(operator)"}</p>
        <p className="text-sm">Backend health: <code>{health}</code></p>
        <p className="text-sm">Readiness: <code>{ready.slice(0, 160)}</code></p>
        <div className="mt-2 flex gap-2">
          <input type="password" value={tok} onChange={(e) => setTok(e.target.value)} placeholder="admin token" aria-label="admin token"
            className="rounded-[10px] border border-line bg-surface px-3 py-2" />
          <Button size="sm" onClick={() => { onSign(tok); setTok(""); }}>{locale === "bg" ? "Вход" : "Sign in"}</Button>
          <Button size="sm" variant="secondary" onClick={onLogout}>{locale === "bg" ? "Изход" : "Log out"}</Button>
        </div>
        <p className="muted mt-2 text-xs">* In strict mode (<code>INSTITUTIONAL_STRICT=1</code>) money calls fail closed without an approved intent.</p>
      </SectionCard>
      <SectionCard title="Access matrix (RBAC)">
        <div className="ws-table-wrap" role="region" aria-label="Access matrix" tabIndex={0}>
        <table className="w-full text-left text-sm">
          <thead><tr><th className="border-b border-line px-2 py-1">Capability</th><th className="border-b border-line px-2 py-1">operator</th><th className="border-b border-line px-2 py-1">admin</th></tr></thead>
          <tbody>{matrix.map((m) => <tr key={m[0]}><td className="border-b border-line px-2 py-1">{m[0]}</td><td className="border-b border-line px-2 py-1">{m[1]}</td><td className="border-b border-line px-2 py-1">{m[2]}</td></tr>)}</tbody>
        </table>
        </div>
      </SectionCard>
      <SectionCard title="AI safety switch"
        hint="Emergency disable stops AI routes (503) without interrupting payments.">
        <div className="flex flex-wrap gap-2">
          <Button size="sm" variant="danger" disabled={!isAdmin} onClick={async () => {
            try { const r = await modal.aiKillSwitch(true, "banking UI drill"); setKillOut(JSON.stringify(r.data)); }
            catch (e) { setKillOut(friendlyError(e, locale)); }
          }}>Disable AI</Button>
          <Button size="sm" variant="secondary" disabled={!isAdmin} onClick={async () => {
            try { const r = await modal.aiKillSwitch(false, "restored"); setKillOut(JSON.stringify(r.data)); }
            catch (e) { setKillOut(friendlyError(e, locale)); }
          }}>Re-enable AI</Button>
          <Button size="sm" variant="secondary" disabled={!isAdmin} onClick={async () => {
            try { const r = await modal.aiAudit(); setKillOut(`AI audit chain valid: ${String((r.data as { chainValid: boolean }).chainValid)}`); }
            catch (e) { setKillOut(friendlyError(e, locale)); }
          }}>Verify AI audit chain</Button>
        </div>
        {killOut && <pre className="ok mt-2">{killOut}</pre>}
      </SectionCard>
      <SectionCard title="Security audit trail"
        hint="Tamper-evident, hash-chained. Tenant-scoped; no personal data.">
        <div className="flex flex-wrap gap-2">
          <Button size="sm" variant="secondary" disabled={!isAdmin} onClick={async () => {
            try {
              const r = await modal.securityAudit(20);
              const d = r.data as { chainValid: boolean; events: { event: string; actor: string }[] };
              setAuditOut(`chain valid: ${d.chainValid}\n${d.events.map((e) => `• ${e.event} — ${e.actor}`).join("\n")}`);
            } catch (e) { setAuditOut(friendlyError(e, locale)); }
          }}>Load last 20 security events</Button>
        </div>
        {auditOut && <pre className="ok mt-2">{auditOut}</pre>}
      </SectionCard>
      <SectionCard title="Organization state">
        {ov ? (
          <ul className="space-y-1 text-sm">
            <li>Roles configured — operator: <code>{String(ov.rolesConfigured.operator)}</code>, admin: <code>{String(ov.rolesConfigured.admin)}</code></li>
            <li>Tenant binding — shared: <code>{String(ov.tenantBinding.shared)}</code>, admin: <code>{String(ov.tenantBinding.admin)}</code></li>
            <li>AI rate limit: <code>{ov.aiRateLimitPerMin}/min</code> · tracked records — fiat: <code>{ov.totals.fiat}</code>, evm: <code>{ov.totals.evm}</code>, agreements: <code>{ov.totals.agreements}</code></li>
            <li className="muted">{ov.usersSeats.note}</li>
          </ul>
        ) : (
          <Alert tone="warn">Admin overview unavailable{(ovErr ? `: ${ovErr}` : " (requires admin token)")}. Access is managed via Modal Secrets (API_SHARED_TOKEN / API_ADMIN_TOKEN) and X-Tenant-Id. Requested API: user invites + seat limits.</Alert>
        )}
      </SectionCard>
      <SectionCard title={locale === "bg" ? "API интеграция и сигурност" : "API integration & security"}>
        <ul className="list-disc space-y-1 pl-5 text-sm">
          <li>Modal Secret: <code>hybridpay-test</code> (values never enter the browser)</li>
          <li>Bearer in memory; CORS allowlist; HMAC webhooks; AI rate limit</li>
          <li>Readiness probe: <code>GET /ready</code> (load-balancer friendly)</li>
          <li>Live: <code>OFF</code> (fail-closed without approval file + live keys)</li>
          <li><Link className="underline" href="/design-system">{locale === "bg" ? "Дизайн система" : "Design system"}</Link> · <code>docs/bank-integration-guide.md</code></li>
        </ul>
      </SectionCard>
    </div>
  );
}

/* ---------- 7. Analytics ---------- */
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
    <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
      <SectionCard title={locale === "bg" ? "Обеми по метод" : "Volume by method"}>
        {busy ? <p>{locale === "bg" ? "Зарежда…" : "Loading…"}</p>
          : items.length ? <StateBarChart label="Payments by kind" data={Object.entries(byKind).map(([name, value]) => ({ name, value }))} />
          : <EmptyState title={locale === "bg" ? "Няма данни" : "No data"} body={locale === "bg" ? "Създайте sandbox плащане, за да се появят метрики. Не се измислят." : "Create a sandbox payment for metrics to appear. Nothing is invented."} />}
      </SectionCard>
      <SectionCard title={locale === "bg" ? "Разпределение по валута" : "Currency distribution"}>
        {items.length ? <StateBarChart label="Payments by currency" data={Object.entries(byCurr).map(([name, value]) => ({ name, value }))} />
          : <EmptyState title={locale === "bg" ? "Няма данни" : "No data"} />}
      </SectionCard>
      <SectionCard title={locale === "bg" ? "Производителност" : "Performance"}
        hint={locale === "bg"
          ? "p95 <500ms все още се измерва (цел M5) — тук се показват само реални броеве, не измислени латентности."
          : "p95 <500ms is still to be measured (M5 target) — only real counts are shown, no invented latencies."}>
        <p className="num mt-2 text-3xl font-extrabold">{items.length}</p>
        <p className="muted text-xs">{locale === "bg" ? "проследени записа" : "tracked records"}</p>
      </SectionCard>
      <SectionCard title="Export"
        hint="CSV of the actually loaded records (client-side export) or the full server history.">
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
      </SectionCard>
    </div>
  );
}

// Note: MakerCheckerDialog lives in src/components/banking-shared.tsx and is
// imported by the Operations view above.

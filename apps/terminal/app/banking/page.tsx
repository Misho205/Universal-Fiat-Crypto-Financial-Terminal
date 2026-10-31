"use client";
import { Landmark, ShieldAlert } from "lucide-react";
import * as React from "react";
import AgreementsPanel from "../../src/AgreementsPanel";
import AssistantPanel from "../../src/AssistantPanel";
import { FiatPayForm } from "../../src/components/fiat-pay-form";
import { Shell } from "../../src/components/shell";
import { useSession } from "../../src/components/session";
import { TxTable, type TxItem } from "../../src/components/tx-table";
import { Alert, EmptyState, Skeleton } from "../../src/components/ui/feedback";
import { Button } from "../../src/components/ui/button";
import { Card, CardTitle } from "../../src/components/ui/card";
import { StateBarChart } from "../../src/components/ui/chart";
import { Field, Input, Select } from "../../src/components/ui/field";
import { Tabs } from "../../src/components/ui/tabs";

export default function BankingPage() {
  const [locale, setLocale] = React.useState<"bg" | "en">("bg");
  const s = useSession();
  const isAdmin = s.role === "admin";
  const [view, setView] = React.useState("overview");
  const [summary, setSummary] = React.useState<null | { fiat: { total: number; byState: Record<string, number> }; evm: { total: number; byState: Record<string, number> }; agreements: { total: number; byState: Record<string, number> } }>(null);
  const [items, setItems] = React.useState<TxItem[]>([]);
  const [kind, setKind] = React.useState("all");
  const [busy, setBusy] = React.useState(false);
  const [err, setErr] = React.useState("");
  const t = (bg: string, en: string) => (locale === "bg" ? bg : en);

  async function refresh() {
    setBusy(true); setErr("");
    try {
      const sum = await s.modal.dashboardSummary();
      setSummary((sum.data as { fiat: { total: number; byState: Record<string, number> }; evm: { total: number; byState: Record<string, number> }; agreements: { total: number; byState: Record<string, number> } }));
      const r = await s.modal.dashboardRecent({ kind, limit: 50 });
      setItems((r.data as { items: TxItem[] }).items);
    } catch (e) { setErr(String(e)); }
    finally { setBusy(false); }
  }
  React.useEffect(() => { refresh(); }, [s.tenant, s.token]);

  const chartData = (m?: Record<string, number>) => Object.entries(m ?? {}).map(([name, value]) => ({ name, value }));

  return (
    <Shell locale={locale} role={s.role}>
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <h1 className="flex items-center gap-2 text-2xl font-extrabold"><Landmark aria-hidden /> {t("Банков работен плот", "Banking Workspace")}</h1>
        <span className="rounded-full bg-[rgb(var(--warn-bg))] px-2.5 py-0.5 text-xs font-bold text-[rgb(var(--warn))]">SANDBOX · ADMIN</span>
        <button onClick={() => setLocale(locale === "bg" ? "en" : "bg")} className="ml-auto rounded-full border border-line px-3 py-1 text-sm font-semibold">
          {locale === "bg" ? "EN" : "БГ"}
        </button>
      </div>

      {!isAdmin && (
        <Alert tone="warn" className="mb-4">
          {t("Този workspace изисква admin токен. Въведете го горе в терминала или поискайте достъп. Четенето работи и с operator.",
             "This workspace requires an admin token. Sign in above, or request access. Reading works with operator too.")}
          <div className="mt-2 flex gap-2">
            <input type="password" placeholder="admin token" id="bank-admin" className="rounded-[10px] border border-line bg-surface px-3 py-2" />
            <Button size="sm" onClick={() => { const el = document.getElementById("bank-admin") as HTMLInputElement | null; if (el?.value) { s.signIn(el.value); el.value = ""; } }}>
              {t("Вход", "Sign in")}
            </Button>
          </div>
        </Alert>
      )}

      <Tabs label="banking views" value={view} onChange={setView} tabs={[
        { id: "overview", label: t("Обзор", "Overview") },
        { id: "tx", label: t("Транзакции", "Transactions") },
        { id: "agreements", label: t("Споразумения", "Agreements") },
        { id: "risk", label: t("Риск", "Risk") },
        { id: "assistant", label: t("Асистент", "Assistant") },
      ]} />

      <div className="mt-4 flex flex-wrap items-center gap-2">
        <Field label={t("Тенант", "Tenant")}>
          <Input value={s.tenant} onChange={(e) => s.setTenant(e.target.value)} autoComplete="off" />
        </Field>
        <Field label={t("Вид", "Kind")}>
          <Select value={kind} onChange={(e) => setKind(e.target.value)}>
            {["all", "fiat", "evm", "agreement"].map((k) => <option key={k} value={k}>{k}</option>)}
          </Select>
        </Field>
        <Button onClick={refresh} disabled={busy}>{busy ? t("Зарежда…", "Loading…") : t("Обнови", "Refresh")}</Button>
      </div>
      {err && <Alert tone="danger" className="mt-2">{err}</Alert>}

      {view === "overview" && (
        <div className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-3">
          {busy && !summary ? <><Skeleton className="h-28" /><Skeleton className="h-28" /><Skeleton className="h-28" /></> : summary ? (
            <>
              <Card><CardTitle>Fiat · {summary.fiat.total}</CardTitle>
                {summary.fiat.total ? <StateBarChart label="Fiat by state" data={chartData(summary.fiat.byState)} /> : <EmptyState title={t("Няма фиатни плащания", "No fiat payments")} />}</Card>
              <Card><CardTitle>EVM · {summary.evm.total}</CardTitle>
                {summary.evm.total ? <StateBarChart label="EVM by state" data={chartData(summary.evm.byState)} /> : <EmptyState title={t("Няма EVM плащания", "No EVM payments")} />}</Card>
              <Card><CardTitle>{t("Споразумения", "Agreements")} · {summary.agreements.total}</CardTitle>
                {summary.agreements.total ? <StateBarChart label="Agreements by state" data={chartData(summary.agreements.byState)} /> : <EmptyState title={t("Няма споразумения", "No agreements")} />}</Card>
            </>
          ) : <EmptyState title={t("Натиснете Обнови", "Press Refresh")} />}
        </div>
      )}

      {view === "tx" && (
        <Card>
          <CardTitle>{t("Транзакции", "Transactions")}</CardTitle>
          <TxTable items={items} modal={s.modal} isAdmin={isAdmin} locale={locale} onChanged={refresh} />
          <div className="mt-4"><FiatPayForm modal={s.modal} locale={locale} compact /></div>
        </Card>
      )}

      {view === "agreements" && (
        <Card>
          <AgreementsPanel modal={s.modal} locale={locale} />
        </Card>
      )}

      {view === "risk" && <RiskPanel modal={s.modal} locale={locale} items={items} />}
      {view === "assistant" && (
        <Card>
          <AssistantPanel modal={s.modal} locale={locale} />
        </Card>
      )}
    </Shell>
  );
}

function RiskPanel({ modal, locale, items }: { modal: ReturnType<typeof useSession>["modal"]; locale: "bg" | "en"; items: TxItem[] }) {
  const [out, setOut] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  async function check(id: string) {
    setBusy(true);
    try {
      const r = await modal.aiFraud({ id });
      const d = r.data.data;
      setOut(`${d.riskLevel} (${d.scoreBps}bps) [${r.data.validated ? "validated" : "stub"}]\n${d.indicators.map((i) => `• ${i.code}: ${i.detail}`).join("\n")}\n${r.data.notice}`);
    } catch (e) { setOut(String(e)); }
    finally { setBusy(false); }
  }
  return (
    <Card>
      <CardTitle><ShieldAlert className="mr-1 inline" size={18} aria-hidden />{locale === "bg" ? "Риск индикатори (съветвателни — НЕ са сертифицирана детекция)" : "Risk indicators (advisory — NOT certified detection)"}</CardTitle>
      {items.length === 0 && <EmptyState title={locale === "bg" ? "Няма транзакции за проверка" : "No transactions to check"} />}
      <ul className="space-y-2">
        {items.slice(0, 10).map((i) => (
          <li key={i.id} className="flex items-center gap-2 rounded-lg border border-line p-2">
            <code className="num text-xs">{i.id}</code>
            <Button size="sm" variant="secondary" disabled={busy} onClick={() => check(i.id)}>
              {locale === "bg" ? "Провери" : "Check"}
            </Button>
          </li>
        ))}
      </ul>
      {out && <pre className="ok mt-3">{out}</pre>}
    </Card>
  );
}

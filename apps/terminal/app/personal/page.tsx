"use client";
import { ArrowUpRight, CalendarClock, History, Home, Inbox, Settings as SettingsIcon, Bot, Wallet } from "lucide-react";
import Link from "next/link";
import * as React from "react";
import { friendlyError, type ModalBackendClient } from "@hybridpay/sdk";
import AssistantPanel from "../../src/AssistantPanel";
import DashboardPanel from "../../src/DashboardPanel";
import { Shell } from "../../src/components/shell";
import { useSession } from "../../src/components/session";
import { usePolling, TERMINAL_STATES } from "../../src/lib/polling";
import { Alert, EmptyState } from "../../src/components/ui/feedback";
import { Button } from "../../src/components/ui/button";
import { Field, Input, Select, Textarea } from "../../src/components/ui/field";
import { StatusBadge } from "../../src/components/ui/badge";
import { FIAT_CURRENCIES } from "../../src/currencies";
import { EnvBadge, KpiCard, KpiGrid, SectionCard, SectionNav, TenantRoleStrip, WorkspaceHeader } from "../../src/components/workspace";

type View = "dash" | "send" | "receive" | "program" | "assistant" | "history" | "settings";

const SECTIONS = [
  { id: "dash", label: "Dashboard", icon: Home },
  { id: "send", label: "Send", icon: ArrowUpRight },
  { id: "receive", label: "Receive", icon: Inbox },
  { id: "program", label: "Scheduled", icon: CalendarClock },
  { id: "assistant", label: "Assistant", icon: Bot },
  { id: "history", label: "History", icon: History },
  { id: "settings", label: "Settings", icon: SettingsIcon },
];

export default function PersonalPage() {
  const [locale] = React.useState<"bg" | "en">("en");
  const s = useSession();
  const [view, setView] = React.useState<View>("dash");
  const t = (bg: string, en: string) => en;

  return (
    <Shell locale={locale} role={s.role}>
      <WorkspaceHeader
        eyebrow={t("Личен портфейл", "Personal wallet")}
        title={t("Личен портфейл", "Personal Workspace")}
        description={t("Плащайте и следете вашата активност — само вашите данни, без реални пари.",
          "Pay and track your activity — only your data, no real money.")}
        badge={<EnvBadge tone="sandbox">SANDBOX</EnvBadge>}
        status={{ tenant: s.tenant, role: s.role, backend: "modal sandbox" }}
      />
      <SectionNav label="Personal sections" sections={SECTIONS} value={view} onChange={(v) => setView(v as View)} />
      <TenantRoleStrip tenant={s.tenant} role={s.role} isAdmin={s.role === "admin"} />

      <div className="mb-3 flex flex-wrap items-center gap-2">
        <label className="text-sm font-semibold">{t("Тенант", "Tenant")}: <input value={s.tenant} onChange={(e) => s.setTenant(e.target.value)} autoComplete="off" className="rounded-[10px] border border-line bg-surface px-3 py-2" /></label>
        <Link className="text-sm underline" href="/#order">{t("QR каса (терминал) →", "QR checkout (terminal) →")}</Link>
      </div>

      <div>
        {view === "dash" && <PersonalDash modal={s.modal} locale={locale} />}
        {view === "send" && <SendWizard modal={s.modal} locale={locale} />}
        {view === "receive" && <ReceivePanel modal={s.modal} locale={locale} />}
        {view === "program" && <ProgramWizard modal={s.modal} locale={locale} />}
        {view === "assistant" && (
          <SectionCard title="Assistant (advisory)" hint="Explanations only — never moves funds.">
            <AssistantPanel modal={s.modal} locale={locale} />
          </SectionCard>
        )}
        {view === "history" && <HistoryPanel modal={s.modal} locale={locale} />}
        {view === "settings" && <SettingsPanel onSign={s.signIn} onLogout={s.logout} role={s.role} locale={locale} />}
      </div>
    </Shell>
  );
}

/* ---------- 1. Personal Dashboard ---------- */
function PersonalDash({ modal, locale }: { modal: ModalBackendClient; locale: "bg" | "en" }) {
  const [sum, setSum] = React.useState<null | { fiat: { total: number }; evm: { total: number }; agreements: { total: number } }>(null);
  const [err, setErr] = React.useState("");
  React.useEffect(() => {
    modal.dashboardSummary().then(
      (r) => setSum(r.data as typeof sum),
      (e) => setErr(e instanceof Error ? e.message : String(e)),
    );
  }, [modal]);
  const t = (bg: string, en: string) => (locale === "bg" ? bg : en);
  if (err) return <Alert tone="danger">{err}</Alert>;
  if (!sum) return <p>{t("Зарежда…", "Loading…")}</p>;
  return (
    <div>
      <KpiGrid>
        <KpiCard label={t("Моите фиат плащания", "My fiat payments")} value={sum.fiat.total} icon={Wallet} />
        <KpiCard label={t("Моите крипто плащания", "My crypto payments")} value={sum.evm.total} icon={Wallet} tone="info" />
        <KpiCard label={t("Моите условни плащания", "My scheduled payments")} value={sum.agreements.total} icon={CalendarClock} tone="ok" />
        <KpiCard label={t("Общо записа", "Total records")} value={sum.fiat.total + sum.evm.total + sum.agreements.total} sub={t("само вашият тенант", "your tenant only")} />
      </KpiGrid>
      <SectionCard title={t("Какво можете да правите", "What you can do")}>
        <ul className="list-disc space-y-1 pl-5 text-sm">
          <li>{t("Изпратете тестово плащане (стъпка по стъпка).", "Send a trial payment (step by step).")}</li>
          <li>{t("Създайте заявка за получаване и я споделете.", "Create a receive request and share it.")}</li>
          <li>{t("Направете условно плащане с обикновени думи.", "Make a conditional payment in plain words.")}</li>
        </ul>
      </SectionCard>
      <SectionCard title={t("Последна активност", "Recent activity")}>
        <DashboardPanel modal={modal} locale={locale} />
      </SectionCard>
    </div>
  );
}

/* ---------- 2. Send Payment wizard ---------- */
function SendWizard({ modal, locale }: { modal: ModalBackendClient; locale: "bg" | "en" }) {
  const [step, setStep] = React.useState(0);
  const [to, setTo] = React.useState("merchant-demo");
  const [method, setMethod] = React.useState<"fiat" | "crypto">("fiat");
  const [ccy, setCcy] = React.useState("EUR");
  const [amt, setAmt] = React.useState("1000");
  const [addr, setAddr] = React.useState("bcrt1qdemo000000000000000000000000000000000");
  const [out, setOut] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const t = (bg: string, en: string) => en;
  const steps = [
    { title: "Recipient", hint: "Who gets paid" },
    { title: "Method", hint: "Fiat or crypto" },
    { title: "Amount", hint: "Minor units" },
    { title: "Review", hint: "Check everything" },
    { title: "Status", hint: "Result" },
  ];

  function fieldError(): string {
    if (step === 0 && !to.trim()) return "Recipient is required.";
    if (step === 2) {
      if (!/^\d+$/.test(amt) || amt.length > 16) return "Amount must be an integer in minor units (e.g. 1000).";
      if (method === "crypto" && !addr.startsWith("bcrt1")) return "Address must be a BTC regtest address (bcrt1…).";
    }
    return "";
  }
  function next() {
    const e = fieldError();
    if (e) { setOut(e); return; }
    setOut("");
    setStep(step + 1);
  }

  async function confirm() {
    setBusy(true); setOut("");
    const key = `ui-send-${Date.now()}`;
    try {
      if (method === "fiat") {
        const c = await modal.fiatCreate({ amountMinor: amt, instructionId: `send-${Date.now()}`, currency: ccy }, key);
        const pid = (c.data as { paymentId: string }).paymentId;
        const cf = await modal.fiatConfirm(pid);
        setOut(`Done: ${pid} → ${(cf.data as { state: string }).state} · ${amt} minor ${ccy} → ${to}`);
      } else {
        const c = await modal.cryptoSimulate({ amountMinor: amt, instructionId: `send-${Date.now()}`, address: addr }, key);
        setOut(`Done: ${JSON.stringify((c.data as { transactionId: string; state: string }))}`);
      }
      setStep(4);
    } catch (e) { setOut(friendlyError(e, locale)); }
    finally { setBusy(false); }
  }

  return (
    <SectionCard title="Send payment (testnet/sandbox)"
      hint="Sandbox and testnet only — no real money moves.">
      <ol className="stepper" aria-label="Send progress">
        {steps.map((s, i) => (
          <li key={s.title} aria-current={i === step ? "step" : undefined}
            className={i === step ? "step-now" : i < step ? "step-done" : ""}>
            {i + 1}. {s.title}<small>{s.hint}</small>
          </li>
        ))}
      </ol>
      {step === 0 && <Field label="Recipient (name or label)" error={!to.trim() && out ? out : ""}><Input value={to} onChange={(e) => { setTo(e.target.value); setOut(""); }} autoComplete="off" /></Field>}
      {step === 1 && (
        <Field label="Method">
          <Select value={method} onChange={(e) => setMethod(e.target.value as "fiat" | "crypto")}>
            <option value="fiat">Fiat (sandbox)</option>
            <option value="crypto">Crypto testnet (BTC regtest)</option>
          </Select>
        </Field>
      )}
      {step === 2 && (<>
        {method === "fiat" ? (<>
          <Field label="Currency"><Select value={ccy} onChange={(e) => setCcy(e.target.value)}>
            {FIAT_CURRENCIES.map((c) => <option key={c.code} value={c.code}>{c.code} — {c.nameEn}</option>)}
          </Select></Field>
          <Field label="Amount (minor units, e.g. 1000 = €10.00)" error={fieldError()}><Input value={amt} onChange={(e) => { setAmt(e.target.value); setOut(""); }} inputMode="numeric" /></Field>
        </>) : (<>
          <Field label="Amount (sats)" error={fieldError()}><Input value={amt} onChange={(e) => { setAmt(e.target.value); setOut(""); }} inputMode="numeric" /></Field>
          <Field label="Address (bcrt1… regtest only)" error={fieldError()}><Input value={addr} onChange={(e) => { setAddr(e.target.value); setOut(""); }} /></Field>
        </>)}
      </>)}
      {step === 3 && (
        <Alert tone="info">
          Check before confirming: {amt} {method === "fiat" ? ccy : "sats"}
          {" to "}{method === "fiat" ? to : addr}. Fees: per agreement. Network: sandbox/testnet. No real money.
        </Alert>
      )}
      {step === 4 && <div role="status">{out ? <pre className="ok">{out}</pre> : <p className="muted">Press “Confirm & send”.</p>}</div>}
      {step < 3 && out && <div className="mt-2"><Alert tone="danger">{out}</Alert></div>}
      <div className="mt-3 flex gap-2">
        {step > 0 && step < 4 && <Button variant="secondary" onClick={() => setStep(step - 1)}>Back</Button>}
        {step < 3 && <Button onClick={next}>Next</Button>}
        {step === 3 && <Button disabled={busy} onClick={confirm}>{busy ? "Sending…" : "Confirm & send"}</Button>}
        {step === 4 && <Button variant="secondary" onClick={() => { setStep(0); setOut(""); }}>New payment</Button>}
      </div>
    </SectionCard>
  );
}

/* ---------- 3. Receive ---------- */
function ReceivePanel({ modal, locale }: { modal: ModalBackendClient; locale: "bg" | "en" }) {
  const [to, setTo] = React.useState("0x0000000000000000000000000000000000000000");
  const [out, setOut] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [pid, setPid] = React.useState("");
  const [auto, setAuto] = React.useState(false);
  const t = (bg: string, en: string) => (locale === "bg" ? bg : en);
  async function create() {
    setBusy(true); setOut("");
    try {
      const r = await modal.evmRequest({ to, valueWei: "1000000000000000000", chainId: 11155111 }, `ui-recv-${Date.now()}`);
      const d = r.data as { paymentId: string; to: string; valueWei: string; explorerBase: string };
      setPid(d.paymentId);
      setOut(`${t("Споделете", "Share")}: paymentId=${d.paymentId} → ${d.to} (${d.valueWei} wei, Sepolia)\nExplorer: ${d.explorerBase}… (hash идва след подписване в портфейла)`);
    } catch (e) { setOut(friendlyError(e, locale)); }
    finally { setBusy(false); }
  }
  async function track() {
    if (!pid) return;
    try {
      const r = await modal.evmStatus(pid);
      const d = r.data as { state: string; confirmations: number; confirmationsRequired: number; txHash: string; explorer: string | null; note: string };
      setOut(`${d.state} ${d.confirmations}/${d.confirmationsRequired} · ${d.txHash || t("чака подпис в портфейла", "awaiting wallet signature")}${d.explorer ? `\n${d.explorer}` : ""}\n${d.note ?? ""}`);
    } catch (e) { setOut(friendlyError(e, locale)); }
  }
  const live = usePolling(async () => {
    if (!pid) return null;
    const r = await modal.evmStatus(pid);
    return r.data as { state: string; confirmations: number; confirmationsRequired: number; txHash: string; explorer: string | null };
  }, { enabled: !!pid && auto, isTerminal: (v) => !!v && TERMINAL_STATES.evm.has(v.state) });
  return (
    <SectionCard title={t("Получи плащане (Sepolia заявка)", "Receive payment (Sepolia request)")}
      hint={t("Създава проследима Sepolia заявка. Подписването става във ВАШИЯ портфейл — ние не искаме seed/ключове.", "Creates a tracked Sepolia request. Signing happens in YOUR wallet — we never ask for seeds/keys.")}>
      <Field label={t("Ваш Sepolia адрес (0x…)", "Your Sepolia address (0x…)")}><Input value={to} onChange={(e) => setTo(e.target.value)} /></Field>
      <div className="flex flex-wrap gap-2">
        <Button disabled={busy} onClick={create}>{t("Създай заявка", "Create request")}</Button>
        <Button variant="secondary" disabled={!pid} onClick={track}>{t("Проследи", "Track")}</Button>
        <label className="flex items-center gap-1 text-sm">
          <input type="checkbox" checked={auto} onChange={(e) => setAuto(e.target.checked)} disabled={!pid} />
          {t("живо", "live")}
        </label>
      </div>
      {live.data && (
        <div role="status" aria-live="polite" className="ok mt-2">
          {live.data.state} {live.data.confirmations}/{live.data.confirmationsRequired}
          {live.data.explorer && <> · <a className="underline" href={live.data.explorer} target="_blank" rel="noreferrer">explorer</a></>}
        </div>
      )}
      {live.error && <p className="mt-1 text-sm text-[rgb(var(--danger))]">{live.error} <button className="underline" onClick={live.reset}>{t("Опитай отново", "Retry")}</button></p>}
      {out && <pre className="ok mt-2">{out}</pre>}
      <p className="muted mt-2 text-xs">{t("Фиат заявките не са налични като backend примитив (виж пропуските) — ползвайте EVM заявка или QR касата.", "Fiat requests are not a backend primitive (see gaps) — use an EVM request or the QR checkout.")}</p>
    </SectionCard>
  );
}

/* ---------- 4. Programmable wizard (plain language → DSL) ---------- */
function ProgramWizard({ modal, locale }: { modal: ModalBackendClient; locale: "bg" | "en" }) {
  const [amount, setAmount] = React.useState("2599");
  const [other, setOther] = React.useState("customer");
  const [cond, setCond] = React.useState("approval");
  const [expiry, setExpiry] = React.useState("2030-01-01");
  const [agId, setAgId] = React.useState("");
  const [out, setOut] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const t = (bg: string, en: string) => (locale === "bg" ? bg : en);

  function buildTerms() {
    const conditions: Record<string, unknown>[] = [{ type: "timeCondition", notAfter: `${expiry}T00:00:00Z` }];
    if (cond === "approval") conditions.push({ type: "partyApproval", party: other });
    if (cond === "threshold") conditions.push({ type: "approvalThreshold", approvers: [other, "arbiter"], threshold: 2 });
    if (cond === "delivery") conditions.push({ type: "deliveryConfirmation", deliveryRef: "d1" });
    return {
      amountMinor: amount, currency: "EUR", parties: ["merchant", other],
      conditions, executionModel: "pay-after-condition", expiresAt: `${expiry}T00:00:00Z`,
    };
  }
  function humanTerms() {
    const c = cond === "approval" ? t(`+ одобрение от ${other}`, `+ approval by ${other}`)
      : cond === "threshold" ? t(`+ 2 одобрения (${other} и арбитър)`, `+ 2 approvals (${other} and arbiter)`)
      : t(`+ потвърдена доставка (d1)`, `+ confirmed delivery (d1)`);
    return t(`Ще платя ${amount} minor EUR на ${other} ако: валидно до ${expiry} ${c}. НЕ е ескроу — без задържане на средства.`,
      `I will pay ${amount} minor EUR to ${other} if: valid until ${expiry} ${c}. NOT escrow — no funds held.`);
  }
  async function create() {
    setBusy(true);
    try {
      const r = await modal.pagCreate(buildTerms(), "merchant-op", `ui-pw-${Date.now()}`);
      const id = (r.data as { agreementId: string }).agreementId;
      setAgId(id);
      await modal.pagActivate(id, "merchant-op", "creator");
      setOut(`${t("Създадено и активирано", "Created and activated")}: ${id}\n${humanTerms()}`);
    } catch (e) { setOut(friendlyError(e, locale)); }
    finally { setBusy(false); }
  }
  async function check() {
    if (!agId) return;
    try {
      const r = await modal.pagGet(agId);
      const d = r.data as { state: string; eligible: boolean; conditionStatuses: Record<string, string> };
      setOut(`${d.state} · eligible=${d.eligible}\n${JSON.stringify(d.conditionStatuses)}`);
    } catch (e) { setOut(friendlyError(e, locale)); }
  }
  return (
    <SectionCard title={t("Условно плащане с обикновени думи", "Conditional payment in plain words")}
      hint={t("Договорът е инструкция, не ескроу — изпълнението иска отделен човешки executor.", "The agreement is an instruction set, not escrow — execution needs a separate human executor.")}>
      <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
        <Field label={t("Сума (minor)", "Amount (minor)")}><Input value={amount} onChange={(e) => setAmount(e.target.value)} inputMode="numeric" /></Field>
        <Field label={t("Друга страна", "Other party")}><Input value={other} onChange={(e) => setOther(e.target.value)} /></Field>
        <Field label={t("Условие", "Condition")}>
          <Select value={cond} onChange={(e) => setCond(e.target.value)}>
            <option value="approval">{t("Одобрение от страната", "Approval by the party")}</option>
            <option value="threshold">{t("2 одобрения (страна + арбитър)", "2 approvals (party + arbiter)")}</option>
            <option value="delivery">{t("Потвърдена доставка", "Confirmed delivery")}</option>
          </Select>
        </Field>
        <Field label={t("Валидно до", "Valid until")}><Input type="date" value={expiry} onChange={(e) => setExpiry(e.target.value)} /></Field>
      </div>
      <Alert tone="info" className="my-2">{humanTerms()}</Alert>
      <div className="flex flex-wrap gap-2">
        <Button disabled={busy} onClick={create}>{t("Създай и активирай", "Create & activate")}</Button>
        <Button variant="secondary" disabled={!agId} onClick={check}>{t("Провери състояние", "Check status")}</Button>
      </div>
      {out && <pre className="ok mt-2">{out}</pre>}
    </SectionCard>
  );
}

/* ---------- 6. History ---------- */
function HistoryPanel({ modal, locale }: { modal: ModalBackendClient; locale: "bg" | "en" }) {
  const [q, setQ] = React.useState("");
  const [kind, setKind] = React.useState("all");
  const [page, setPage] = React.useState(0);
  const PAGE_SIZE = 20;
  const [items, setItems] = React.useState<{ kind: string; id: string; state: string; detail: string; ref: string; explorer?: string | null }[]>([]);
  const [total, setTotal] = React.useState(0);
  const [detail, setDetail] = React.useState("");
  const t = (bg: string, en: string) => en;
  async function search(nextPage = page) {
    try {
      const r = await modal.dashboardRecent({ kind, q: q || undefined, limit: PAGE_SIZE, offset: nextPage * PAGE_SIZE });
      const d = r.data as { items: typeof items; pagination?: { total: number } };
      setItems(d.items);
      setTotal(d.pagination?.total ?? d.items.length);
    } catch (e) { setDetail(friendlyError(e, locale)); }
  }
  React.useEffect(() => { search(0); }, []);
  function download(item: (typeof items)[number]) {
    const blob = new Blob([JSON.stringify({ ...item, sandbox: true, exportedAt: new Date().toISOString() }, null, 2)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `receipt-${item.id}.json`;
    a.click();
    URL.revokeObjectURL(a.href);
  }
  return (
    <SectionCard title={t("История", "History")}
      hint={t("Търсене по id/референция; квитанцията е JSON за изтегляне.", "Search by id/reference; the receipt downloads as JSON.")}>
      <div className="ws-toolbar" role="search">
        <Field label="Kind">
          <Select value={kind} onChange={(e) => setKind(e.target.value)} aria-label="kind">
            {["all", "fiat", "evm", "agreement"].map((k) => <option key={k} value={k}>{k}</option>)}
          </Select>
        </Field>
        <Field label="Search"><Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="search by id/ref…" aria-label="search" /></Field>
        <Button variant="secondary" onClick={() => { setPage(0); search(0); }}>Search</Button>
      </div>
      <div className="mb-2 flex flex-wrap items-center gap-2 text-sm">
        <Button size="sm" variant="secondary" disabled={page === 0} onClick={() => { const p = Math.max(0, page - 1); setPage(p); search(p); }}>← Prev</Button>
        <span className="text-xs text-muted">Page {page + 1}{total ? ` · ${total} records` : ""}</span>
        <Button size="sm" variant="secondary" disabled={items.length < PAGE_SIZE} onClick={() => { const p = page + 1; setPage(p); search(p); }}>Next →</Button>
      </div>
      {items.length === 0 && <p className="muted">{t("Няма резултати — направете плащане от таба Изпрати.", "No results — make a payment from the Send tab.")}</p>}
      <ul className="space-y-2">
        {items.map((i) => (
          <li key={i.id} className="rounded-lg border border-line p-2">
            <div className="flex flex-wrap items-center gap-2">
              <code className="num text-xs">{i.id}</code>
              <span className="text-xs">[{i.kind}] {i.state}</span>
              <StatusBadge state={i.state} />
              <span className="ml-auto flex gap-2">
                <Button size="sm" variant="secondary" onClick={async () => {
                  try {
                    if (i.kind === "fiat") setDetail(JSON.stringify((await modal.fiatGet(i.id)).data, null, 2));
                    else if (i.kind === "evm") setDetail(JSON.stringify((await modal.evmStatus(i.id)).data, null, 2));
                    else setDetail(JSON.stringify((await modal.pagGet(i.id)).data, null, 2).slice(0, 2000));
                  } catch (e) { setDetail(friendlyError(e, locale)); }
                }}>{t("Детайл", "Details")}</Button>
                <Button size="sm" variant="secondary" onClick={() => download(i)}>{t("Квитанция (JSON)", "Receipt (JSON)")}</Button>
              </span>
            </div>
            <p className="mt-1 text-xs text-muted">{i.detail}</p>
          </li>
        ))}
      </ul>
      {detail && <pre className="ok mt-2">{detail}</pre>}
    </SectionCard>
  );
}

/* ---------- 7. Settings ---------- */
function SettingsPanel({ onSign, onLogout, role, locale }: {
  onSign: (v: string) => void; onLogout: () => void; role: string; locale: "bg" | "en";
}) {
  const [name, setName] = React.useState("");
  const [tok, setTok] = React.useState("");
  const [wallet, setWallet] = React.useState("");
  const [notif, setNotif] = React.useState(true);
  const t = (bg: string, en: string) => (locale === "bg" ? bg : en);
  async function connectWallet() {
    try {
      const w = (globalThis as unknown as { ethereum?: { request: (a: { method: string }) => Promise<string[]> } }).ethereum;
      if (!w) { setWallet("NO_WALLET"); return; }
      const accs = await w.request({ method: "eth_requestAccounts" });
      setWallet(accs[0] ?? "");
    } catch { setWallet("DENIED"); }
  }
  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
      <SectionCard title={t("Профил", "Profile")} hint={t("Само в тази сесия — не се съхранява на сървъра.", "Session only — never stored on the server.")}>
        <Field label={t("Показвано име", "Display name")}><Input value={name} onChange={(e) => setName(e.target.value)} autoComplete="off" /></Field>
      </SectionCard>
      <SectionCard title={t("Сигурност", "Security")}>
        <p className="text-sm">{t("Роля", "Role")}: <code>{role}</code></p>
        <div className="mt-2 flex gap-2">
          <Input type="password" value={tok} onChange={(e) => setTok(e.target.value)} placeholder="API token" aria-label="API token" />
          <Button size="sm" onClick={() => { onSign(tok); setTok(""); }}>{t("Вход", "Sign in")}</Button>
          <Button size="sm" variant="secondary" onClick={onLogout}>{t("Изход", "Log out")}</Button>
        </div>
        <p className="muted mt-2 text-xs">{t("Токенът живее само в паметта. Изходът го изтрива.", "Token lives in memory only. Logging out erases it.")}</p>
      </SectionCard>
      <SectionCard title={t("Свързани портфейли", "Connected wallets")}>
        {wallet && wallet !== "NO_WALLET" && wallet !== "DENIED"
          ? <p className="text-sm"><code>{wallet}</code> <Button size="sm" variant="secondary" onClick={() => setWallet("")}>{t("Разкачи", "Disconnect")}</Button></p>
          : <Button size="sm" onClick={connectWallet}>{t("Свържи портфейл", "Connect wallet")}</Button>}
        {wallet === "NO_WALLET" && <p className="mt-1 text-sm">{t("Няма портфейл — инсталирайте MetaMask.", "No wallet — install MetaMask.")}</p>}
        <p className="muted mt-2 text-xs">{t("Никога не споделяйте seed фраза или частни ключове. Подписвате само в портфейла.", "Never share seed phrases or private keys. You sign only in the wallet.")}</p>
      </SectionCard>
      <SectionCard title={t("Известия", "Notifications")}>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={notif} onChange={(e) => setNotif(e.target.checked)} />
          {t("Показвай статус съобщения (само в тази сесия)", "Show status messages (this session only)")}
        </label>
      </SectionCard>
    </div>
  );
}

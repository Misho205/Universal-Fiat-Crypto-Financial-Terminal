"use client";
import { User } from "lucide-react";
import Link from "next/link";
import * as React from "react";
import { friendlyError, type ModalBackendClient } from "@hybridpay/sdk";
import AssistantPanel from "../../src/AssistantPanel";
import DashboardPanel from "../../src/DashboardPanel";
import { Shell } from "../../src/components/shell";
import { useSession } from "../../src/components/session";
import { Alert, EmptyState } from "../../src/components/ui/feedback";
import { Button } from "../../src/components/ui/button";
import { Card, CardTitle } from "../../src/components/ui/card";
import { Field, Input, Select, Textarea } from "../../src/components/ui/field";
import { Money } from "../../src/components/ui/money";
import { StatusBadge } from "../../src/components/ui/badge";
import { Tabs } from "../../src/components/ui/tabs";
import { FIAT_CURRENCIES } from "../../src/currencies";

type View = "dash" | "send" | "receive" | "program" | "assistant" | "history" | "settings";

export default function PersonalPage() {
  const [locale, setLocale] = React.useState<"bg" | "en">("bg");
  const s = useSession();
  const [view, setView] = React.useState<View>("dash");
  const t = (bg: string, en: string) => (locale === "bg" ? bg : en);

  return (
    <Shell locale={locale} role={s.role}>
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <h1 className="flex items-center gap-2 text-2xl font-extrabold"><User aria-hidden /> {t("Личен портфейл", "Personal Wallet")}</h1>
        <span className="rounded-full bg-[rgb(var(--info-bg))] px-2.5 py-0.5 text-xs font-bold text-[rgb(var(--info))]">SANDBOX</span>
        <button onClick={() => setLocale(locale === "bg" ? "en" : "bg")} className="ml-auto rounded-full border border-line px-3 py-1 text-sm font-semibold">
          {locale === "bg" ? "EN" : "БГ"}
        </button>
      </div>
      <p className="muted mb-2">{t("Плащайте и следете вашата активност — само вашите данни, без реални пари.", "Pay and track your activity — only your data, no real money.")}</p>

      <div className="mb-3 flex items-center gap-2">
        <label className="text-sm font-semibold">{t("Тенант", "Tenant")}: <input value={s.tenant} onChange={(e) => s.setTenant(e.target.value)} autoComplete="off" className="rounded-[10px] border border-line bg-surface px-3 py-2" /></label>
        <Link className="text-sm underline" href="/#order">{t("QR каса (терминал) →", "QR checkout (terminal) →")}</Link>
      </div>

      <Tabs label="personal views" value={view} onChange={(v) => setView(v as View)} tabs={[
        { id: "dash", label: t("1 Табло", "1 Dashboard") },
        { id: "send", label: t("2 Изпрати", "2 Send") },
        { id: "receive", label: t("3 Получи", "3 Receive") },
        { id: "program", label: t("4 Условни", "4 Scheduled") },
        { id: "assistant", label: t("5 Асистент", "5 Assistant") },
        { id: "history", label: t("6 История", "6 History") },
        { id: "settings", label: t("7 Настройки", "7 Settings") },
      ]} />

      <div className="mt-4">
        {view === "dash" && <PersonalDash modal={s.modal} locale={locale} />}
        {view === "send" && <SendWizard modal={s.modal} locale={locale} />}
        {view === "receive" && <ReceivePanel modal={s.modal} locale={locale} />}
        {view === "program" && <ProgramWizard modal={s.modal} locale={locale} />}
        {view === "assistant" && <Card><AssistantPanel modal={s.modal} locale={locale} /></Card>}
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
  const cards = [
    { label: t("Моите фиат плащания", "My fiat payments"), value: sum.fiat.total },
    { label: t("Моите крипто плащания", "My crypto payments"), value: sum.evm.total },
    { label: t("Моите условни плащания", "My scheduled payments"), value: sum.agreements.total },
  ];
  return (
    <div>
      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        {cards.map((c) => (
          <Card key={c.label}><CardTitle>{c.label}</CardTitle><p className="num text-3xl font-extrabold">{c.value}</p></Card>
        ))}
      </div>
      <Card>
        <CardTitle>{t("Какво можете да правите", "What you can do")}</CardTitle>
        <ul className="list-disc space-y-1 pl-5 text-sm">
          <li>{t("Изпратете тестово плащане (стъпка по стъпка).", "Send a trial payment (step by step).")}</li>
          <li>{t("Създайте заявка за получаване и я споделете.", "Create a receive request and share it.")}</li>
          <li>{t("Направете условно плащане с обикновени думи.", "Make a conditional payment in plain words.")}</li>
        </ul>
      </Card>
      <Card>
        <CardTitle>{t("Последна активност", "Recent activity")}</CardTitle>
        <DashboardPanel modal={modal} locale={locale} />
      </Card>
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
  const t = (bg: string, en: string) => (locale === "bg" ? bg : en);
  const steps = [t("1 Получател", "1 Recipient"), t("2 Метод", "2 Method"), t("3 Сума", "3 Amount"), t("4 Преглед", "4 Review"), t("5 Статус", "5 Status")];

  async function confirm() {
    setBusy(true); setOut("");
    const key = `ui-send-${Date.now()}`;
    try {
      if (method === "fiat") {
        const c = await modal.fiatCreate({ amountMinor: amt, instructionId: `send-${Date.now()}`, currency: ccy }, key);
        const pid = (c.data as { paymentId: string }).paymentId;
        const cf = await modal.fiatConfirm(pid);
        setOut(`${t("Готово", "Done")}: ${pid} → ${(cf.data as { state: string }).state} · ${amt} minor ${ccy} → ${to}`);
      } else {
        const c = await modal.cryptoSimulate({ amountMinor: amt, instructionId: `send-${Date.now()}`, address: addr }, key);
        setOut(`${t("Готово", "Done")}: ${JSON.stringify((c.data as { transactionId: string; state: string }))}`);
      }
      setStep(4);
    } catch (e) { setOut(friendlyError(e, locale)); }
    finally { setBusy(false); }
  }

  return (
    <Card>
      <CardTitle>{t("Изпрати плащане (testnet/sandbox)", "Send payment (testnet/sandbox)")}</CardTitle>
      <ol className="mb-3 flex flex-wrap gap-2" aria-label={t("Стъпки", "Steps")}>
        {steps.map((s, i) => (
          <li key={s} aria-current={i === step ? "step" : undefined}
            className={`rounded-full px-3 py-1 text-xs font-bold ${i === step ? "bg-brand-900 text-white dark:bg-brand-100" : "border border-line"}`}>{s}</li>
        ))}
      </ol>
      {step === 0 && <Field label={t("Получател (име или етикет)", "Recipient (name or label)")}><Input value={to} onChange={(e) => setTo(e.target.value)} autoComplete="off" /></Field>}
      {step === 1 && (
        <Field label={t("Метод", "Method")}>
          <Select value={method} onChange={(e) => setMethod(e.target.value as "fiat" | "crypto")}>
            <option value="fiat">{t("Фиат (пясъчник)", "Fiat (sandbox)")}</option>
            <option value="crypto">{t("Крипто testnet (BTC regtest)", "Crypto testnet (BTC regtest)")}</option>
          </Select>
        </Field>
      )}
      {step === 2 && (<>
        {method === "fiat" ? (<>
          <Field label={t("Валута", "Currency")}><Select value={ccy} onChange={(e) => setCcy(e.target.value)}>
            {FIAT_CURRENCIES.map((c) => <option key={c.code} value={c.code}>{c.code} — {locale === "bg" ? c.nameBg : c.nameEn}</option>)}
          </Select></Field>
          <Field label={t("Сума (minor units, напр. 1000 = €10.00)", "Amount (minor units, e.g. 1000 = €10.00)")}><Input value={amt} onChange={(e) => setAmt(e.target.value)} inputMode="numeric" /></Field>
        </>) : (<>
          <Field label={t("Сума (sats)", "Amount (sats)")}><Input value={amt} onChange={(e) => setAmt(e.target.value)} inputMode="numeric" /></Field>
          <Field label={t("Адрес (само bcrt1… regtest)", "Address (bcrt1… regtest only)")}><Input value={addr} onChange={(e) => setAddr(e.target.value)} /></Field>
        </>)}
      </>)}
      {step === 3 && (
        <Alert tone="info">
          {t("Проверете преди потвърждение", "Check before confirming")}: {amt} {method === "fiat" ? ccy : "sats"}
          {t(" към ", " to ")}{method === "fiat" ? to : addr}. {t("Такси: по споразумението. Мрежа: sandbox/testnet. Без реални пари.", "Fees: per agreement. Network: sandbox/testnet. No real money.")}
        </Alert>
      )}
      {step === 4 && <div role="status">{out ? <pre className="ok">{out}</pre> : <p className="muted">{t("Натиснете „Потвърди и изпрати“.", "Press “Confirm & send”.")}</p>}</div>}
      <div className="mt-3 flex gap-2">
        {step > 0 && step < 4 && <Button variant="secondary" onClick={() => setStep(step - 1)}>{t("Назад", "Back")}</Button>}
        {step < 3 && <Button onClick={() => setStep(step + 1)}>{t("Напред", "Next")}</Button>}
        {step === 3 && <Button disabled={busy} onClick={confirm}>{busy ? t("Изпраща…", "Sending…") : t("Потвърди и изпрати", "Confirm & send")}</Button>}
        {step === 4 && <Button variant="secondary" onClick={() => { setStep(0); setOut(""); }}>{t("Ново плащане", "New payment")}</Button>}
      </div>
    </Card>
  );
}

/* ---------- 3. Receive ---------- */
function ReceivePanel({ modal, locale }: { modal: ModalBackendClient; locale: "bg" | "en" }) {
  const [to, setTo] = React.useState("bcrt1qdemo000000000000000000000000000000000");
  const [out, setOut] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [st, setSt] = React.useState("");
  const [pid, setPid] = React.useState("");
  const t = (bg: string, en: string) => (locale === "bg" ? bg : en);
  async function create() {
    setBusy(true); setOut("");
    try {
      const r = await modal.evmRequest({ to, valueWei: "1000000000000000", chainId: 11155111 }, `ui-recv-${Date.now()}`);
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
      const d = r.data as { state: string; confirmations: number; confirmationsRequired: number; txHash: string; explorer: string | null };
      setSt(`${d.state} ${d.confirmations}/${d.confirmationsRequired} · ${d.txHash || t("чака подпис в портфейла", "awaiting wallet signature")}${d.explorer ? `\n${d.explorer}` : ""}`);
    } catch (e) { setSt(friendlyError(e, locale)); }
  }
  return (
    <Card>
      <CardTitle>{t("Получи плащане (Sepolia заявка)", "Receive payment (Sepolia request)")}</CardTitle>
      <p className="muted mb-2 text-sm">{t("Създава проследима Sepolia заявка. Подписването става във ВАШИЯ портфейл — ние не искаме seed/ключове.", "Creates a tracked Sepolia request. Signing happens in YOUR wallet — we never ask for seeds/keys.")}</p>
      <Field label={t("Ваш Sepolia адрес (0x…)", "Your Sepolia address (0x…)")}><Input value={to} onChange={(e) => setTo(e.target.value)} /></Field>
      <div className="flex gap-2">
        <Button disabled={busy} onClick={create}>{t("Създай заявка", "Create request")}</Button>
        <Button variant="secondary" disabled={!pid} onClick={track}>{t("Проследи", "Track")}</Button>
      </div>
      {out && <pre className="ok mt-2">{out}</pre>}
      {st && <pre className="ok mt-2">{st}</pre>}
      <p className="muted mt-2 text-xs">{t("Фиат заявките не са налични като backend примитив (виж пропуските) — ползвайте EVM заявка или QR касата.", "Fiat requests are not a backend primitive (see gaps) — use an EVM request or the QR checkout.")}</p>
    </Card>
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
    <Card>
      <CardTitle>{t("Условно плащане с обикновени думи", "Conditional payment in plain words")}</CardTitle>
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
      <div className="flex gap-2">
        <Button disabled={busy} onClick={create}>{t("Създай и активирай", "Create & activate")}</Button>
        <Button variant="secondary" disabled={!agId} onClick={check}>{t("Провери състояние", "Check status")}</Button>
      </div>
      {out && <pre className="ok mt-2">{out}</pre>}
    </Card>
  );
}

/* ---------- 6. History ---------- */
function HistoryPanel({ modal, locale }: { modal: ModalBackendClient; locale: "bg" | "en" }) {
  const [q, setQ] = React.useState("");
  const [kind, setKind] = React.useState("all");
  const [items, setItems] = React.useState<{ kind: string; id: string; state: string; detail: string; ref: string; explorer?: string | null }[]>([]);
  const [detail, setDetail] = React.useState("");
  const t = (bg: string, en: string) => (locale === "bg" ? bg : en);
  async function search() {
    try {
      const r = await modal.dashboardRecent({ kind, q: q || undefined, limit: 50 });
      setItems((r.data as { items: typeof items }).items);
    } catch (e) { setDetail(friendlyError(e, locale)); }
  }
  React.useEffect(() => { search(); }, []);
  function download(item: (typeof items)[number]) {
    const blob = new Blob([JSON.stringify({ ...item, sandbox: true, exportedAt: new Date().toISOString() }, null, 2)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `receipt-${item.id}.json`;
    a.click();
    URL.revokeObjectURL(a.href);
  }
  return (
    <Card>
      <CardTitle>{t("История", "History")}</CardTitle>
      <div className="mb-2 flex flex-wrap gap-2">
        <Select value={kind} onChange={(e) => setKind(e.target.value)} aria-label="kind">
          {["all", "fiat", "evm", "agreement"].map((k) => <option key={k} value={k}>{k}</option>)}
        </Select>
        <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("търси по id/ref…", "search by id/ref…")} aria-label="search" />
        <Button variant="secondary" onClick={search}>{t("Търси", "Search")}</Button>
      </div>
      {items.length === 0 && <p className="muted">{t("Няма резултати — направете плащане от таба Изпрати.", "No results — make a payment from the Send tab.")}</p>}
      <ul className="space-y-2">
        {items.map((i) => (
          <li key={i.id} className="rounded-lg border border-line p-2">
            <div className="flex flex-wrap items-center gap-2">
              <code className="num text-xs">{i.id}</code>
              <span className="text-xs">[{i.kind}] {i.state}</span>
              <Button size="sm" variant="secondary" onClick={async () => {
                try {
                  if (i.kind === "fiat") setDetail(JSON.stringify((await modal.fiatGet(i.id)).data, null, 2));
                  else if (i.kind === "evm") setDetail(JSON.stringify((await modal.evmStatus(i.id)).data, null, 2));
                  else setDetail(JSON.stringify((await modal.pagGet(i.id)).data, null, 2).slice(0, 2000));
                } catch (e) { setDetail(friendlyError(e, locale)); }
              }}>{t("Детайл", "Details")}</Button>
              <Button size="sm" variant="secondary" onClick={() => download(i)}>{t("Квитанция (JSON)", "Receipt (JSON)")}</Button>
            </div>
            <p className="mt-1 text-xs text-muted">{i.detail}</p>
          </li>
        ))}
      </ul>
      {detail && <pre className="ok mt-2">{detail}</pre>}
    </Card>
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
      <Card>
        <CardTitle>{t("Профил", "Profile")}</CardTitle>
        <p className="muted mb-2 text-xs">{t("Само в тази сесия — не се съхранява на сървъра.", "Session only — never stored on the server.")}</p>
        <Field label={t("Показвано име", "Display name")}><Input value={name} onChange={(e) => setName(e.target.value)} autoComplete="off" /></Field>
      </Card>
      <Card>
        <CardTitle>{t("Сигурност", "Security")}</CardTitle>
        <p className="text-sm">{t("Роля", "Role")}: <code>{role}</code></p>
        <div className="mt-2 flex gap-2">
          <Input type="password" value={tok} onChange={(e) => setTok(e.target.value)} placeholder="API token" aria-label="API token" />
          <Button size="sm" onClick={() => { onSign(tok); setTok(""); }}>{t("Вход", "Sign in")}</Button>
          <Button size="sm" variant="secondary" onClick={onLogout}>{t("Изход", "Log out")}</Button>
        </div>
        <p className="muted mt-2 text-xs">{t("Токенът живее само в паметта. Изходът го изтрива.", "Token lives in memory only. Logging out erases it.")}</p>
      </Card>
      <Card>
        <CardTitle>{t("Свързани портфейли", "Connected wallets")}</CardTitle>
        {wallet && wallet !== "NO_WALLET" && wallet !== "DENIED"
          ? <p className="text-sm"><code>{wallet}</code> <Button size="sm" variant="secondary" onClick={() => setWallet("")}>{t("Разкачи", "Disconnect")}</Button></p>
          : <Button size="sm" onClick={connectWallet}>{t("Свържи портфейл", "Connect wallet")}</Button>}
        {wallet === "NO_WALLET" && <p className="mt-1 text-sm">{t("Няма портфейл — инсталирайте MetaMask.", "No wallet — install MetaMask.")}</p>}
        <p className="muted mt-2 text-xs">{t("Никога не споделяйте seed фраза или частни ключове. Подписвате само в портфейла.", "Never share seed phrases or private keys. You sign only in the wallet.")}</p>
      </Card>
      <Card>
        <CardTitle>{t("Известия", "Notifications")}</CardTitle>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={notif} onChange={(e) => setNotif(e.target.checked)} />
          {t("Показвай статус съобщения (само в тази сесия)", "Show status messages (this session only)")}
        </label>
      </Card>
    </div>
  );
}

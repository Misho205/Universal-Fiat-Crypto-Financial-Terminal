"use client";
import { useMemo, useRef, useState } from "react";
import { dict, type Locale } from "../src/i18n";
import { HybridPayClient, ModalBackendClient, ApiError, friendlyError } from "@hybridpay/sdk";
import { FIAT_CURRENCIES, CRYPTO_ASSETS } from "../src/currencies";
import EvmPanel from "../src/EvmPanel";
import AgreementsPanel from "../src/AgreementsPanel";
import AssistantPanel from "../src/AssistantPanel";
import DashboardPanel from "../src/DashboardPanel";

// Browser-safe config: only NEXT_PUBLIC_* (never secrets). Meta/provider keys stay in Modal Secrets.
const NEST_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:3001";
const MODAL_URL = process.env.NEXT_PUBLIC_MODAL_API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const DEV_TOKEN = process.env.NEXT_PUBLIC_API_TOKEN ?? "";

type Tab = "dashboard" | "order" | "fiat" | "crypto" | "contract" | "status" | "evm" | "agreements" | "assistant";
type Outcome = { kind: "idle" } | { kind: "loading" } | { kind: "ok"; text: string } | { kind: "err"; text: string; retryable: boolean };

function useIdempotency() {
  const ref = useRef<string | null>(null);
  return () => {
    if (!ref.current) ref.current = `ui-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    return ref.current;
  };
}

const card: React.CSSProperties = { background: "#fff", border: "1px solid #e5e7eb", borderRadius: 16, padding: 20, marginTop: 16, boxShadow: "0 1px 3px rgba(16,24,40,.08)" };
const btnPrimary: React.CSSProperties = { background: "linear-gradient(135deg,#4f46e5,#7c3aed)", color: "#fff", border: "none", borderRadius: 10, padding: "10px 18px", fontWeight: 600, cursor: "pointer", marginRight: 8, marginTop: 8 };
const btnGhost: React.CSSProperties = { background: "#eef2ff", color: "#4338ca", border: "1px solid #c7d2fe", borderRadius: 10, padding: "10px 14px", fontWeight: 600, cursor: "pointer", marginRight: 8, marginTop: 8 };

export default function Home() {
  const [locale] = useState<Locale>("en");
  const [tab, setTab] = useState<Tab>("dashboard");
  const [tenant, setTenant] = useState("demo-tenant");
  // Session token lives in memory only (useState) — never localStorage/sessionStorage.
  const [token, setToken] = useState(DEV_TOKEN);
  const [tokenInput, setTokenInput] = useState("");
  const [role, setRole] = useState("—");
  const t = dict[locale];
  const nest = useMemo(() => new HybridPayClient({ baseUrl: NEST_URL, tenantId: tenant, token: token || undefined }), [tenant, token]);
  const modal = useMemo(() => new ModalBackendClient({ baseUrl: MODAL_URL, tenantId: tenant, token: token || undefined }), [tenant, token]);
  async function refreshRole() {
    try { const r = await modal.me(); setRole((r.data as { role: string }).role); }
    catch { setRole("unreachable"); }
  }

  // order state (existing flow, now via SDK + full states)
  const [amount, setAmount] = useState("10.00");
  const [orderCcy, setOrderCcy] = useState("EUR");
  const [qr, setQr] = useState<string | null>(null);
  const [orderOut, setOrderOut] = useState<Outcome>({ kind: "idle" });
  const orderKey = useIdempotency();
  const [orderBusy, setOrderBusy] = useState(false);

  async function createOrder(retry = false) {
    if (orderBusy && !retry) { setOrderOut({ kind: "err", text: t.duplicateBlocked, retryable: false }); return; }
    setOrderBusy(true);
    setOrderOut({ kind: "loading" });
    try {
      const [eur, cents = "00"] = amount.split(".");
      const minor = `${eur}${cents.padEnd(2, "0").slice(0, 2)}`;
      const o = await nest.createOrder({ storeId: "store-1", denomination: `fiat:${orderCcy}`, totalMinor: minor }, retry ? `ui-${Date.now()}` : orderKey());
      if (o.status !== 201 && o.status !== 200) throw new ApiError(o.status, (o.data as { detail?: unknown }).detail ?? o.data);
      const orderId = (o.data as { id: string }).id;
      const tok = await nest.checkoutToken(orderId, 1);
      setQr((tok.data as { qrPayload: string }).qrPayload);
      setOrderOut({ kind: "ok", text: `order ${orderId} · ${minor} minor ${orderCcy}` });
    } catch (e) {
      setOrderOut({ kind: "err", text: friendlyError(e, locale), retryable: e instanceof ApiError ? e.retryable : true });
    } finally { setOrderBusy(false); }
  }

  // fiat sandbox
  const [fiatAmt, setFiatAmt] = useState("1000");
  const [fiatCcy, setFiatCcy] = useState("EUR");
  const [fiatIns, setFiatIns] = useState("demo-ins-1");
  const [fiatOut, setFiatOut] = useState<Outcome>({ kind: "idle" });
  const [fiatBusy, setFiatBusy] = useState(false);
  async function submitFiat() {
    if (fiatBusy) return; setFiatBusy(true); setFiatOut({ kind: "loading" });
    try {
      const key = `ui-fiat-${Date.now()}`;
      const created = await modal.fiatCreate({ amountMinor: fiatAmt, instructionId: fiatIns, currency: fiatCcy }, key);
      const pid = (created.data as { paymentId: string }).paymentId;
      let detail = `created: ${JSON.stringify(created.data)}`;
      try {
        const confirmed = await modal.fiatConfirm(pid);
        detail += `\nconfirmed (authoritative, provider): ${JSON.stringify(confirmed.data)}`;
      } catch (ce) {
        detail += `\nconfirm: ${friendlyError(ce, locale)}`;
      }
      setFiatOut({ kind: "ok", text: detail });
    } catch (e) { setFiatOut({ kind: "err", text: friendlyError(e, locale), retryable: e instanceof ApiError ? e.retryable : true }); }
    finally { setFiatBusy(false); }
  }

  // crypto testnet
  const [cryAmt, setCryAmt] = useState("50000");
  const [cryIns, setCryIns] = useState("demo-crypto-1");
  const [cryAddr, setCryAddr] = useState("bcrt1qdemo000000000000000000000000000000000");
  const [cryOut, setCryOut] = useState<Outcome>({ kind: "idle" });
  const [cryBusy, setCryBusy] = useState(false);
  async function submitCrypto() {
    if (cryBusy) return; setCryBusy(true); setCryOut({ kind: "loading" });
    try {
      const r = await modal.cryptoSimulate({ amountMinor: cryAmt, instructionId: cryIns, address: cryAddr }, `ui-cry-${Date.now()}`);
      setCryOut({ kind: "ok", text: JSON.stringify(r.data) });
    } catch (e) { setCryOut({ kind: "err", text: friendlyError(e, locale), retryable: e instanceof ApiError ? e.retryable : true }); }
    finally { setCryBusy(false); }
  }

  // contract validate
  const [terms, setTerms] = useState('{"amountMinor":"2599","beneficiaries":[{"shareBps":10000}],"conditions":[{"type":"timeCondition","notAfter":"2030-01-01T00:00:00Z"}],"executionModel":"pay-after-condition"}');
  const [conOut, setConOut] = useState<Outcome>({ kind: "idle" });
  const [conBusy, setConBusy] = useState(false);
  async function submitContract() {
    if (conBusy) return; setConBusy(true); setConOut({ kind: "loading" });
    try {
      const parsed = JSON.parse(terms);
      const r = await modal.validateContract(parsed);
      setConOut({ kind: "ok", text: JSON.stringify(r.data) });
    } catch (e) { setConOut({ kind: "err", text: friendlyError(e, locale), retryable: false }); }
    finally { setConBusy(false); }
  }

  // status + AI
  const [txId, setTxId] = useState("");
  const [stOut, setStOut] = useState<Outcome>({ kind: "idle" });
  const [aiOut, setAiOut] = useState<Outcome>({ kind: "idle" });
  const [health, setHealth] = useState("—");
  async function checkStatus() {
    setStOut({ kind: "loading" });
    try { const r = await modal.txStatus(txId); setStOut({ kind: "ok", text: JSON.stringify(r.data) }); }
    catch (e) { setStOut({ kind: "err", text: friendlyError(e, locale), retryable: e instanceof ApiError ? e.retryable : false }); }
  }
  async function runAi(kind: "explain" | "fraud") {
    setAiOut({ kind: "loading" });
    try {
      const r = kind === "explain" ? await modal.aiExplain({ transactionId: txId }) : await modal.aiFraud({ transactionId: txId });
      setAiOut({ kind: "ok", text: JSON.stringify(r.data).slice(0, 2000) });
    } catch (e) { setAiOut({ kind: "err", text: friendlyError(e, locale), retryable: e instanceof ApiError ? e.retryable : true }); }
  }

  function renderOutcome(o: Outcome, onRetry?: () => void) {
    if (o.kind === "idle") return <p className="muted">{t.empty}</p>;
    if (o.kind === "loading") return <p aria-live="polite">⏳ {t.loading}</p>;
    if (o.kind === "ok") return <pre className="ok">{o.text}</pre>;
    return (<div><pre className="err">{o.text}</pre>
      {o.retryable && onRetry && <button style={btnGhost} onClick={onRetry}>{t.retry}</button>}</div>);
  }

  const tabs: { id: Tab; label: string }[] = [
    { id: "dashboard", label: `📊 ${t.tabDashboard}` },
    { id: "order", label: `🧾 ${t.tabOrder}` },
    { id: "fiat", label: `💶 ${t.tabFiat}` },
    { id: "crypto", label: `₿ ${t.tabCrypto}` },
    { id: "evm", label: `⬣ ${t.tabEvm}` },
    { id: "contract", label: `📜 ${t.tabContract}` },
    { id: "agreements", label: `🤝 ${t.tabAgreements}` },
    { id: "assistant", label: `✨ ${t.tabAssistant}` },
    { id: "status", label: `🔍 ${t.tabStatus}` },
  ];

  return (
    <main>
      <header className="hero">
        <div className="hero-inner">
          <div>
            <div className="brand">◈ HybridPay Terminal</div>
            <p className="tagline">{locale === "bg" ? "Модерен платежен терминал — фиат и крипто, пясъчник и testnet. За хора и за банки (демо)." : "Modern payment terminal — fiat & crypto, sandbox & testnet. For people and banks (demo)."}</p>
          </div>
          <div className="hero-side">
            <span className="live-badge">{t.liveOff}</span>
          </div>
        </div>
        <p className="sandbox">{t.sandboxNote}</p>
      </header>

      <nav className="tabs" aria-label="sections">
        {tabs.map((k) => (
          <button key={k.id} className={tab === k.id ? "tab active" : "tab"} onClick={() => setTab(k.id)} aria-current={tab === k.id ? "page" : undefined}>
            {k.label}
          </button>
        ))}
      </nav>

      <section style={card} aria-label="session">
        <div className="grid2">
          <label>{t.tenant}: <input value={tenant} onChange={(e) => setTenant(e.target.value)} autoComplete="off" /></label>
          <label>{t.tokenLabel}: <input type="password" value={tokenInput} onChange={(e) => setTokenInput(e.target.value)} autoComplete="off" placeholder={token ? "••••••" : ""} /></label>
        </div>
        <div style={{ marginTop: 8 }}>
          <button style={btnPrimary} onClick={() => { setToken(tokenInput.trim()); setTokenInput(""); refreshRole(); }}>{t.signIn}</button>
          <button style={btnGhost} onClick={() => { setToken(""); setTokenInput(""); setRole("—"); }}>{t.logout}</button>
          <span style={{ marginLeft: 8 }}>{t.roleLabel}: <code>{role}</code>{role === "admin" ? "" : role === "operator" ? " (money movement needs admin)" : ""}</span>
        </div>
        <div className="muted" style={{ marginTop: 8 }}>Nest: {NEST_URL} · Modal: {MODAL_URL} · <button className="link" onClick={async () => { try { const h = await modal.health(); setHealth(JSON.stringify(h.data)); } catch (e) { setHealth(friendlyError(e, locale)); } }}>{t.refreshHealth}</button> <code>{health}</code></div>
      </section>

      {tab === "dashboard" && (<section style={card} aria-label="dashboard">
        <h2>📊 {t.tabDashboard}</h2>
        <DashboardPanel modal={modal} locale={locale} />
      </section>)}

      {tab === "order" && (<section style={card}>
        <h2>🧾 {t.tabOrder}</h2>
        <div className="grid2">
          <label>{t.amount}: <input value={amount} onChange={(e) => setAmount(e.target.value)} inputMode="decimal" /></label>
          <label>{locale === "bg" ? "Валута" : "Currency"}: <select value={orderCcy} onChange={(e) => setOrderCcy(e.target.value)}>{FIAT_CURRENCIES.map((c) => <option key={c.code} value={c.code}>{c.code} — {locale === "bg" ? c.nameBg : c.nameEn} ({c.symbol})</option>)}</select></label>
        </div>
        <div><button style={btnPrimary} disabled={orderBusy} onClick={() => createOrder()}>{t.create}</button></div>
        {renderOutcome(orderOut, () => createOrder(true))}
        {qr && (<div><p>{t.scan}</p><code className="qr">{qr}</code><p><strong>{t.receipt}</strong></p></div>)}
      </section>)}

      {tab === "fiat" && (<section style={card}>
        <h2>💶 {t.tabFiat}</h2>
        <div className="asset-row" aria-label="fiat assets">
          {FIAT_CURRENCIES.slice(0, 6).map((c) => (
            <button key={c.code} className={fiatCcy === c.code ? "chip active" : "chip"} onClick={() => setFiatCcy(c.code)}>{c.symbol} {c.code}</button>
          ))}
        </div>
        <div className="grid2">
          <label>{t.fiatAmount}: <input value={fiatAmt} onChange={(e) => setFiatAmt(e.target.value)} inputMode="numeric" /></label>
          <label>{locale === "bg" ? "Валута" : "Currency"}: <select value={fiatCcy} onChange={(e) => setFiatCcy(e.target.value)}>{FIAT_CURRENCIES.map((c) => <option key={c.code} value={c.code}>{c.code} — {locale === "bg" ? c.nameBg : c.nameEn}</option>)}</select></label>
        </div>
        <label>{t.instruction}: <input value={fiatIns} onChange={(e) => setFiatIns(e.target.value)} /></label>
        <div><button style={btnPrimary} disabled={fiatBusy} onClick={submitFiat}>{t.submitFiat}</button></div>
        {renderOutcome(fiatOut, submitFiat)}
      </section>)}

      {tab === "crypto" && (<section style={card}>
        <h2>₿ {t.tabCrypto}</h2>
        <div className="asset-row" aria-label="crypto assets">
          {CRYPTO_ASSETS.map((a) => (
            <span key={a.id} className="chip static" title={a.network}>{locale === "bg" ? a.nameBg : a.nameEn}</span>
          ))}
        </div>
        <label>{t.fiatAmount}: <input value={cryAmt} onChange={(e) => setCryAmt(e.target.value)} inputMode="numeric" /></label><br />
        <label>{t.instruction}: <input value={cryIns} onChange={(e) => setCryIns(e.target.value)} /></label><br />
        <label>{t.address}: <input style={{ width: "100%" }} value={cryAddr} onChange={(e) => setCryAddr(e.target.value)} /></label>
        <div><button style={btnPrimary} disabled={cryBusy} onClick={submitCrypto}>{t.submitCrypto}</button></div>
        {renderOutcome(cryOut, submitCrypto)}
      </section>)}

      {tab === "contract" && (<section style={card}>
        <h2>📜 {t.tabContract}</h2>
        <label>{t.terms}:<br /><textarea style={{ width: "100%", height: 120 }} value={terms} onChange={(e) => setTerms(e.target.value)} /></label>
        <div><button style={btnPrimary} disabled={conBusy} onClick={submitContract}>{t.submitContract}</button></div>
        {renderOutcome(conOut)}
      </section>)}

      {tab === "evm" && (<section style={card}>
        <h2>⬣ {t.tabEvm}</h2>
        <EvmPanel modal={modal} locale={locale} />
      </section>)}

      {tab === "agreements" && (<section style={card}>
        <h2>🤝 {t.tabAgreements}</h2>
        <AgreementsPanel modal={modal} locale={locale} />
      </section>)}

      {tab === "assistant" && (<section style={card}>
        <h2>✨ {t.tabAssistant}</h2>
        <AssistantPanel modal={modal} locale={locale} />
      </section>)}

      {tab === "status" && (<section style={card}>
        <h2>🔍 {t.tabStatus}</h2>
        <label>{t.txId}: <input style={{ width: "100%" }} value={txId} onChange={(e) => setTxId(e.target.value)} /></label>
        <div><button style={btnPrimary} onClick={checkStatus}>{t.checkStatus}</button>
          <button style={btnGhost} onClick={() => runAi("explain")}>{t.explain}</button>
          <button style={btnGhost} onClick={() => runAi("fraud")}>{t.fraud}</button></div>
        <h3>Transaction</h3>{renderOutcome(stOut, checkStatus)}
        <h3>AI (advisory only)</h3>{renderOutcome(aiOut)}
      </section>)}

      <p style={{ marginTop: 16 }}><a href="/simulator">{t.simulatorLink}</a></p>
    </main>
  );
}

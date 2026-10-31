"use client";
import { useMemo, useRef, useState } from "react";
import { dict, type Locale } from "../src/i18n";
import { HybridPayClient, ModalBackendClient, ApiError, friendlyError } from "@hybridpay/sdk";

// Browser-safe config: only NEXT_PUBLIC_* (never secrets). Meta/provider keys stay in Modal Secrets.
const NEST_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:3001";
const MODAL_URL = process.env.NEXT_PUBLIC_MODAL_API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const DEV_TOKEN = process.env.NEXT_PUBLIC_API_TOKEN ?? "";

type Tab = "order" | "fiat" | "crypto" | "contract" | "status";
type Outcome = { kind: "idle" } | { kind: "loading" } | { kind: "ok"; text: string } | { kind: "err"; text: string; retryable: boolean };

function useIdempotency() {
  const ref = useRef<string | null>(null);
  return () => {
    if (!ref.current) ref.current = `ui-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    return ref.current;
  };
}

const box: React.CSSProperties = { border: "1px solid #ddd", borderRadius: 8, padding: 12, marginTop: 12 };
const btn: React.CSSProperties = { marginRight: 8, marginTop: 8 };

export default function Home() {
  const [locale, setLocale] = useState<Locale>("bg");
  const [tab, setTab] = useState<Tab>("order");
  const [tenant, setTenant] = useState("demo-tenant");
  const t = dict[locale];
  const nest = useMemo(() => new HybridPayClient({ baseUrl: NEST_URL, tenantId: tenant, token: DEV_TOKEN || undefined }), [tenant]);
  const modal = useMemo(() => new ModalBackendClient({ baseUrl: MODAL_URL, tenantId: tenant, token: DEV_TOKEN || undefined }), [tenant]);

  // order state (existing flow, now via SDK + full states)
  const [amount, setAmount] = useState("10.00");
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
      const o = await nest.createOrder({ storeId: "store-1", denomination: "fiat:EUR", totalMinor: minor }, retry ? `ui-${Date.now()}` : orderKey());
      if (o.status !== 201 && o.status !== 200) throw new ApiError(o.status, (o.data as { detail?: unknown }).detail ?? o.data);
      const orderId = (o.data as { id: string }).id;
      const tok = await nest.checkoutToken(orderId, 1);
      setQr((tok.data as { qrPayload: string }).qrPayload);
      setOrderOut({ kind: "ok", text: `order ${orderId}` });
    } catch (e) {
      setOrderOut({ kind: "err", text: friendlyError(e, locale), retryable: e instanceof ApiError ? e.retryable : true });
    } finally { setOrderBusy(false); }
  }

  // fiat sandbox
  const [fiatAmt, setFiatAmt] = useState("1000");
  const [fiatIns, setFiatIns] = useState("demo-ins-1");
  const [fiatOut, setFiatOut] = useState<Outcome>({ kind: "idle" });
  const [fiatBusy, setFiatBusy] = useState(false);
  async function submitFiat() {
    if (fiatBusy) return; setFiatBusy(true); setFiatOut({ kind: "loading" });
    try {
      const key = `ui-fiat-${Date.now()}`;
      const r = await modal.fiatSimulate({ amountMinor: fiatAmt, instructionId: fiatIns, currency: "EUR" }, key);
      setFiatOut({ kind: "ok", text: JSON.stringify(r.data) });
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
    if (o.kind === "idle") return <p style={{ color: "#666" }}>{t.empty}</p>;
    if (o.kind === "loading") return <p aria-live="polite">{t.loading}</p>;
    if (o.kind === "ok") return <pre style={{ whiteSpace: "pre-wrap", background: "#f0fdf4", padding: 8 }}>{o.text}</pre>;
    return (<div><pre style={{ whiteSpace: "pre-wrap", background: "#fef2f2", padding: 8 }}>{o.text}</pre>
      {o.retryable && onRetry && <button style={btn} onClick={onRetry}>{t.retry}</button>}</div>);
  }

  return (
    <main style={{ fontFamily: "system-ui", padding: 24, maxWidth: 720 }}>
      <div style={{ background: "#111", color: "#fff", padding: 8, borderRadius: 8 }}>{t.liveOff} — {t.liveBlocked}</div>
      <div style={{ marginTop: 8 }}>
        <button onClick={() => setLocale(locale === "bg" ? "en" : "bg")}>{locale === "bg" ? "EN" : "БГ"}</button>
        <span style={{ marginLeft: 12, color: "#555" }}>{t.sandboxNote}</span>
      </div>
      <h1>HybridPay Terminal — {t.newOrder}</h1>
      <div>
        {(["order", "fiat", "crypto", "contract", "status"] as Tab[]).map((k) => (
          <button key={k} style={{ ...btn, fontWeight: tab === k ? "bold" : "normal" }} onClick={() => setTab(k)}>
            {k === "order" ? t.tabOrder : k === "fiat" ? t.tabFiat : k === "crypto" ? t.tabCrypto : k === "contract" ? t.tabContract : t.tabStatus}
          </button>
        ))}
      </div>
      <div style={box}>
        <label>{t.tenant}: <input value={tenant} onChange={(e) => setTenant(e.target.value)} /></label>
        <div style={{ color: "#555", fontSize: 12, marginTop: 4 }}>Nest: {NEST_URL} · Modal: {MODAL_URL}</div>
        <div style={{ marginTop: 4 }}><button onClick={async () => { try { const h = await modal.health(); setHealth(JSON.stringify(h.data)); } catch (e) { setHealth(friendlyError(e, locale)); } }}>{t.refreshHealth}</button>
          <code style={{ marginLeft: 8 }}>{health}</code></div>
      </div>

      {tab === "order" && (<section style={box}>
        <h2>{t.tabOrder}</h2>
        <label>{t.amount}: <input value={amount} onChange={(e) => setAmount(e.target.value)} /></label>
        <div><button style={btn} disabled={orderBusy} onClick={() => createOrder()}>{t.create}</button></div>
        {renderOutcome(orderOut, () => createOrder(true))}
        {qr && (<div><p>{t.scan}</p><code style={{ wordBreak: "break-all" }}>{qr}</code><p><strong>{t.receipt}</strong></p></div>)}
      </section>)}

      {tab === "fiat" && (<section style={box}>
        <h2>{t.tabFiat}</h2>
        <label>{t.fiatAmount}: <input value={fiatAmt} onChange={(e) => setFiatAmt(e.target.value)} /></label><br />
        <label>{t.instruction}: <input value={fiatIns} onChange={(e) => setFiatIns(e.target.value)} /></label>
        <div><button style={btn} disabled={fiatBusy} onClick={submitFiat}>{t.submitFiat}</button></div>
        {renderOutcome(fiatOut, submitFiat)}
      </section>)}

      {tab === "crypto" && (<section style={box}>
        <h2>{t.tabCrypto}</h2>
        <label>{t.fiatAmount}: <input value={cryAmt} onChange={(e) => setCryAmt(e.target.value)} /></label><br />
        <label>{t.instruction}: <input value={cryIns} onChange={(e) => setCryIns(e.target.value)} /></label><br />
        <label>{t.address}: <input style={{ width: "100%" }} value={cryAddr} onChange={(e) => setCryAddr(e.target.value)} /></label>
        <div><button style={btn} disabled={cryBusy} onClick={submitCrypto}>{t.submitCrypto}</button></div>
        {renderOutcome(cryOut, submitCrypto)}
      </section>)}

      {tab === "contract" && (<section style={box}>
        <h2>{t.tabContract}</h2>
        <label>{t.terms}:<br /><textarea style={{ width: "100%", height: 120 }} value={terms} onChange={(e) => setTerms(e.target.value)} /></label>
        <div><button style={btn} disabled={conBusy} onClick={submitContract}>{t.submitContract}</button></div>
        {renderOutcome(conOut)}
      </section>)}

      {tab === "status" && (<section style={box}>
        <h2>{t.tabStatus}</h2>
        <label>{t.txId}: <input style={{ width: "100%" }} value={txId} onChange={(e) => setTxId(e.target.value)} /></label>
        <div><button style={btn} onClick={checkStatus}>{t.checkStatus}</button>
          <button style={btn} onClick={() => runAi("explain")}>{t.explain}</button>
          <button style={btn} onClick={() => runAi("fraud")}>{t.fraud}</button></div>
        <h3>Transaction</h3>{renderOutcome(stOut, checkStatus)}
        <h3>AI (advisory only)</h3>{renderOutcome(aiOut)}
      </section>)}

      <p style={{ marginTop: 16 }}><a href="/simulator">{t.simulatorLink}</a></p>
    </main>
  );
}

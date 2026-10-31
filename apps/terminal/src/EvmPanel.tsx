"use client";
import { useState } from "react";
import { dict, type Locale } from "./i18n";
import { ModalBackendClient, ApiError, friendlyError } from "@hybridpay/sdk";
import { walletAvailable, connectWallet, walletChainId, switchToSepolia, sendSepoliaTx,
         SEPOLIA_CHAIN_ID, explorerTx } from "./evm";

const btn: React.CSSProperties = { marginRight: 8, marginTop: 8 };
type Outcome = { kind: "idle" } | { kind: "loading" } | { kind: "ok"; text: string } | { kind: "err"; text: string; retryable: boolean };

export default function EvmPanel({ modal, locale }: { modal: ModalBackendClient; locale: Locale }) {
  const t = dict[locale];
  const [addr, setAddr] = useState<string | null>(null);
  const [chain, setChain] = useState<number | null>(null);
  const [to, setTo] = useState("0x0000000000000000000000000000000000000000");
  const [eth, setEth] = useState("0.001");
  const [payId, setPayId] = useState("");
  const [out, setOut] = useState<Outcome>({ kind: "idle" });
  const [busy, setBusy] = useState(false);

  async function connect() {
    setOut({ kind: "loading" });
    try {
      if (!walletAvailable()) { setOut({ kind: "err", text: t.walletNeeded, retryable: false }); return; }
      const a = await connectWallet();
      setAddr(a);
      setChain(await walletChainId());
      setOut({ kind: "ok", text: `wallet ${a}` });
    } catch (e) { setOut({ kind: "err", text: friendlyError(e, locale), retryable: false }); }
  }
  async function createTracked() {
    if (busy) return; setBusy(true); setOut({ kind: "loading" });
    try {
      const wei = String(BigInt(Math.round(parseFloat(eth) * 1e18)));
      const r = await modal.evmRequest({ to, valueWei: wei, chainId: SEPOLIA_CHAIN_ID }, `ui-evm-${Date.now()}`);
      setPayId((r.data as { paymentId: string }).paymentId);
      setOut({ kind: "ok", text: JSON.stringify(r.data) });
    } catch (e) { setOut({ kind: "err", text: friendlyError(e, locale), retryable: e instanceof ApiError ? e.retryable : true }); }
    finally { setBusy(false); }
  }
  async function signAndSend() {
    if (busy || !addr || !payId) return; setBusy(true); setOut({ kind: "loading" });
    try {
      const hash = await sendSepoliaTx(addr, to, eth);
      const s = await modal.evmSubmit(payId, hash);
      setOut({ kind: "ok", text: `tx ${hash}\n${explorerTx(hash)}\n${JSON.stringify(s.data)}` });
    } catch (e) { setOut({ kind: "err", text: friendlyError(e, locale), retryable: false }); }
    finally { setBusy(false); }
  }
  async function checkReceipt() {
    if (!payId) return; setOut({ kind: "loading" });
    try {
      const r = await modal.evmStatus(payId);
      const d = r.data as { state: string; confirmations: number; confirmationsRequired: number; explorer: string | null; note: string };
      setOut({ kind: "ok", text: `state=${d.state} ${d.confirmations}/${d.confirmationsRequired} ${t.confirmations}\n${d.explorer ?? ""}\n${d.note}\n${t.chainNote}` });
    } catch (e) { setOut({ kind: "err", text: friendlyError(e, locale), retryable: e instanceof ApiError ? e.retryable : true }); }
  }

  const wrongChain = chain !== null && chain !== SEPOLIA_CHAIN_ID;
  return (
    <div>
      <div style={{ background: "#111", color: "#fff", padding: 6, borderRadius: 8, marginBottom: 8 }}>
        Sepolia testnet only (chain {SEPOLIA_CHAIN_ID}). Mainnet blocked. Keys never leave your wallet.
      </div>
      {!addr
        ? <div><button style={btn} onClick={connect}>{t.connectWallet}</button></div>
        : <div>wallet: <code>{addr}</code> · chain: <code>{chain}</code>
            {wrongChain && <div style={{ color: "#a00" }}>{t.wrongChain} <button style={btn} onClick={async () => { await switchToSepolia(); setChain(await walletChainId()); }}>{t.switchSepolia}</button></div>}
          </div>}
      <div style={{ marginTop: 8 }}>
        <label>{t.toAddress}: <input style={{ width: "100%" }} value={to} onChange={(e) => setTo(e.target.value)} /></label><br />
        <label>{t.amountEth}: <input value={eth} onChange={(e) => setEth(e.target.value)} /></label>
      </div>
      <div>
        <button style={btn} disabled={busy} onClick={createTracked}>{t.createTracked}</button>
        <button style={btn} disabled={busy || !addr || !payId || wrongChain} onClick={signAndSend}>{t.sendViaWallet}</button>
        <button style={btn} disabled={!payId} onClick={checkReceipt}>{t.checkReceipt}</button>
      </div>
      {out.kind === "idle" && <p style={{ color: "#666" }}>{t.empty}</p>}
      {out.kind === "loading" && <p aria-live="polite">{t.loading}</p>}
      {out.kind === "ok" && <pre style={{ whiteSpace: "pre-wrap", background: "#f0fdf4", padding: 8 }}>{out.text}</pre>}
      {out.kind === "err" && <pre style={{ whiteSpace: "pre-wrap", background: "#fef2f2", padding: 8 }}>{out.text}</pre>}
    </div>
  );
}

"use client";
import { useState } from "react";
import { dict, type Locale } from "./i18n";
import { ModalBackendClient, ApiError, friendlyError } from "@hybridpay/sdk";
import { usePolling, TERMINAL_STATES } from "./lib/polling";
import { walletAvailable, connectWallet, walletChainId, switchToSepolia, sendSepoliaTx,
  SEPOLIA_CHAIN_ID, explorerTx } from "./evm";
import { Card, CardTitle } from "./components/ui/card";
import { Button } from "./components/ui/button";
import { Field, Input } from "./components/ui/field";
import { Alert } from "./components/ui/feedback";
import { StatusBadge, SandboxBadge } from "./components/ui/badge";

type Outcome = { kind: "idle" } | { kind: "loading" } | { kind: "ok"; text: string } | { kind: "err"; text: string; retryable: boolean };

/** Exact ETH string → wei string. Returns null on invalid input (no float math). */
export function ethToWei(input: string): string | null {
  const s = input.trim();
  if (!/^\d+(\.\d{1,18})?$/.test(s)) return null;
  const [whole, frac = ""] = s.split(".");
  const fracPadded = (frac + "0".repeat(18)).slice(0, 18);
  try {
    return String(BigInt(whole) * BigInt(10) ** BigInt(18) + BigInt(fracPadded || "0"));
  } catch {
    return null;
  }
}

export default function EvmPanel({ modal, locale }: { modal: ModalBackendClient; locale: Locale }) {
  const t = dict[locale];
  const [addr, setAddr] = useState<string | null>(null);
  const [chain, setChain] = useState<number | null>(null);
  const [to, setTo] = useState("0x0000000000000000000000000000000000000000");
  const [eth, setEth] = useState("0.001");
  const [addrErr, setAddrErr] = useState("");
  const [ethErr, setEthErr] = useState("");
  const [payId, setPayId] = useState("");
  const [out, setOut] = useState<Outcome>({ kind: "idle" });
  const [busy, setBusy] = useState(false);

  function validateInputs(): boolean {
    let ok = true;
    if (!/^0x[0-9a-fA-F]{40}$/.test(to)) {
      setAddrErr("Destination must be a valid EVM address (0x + 40 hex).");
      ok = false;
    } else setAddrErr("");
    if (ethToWei(eth) === null) {
      setEthErr("Invalid ETH amount (e.g. 0.001, up to 18 decimals).");
      ok = false;
    } else setEthErr("");
    return ok;
  }

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
    if (busy) return;
    if (!validateInputs()) { setOut({ kind: "err", text: "Fix the highlighted fields first.", retryable: false }); return; }
    setBusy(true); setOut({ kind: "loading" });
    try {
      const wei = ethToWei(eth) as string;
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
  async function explainCrypto() {
    if (!payId) return; setOut({ kind: "loading" });
    try {
      const st = await modal.evmStatus(payId);
      const d = st.data as { state: string; txHash: string; confirmations: number; confirmationsRequired: number; explorer: string | null; note: string };
      const r = await modal.aiExplainCrypto({ txHash: d.txHash, state: d.state, confirmations: d.confirmations, confirmationsRequired: d.confirmationsRequired, chain: "sepolia", explorer: d.explorer });
      const body = r.data as { validated: boolean; data: unknown; notice: string };
      setOut({ kind: "ok", text: `${JSON.stringify(body.data)}\n[${body.validated ? t.validatedLabel : t.stubLabel}] ${body.notice ?? ""}` });
    } catch (e) { setOut({ kind: "err", text: `${friendlyError(e, locale)}\nShowing deterministic data instead: use Check receipt.`, retryable: false }); }
  }

  const wrongChain = chain !== null && chain !== SEPOLIA_CHAIN_ID;

  // Live tracking: polls receipts with backoff, stops on terminal states.
  const [autoTrack, setAutoTrack] = useState(false);
  const tracked = usePolling(async () => {
    if (!payId) return null;
    const r = await modal.evmStatus(payId);
    return r.data as { state: string; confirmations: number; confirmationsRequired: number; txHash: string; explorer: string | null; note: string };
  }, { enabled: !!payId && autoTrack, isTerminal: (v) => !!v && TERMINAL_STATES.evm.has(v.state) });
  return (
    <Card>
      <CardTitle>EVM Sepolia (testnet)</CardTitle>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <SandboxBadge />
        <span className="text-xs text-muted">Sepolia testnet only (chain {SEPOLIA_CHAIN_ID}). Mainnet blocked. Keys never leave your wallet.</span>
      </div>
      {!addr
        ? <div><Button size="sm" onClick={connect}>{t.connectWallet}</Button></div>
        : <div className="text-sm">wallet: <code>{addr}</code> · chain: <code>{chain}</code>
            {wrongChain && <div className="mt-1"><Alert tone="warn">{t.wrongChain} <Button size="sm" variant="secondary" onClick={async () => { await switchToSepolia(); setChain(await walletChainId()); }}>{t.switchSepolia}</Button></Alert></div>}
          </div>}
      <div className="mt-3 grid grid-cols-1 gap-2 md:grid-cols-2">
        <Field label={t.toAddress} error={addrErr}><Input value={to} onChange={(e) => { setTo(e.target.value); setAddrErr(""); }} autoComplete="off" /></Field>
        <Field label={t.amountEth} error={ethErr}><Input value={eth} onChange={(e) => { setEth(e.target.value); setEthErr(""); }} inputMode="decimal" /></Field>
      </div>
      <div className="mt-2 flex flex-wrap gap-2">
        <Button size="sm" disabled={busy} onClick={createTracked}>{t.createTracked}</Button>
        <Button size="sm" variant="secondary" disabled={busy || !addr || !payId || wrongChain} onClick={signAndSend}>{t.sendViaWallet}</Button>
        <Button size="sm" variant="secondary" disabled={!payId} onClick={checkReceipt}>{t.checkReceipt}</Button>
        <Button size="sm" variant="secondary" disabled={!payId} onClick={explainCrypto}>{t.explainCrypto}</Button>
        <label className="flex items-center gap-1 text-sm">
          <input type="checkbox" checked={autoTrack} onChange={(e) => setAutoTrack(e.target.checked)} disabled={!payId} /> live tracking
        </label>
      </div>
      {tracked.data && (
        <div role="status" aria-live="polite" className="ok mt-2 flex flex-wrap items-center gap-2">
          <StatusBadge state={tracked.data.state} />
          <span>{tracked.data.confirmations}/{tracked.data.confirmationsRequired} {t.confirmations}</span>
          {tracked.data.explorer && <> · <a className="underline" href={tracked.data.explorer} target="_blank" rel="noreferrer">explorer</a></>}
        </div>
      )}
      {tracked.error && <div className="mt-2"><Alert tone="danger">{tracked.error} <button className="underline" onClick={tracked.reset}>{t.retry}</button></Alert></div>}
      <div className="mt-2" aria-live="polite">
        {out.kind === "idle" && <p className="muted text-sm">{t.empty}</p>}
        {out.kind === "loading" && <p className="text-sm">Working…</p>}
        {out.kind === "ok" && <pre className="ok">{out.text}</pre>}
        {out.kind === "err" && <Alert tone="danger">{out.text}</Alert>}
      </div>
    </Card>
  );
}

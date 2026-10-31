"use client";
import { useState } from "react";
import { dict, type Locale } from "./i18n";
import { ModalBackendClient, ApiError, friendlyError } from "@hybridpay/sdk";

const btn: React.CSSProperties = { marginRight: 8, marginTop: 8 };
type Outcome = { kind: "idle" } | { kind: "loading" } | { kind: "ok"; text: string } | { kind: "err"; text: string; retryable: boolean };

const PRESET = {
  amountMinor: "2599", currency: "EUR", parties: ["merchant", "customer"],
  conditions: [
    { type: "timeCondition", notBefore: "2020-01-01T00:00:00Z", notAfter: "2030-01-01T00:00:00Z" },
    { type: "partyApproval", party: "customer" },
  ],
  executionModel: "pay-after-condition", expiresAt: "2030-01-01T00:00:00Z",
};

export default function AgreementsPanel({ modal, locale }: { modal: ModalBackendClient; locale: Locale }) {
  const t = dict[locale];
  const [terms, setTerms] = useState(JSON.stringify(PRESET, null, 2));
  const [creator, setCreator] = useState("merchant-op");
  const [agId, setAgId] = useState("");
  const [actor, setActor] = useState("customer");
  const [out, setOut] = useState<Outcome>({ kind: "idle" });
  const [busy, setBusy] = useState(false);

  async function run(fn: () => Promise<unknown>) {
    if (busy) return; setBusy(true); setOut({ kind: "loading" });
    try {
      const r = await fn() as { data: unknown };
      setOut({ kind: "ok", text: JSON.stringify(r.data, null, 2).slice(0, 4000) });
    } catch (e) { setOut({ kind: "err", text: friendlyError(e, locale), retryable: e instanceof ApiError ? e.retryable : false }); }
    finally { setBusy(false); }
  }
  const create = () => run(async () => {
    const r = await modal.pagCreate(JSON.parse(terms), creator, `ui-pag-${Date.now()}`);
    setAgId((r.data as { agreementId: string }).agreementId);
    return r;
  });

  return (
    <div>
      <div style={{ background: "#fef9c3", padding: 6, borderRadius: 8, marginBottom: 8 }}>
        {locale === "bg"
          ? "НЕ е ескроу: няма резервиране/държане/гарантиране на средства. Изпълнението само извиква sandbox доставчика."
          : "NOT escrow: no reservation/holding/guarantee of funds. Execution only calls the sandbox provider."}
      </div>
      <label>{t.terms}:<br /><textarea style={{ width: "100%", height: 150 }} value={terms} onChange={(e) => setTerms(e.target.value)} /></label><br />
      <label>{t.actorName} (creator): <input value={creator} onChange={(e) => setCreator(e.target.value)} /></label>
      <div><button style={btn} disabled={busy} onClick={create}>{t.createAgreement}</button></div>
      <div style={{ marginTop: 8 }}>
        <label>agreementId: <input style={{ width: "100%" }} value={agId} onChange={(e) => setAgId(e.target.value)} /></label><br />
        <label>{t.actorName}: <input value={actor} onChange={(e) => setActor(e.target.value)} /></label>
      </div>
      <div>
        <button style={btn} disabled={!agId} onClick={() => run(() => modal.pagGet(agId))}>{t.checkStatus}</button>
        <button style={btn} disabled={!agId} onClick={() => run(() => modal.pagActivate(agId, creator, "creator"))}>{t.activate}</button>
        <button style={btn} disabled={!agId} onClick={() => run(() => modal.pagApprove(agId, actor, "party"))}>{t.approve}</button>
        <button style={btn} disabled={!agId} onClick={() => run(() => modal.pagExecute(agId, "finance-op", `ui-exec-${Date.now()}`))}>{t.execute}</button>
      </div>
      {out.kind === "idle" && <p style={{ color: "#666" }}>{t.empty}</p>}
      {out.kind === "loading" && <p aria-live="polite">{t.loading}</p>}
      {out.kind === "ok" && <pre style={{ whiteSpace: "pre-wrap", background: "#f0fdf4", padding: 8 }}>{out.text}</pre>}
      {out.kind === "err" && <pre style={{ whiteSpace: "pre-wrap", background: "#fef2f2", padding: 8 }}>{out.text}</pre>}
    </div>
  );
}

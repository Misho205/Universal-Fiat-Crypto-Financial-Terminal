"use client";
import { useState } from "react";
import { dict, type Locale } from "./i18n";
import { ModalBackendClient, ApiError, friendlyError } from "@hybridpay/sdk";

const btn: React.CSSProperties = { marginRight: 8, marginTop: 8 };
type Item = { kind: string; id: string; state: string; detail: string; ref: string; explorer?: string | null };

export default function DashboardPanel({ modal, locale }: { modal: ModalBackendClient; locale: Locale }) {
  const t = dict[locale];
  const [summary, setSummary] = useState("");
  const [items, setItems] = useState<Item[]>([]);
  const [kind, setKind] = useState("all");
  const [stateF, setStateF] = useState("");
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  async function refresh() {
    if (busy) return; setBusy(true); setErr("");
    try {
      const s = await modal.dashboardSummary();
      const d = s.data as { fiat: { total: number; byState: Record<string, number> }; evm: { total: number; byState: Record<string, number> }; agreements: { total: number; byState: Record<string, number> } };
      setSummary(`fiat ${d.fiat.total} ${JSON.stringify(d.fiat.byState)} · evm ${d.evm.total} ${JSON.stringify(d.evm.byState)} · agreements ${d.agreements.total} ${JSON.stringify(d.agreements.byState)}`);
      const r = await modal.dashboardRecent({ kind, state: stateF || undefined, q: q || undefined });
      setItems((r.data as { items: Item[] }).items);
    } catch (e) { setErr(friendlyError(e, locale)); }
    finally { setBusy(false); }
  }

  return (
    <div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginBottom: 8 }} role="group" aria-label="filters">
        <label>kind: <select value={kind} onChange={(e) => setKind(e.target.value)} aria-label="kind filter">
          {["all", "fiat", "evm", "agreement"].map((k) => <option key={k} value={k}>{k}</option>)}
        </select></label>
        <label>state: <input value={stateF} onChange={(e) => setStateF(e.target.value)} placeholder="pending…" aria-label="state filter" /></label>
        <label>search: <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="id / ref…" aria-label="search" /></label>
        <button style={btn} disabled={busy} onClick={refresh}>{locale === "bg" ? "Обнови" : "Refresh"}</button>
      </div>
      <div role="status" aria-live="polite">
        {summary ? <p><strong>{locale === "bg" ? "Сводка" : "Summary"}:</strong> <code>{summary}</code></p>
          : <p style={{ color: "#666" }}>{t.empty}</p>}
        {err && <pre style={{ whiteSpace: "pre-wrap", background: "#fef2f2", padding: 8 }}>{err}</pre>}
        {busy && <p>{t.loading}</p>}
      </div>
      <ul style={{ listStyle: "none", padding: 0 }}>
        {items.map((i) => (
          <li key={`${i.kind}:${i.id}`} style={{ border: "1px solid #ddd", borderRadius: 8, padding: 8, marginTop: 8 }}>
            <code>[{i.kind}]</code> <strong>{i.id}</strong> <code>{i.state}</code>
            <div style={{ color: "#444", fontSize: 13 }}>{i.detail}</div>
            {i.ref && <div style={{ fontSize: 12 }}><code style={{ wordBreak: "break-all" }}>{i.ref}</code></div>}
            {i.explorer && <div style={{ fontSize: 12 }}><a href={i.explorer} target="_blank" rel="noreferrer">{i.explorer}</a></div>}
          </li>
        ))}
      </ul>
    </div>
  );
}

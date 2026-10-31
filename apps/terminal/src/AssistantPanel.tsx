"use client";
import { useState } from "react";
import { dict, type Locale } from "./i18n";
import { ModalBackendClient, ApiError, friendlyError } from "@hybridpay/sdk";

const btn: React.CSSProperties = { marginRight: 8, marginTop: 8 };
type Msg = { role: "you" | "ai"; text: string; validated?: boolean };

export default function AssistantPanel({ modal, locale }: { modal: ModalBackendClient; locale: Locale }) {
  const t = dict[locale];
  const [q, setQ] = useState("");
  const [log, setLog] = useState<Msg[]>([]);
  const [busy, setBusy] = useState(false);
  const [usage, setUsage] = useState("");

  async function ask() {
    if (busy || !q.trim()) return;
    const msg = q.trim();
    setQ(""); setBusy(true);
    setLog((p) => [...p, { role: "you", text: msg }]);
    try {
      const r = await modal.aiAssistant(msg, { tab: "dashboard" });
      const d = r.data.data as { answer: string; topic: string; actions: string[] };
      const validated = (r.data as { validated: boolean }).validated;
      setLog((p) => [...p, { role: "ai", text: `[${d.topic}] ${d.answer}${d.actions.length ? `\n→ ${d.actions.join(", ")}` : ""}`, validated }]);
    } catch (e) {
      // Fallback UI: deterministic guidance when AI is unavailable — never a dead end.
      setLog((p) => [...p, { role: "ai", text: `${friendlyError(e, locale)}\n${locale === "bg" ? "Показвам детерминистични данни: проверете Status таба и /simulator." : "Showing deterministic data instead: check the Status tab and /simulator."}`, validated: false }]);
    } finally { setBusy(false); }
  }
  async function loadUsage() {
    try {
      const r = await modal.aiUsage();
      const d = r.data as { calls: number; fallbacks: number; promptTokens: number; completionTokens: number };
      setUsage(`calls=${d.calls} fallbacks=${d.fallbacks} promptTokens=${d.promptTokens} completionTokens=${d.completionTokens}`);
    } catch (e) { setUsage(friendlyError(e, locale)); }
  }

  return (
    <div>
      <div style={{ background: "#111", color: "#fff", padding: 6, borderRadius: 8, marginBottom: 8 }}>
        {locale === "bg" ? "Асистентът само съветва — не мести средства, не подписва, не одобрява." : "The assistant only advises — it never moves funds, signs, or approves."}
      </div>
      <div style={{ border: "1px solid #ddd", borderRadius: 8, padding: 8, minHeight: 120, maxHeight: 320, overflowY: "auto" }}>
        {log.length === 0 && <p style={{ color: "#666" }}>{t.askPlaceholder}</p>}
        {log.map((m, i) => (
          <div key={i} style={{ marginBottom: 8, background: m.role === "you" ? "#eef" : "#f8fafc", padding: 6, borderRadius: 6 }}>
            <strong>{m.role === "you" ? "›" : "AI"}</strong> <span style={{ whiteSpace: "pre-wrap" }}>{m.text}</span>
            {m.role === "ai" && <span style={{ color: "#666", fontSize: 12 }}> [{m.validated ? t.validatedLabel : t.stubLabel}]</span>}
          </div>
        ))}
        {busy && <p aria-live="polite">{t.loading}</p>}
      </div>
      <div style={{ marginTop: 8 }}>
        <input style={{ width: "70%" }} value={q} onChange={(e) => setQ(e.target.value)}
          placeholder={t.askPlaceholder} onKeyDown={(e) => { if (e.key === "Enter") ask(); }} />
        <button style={btn} disabled={busy} onClick={ask}>{t.ask}</button>
        <button style={btn} onClick={loadUsage}>{t.usageLabel}</button>
        {usage && <code style={{ fontSize: 12 }}>{usage}</code>}
      </div>
    </div>
  );
}

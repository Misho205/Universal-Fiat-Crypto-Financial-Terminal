"use client";
import { useMemo, useState } from "react";
import { ModalBackendClient, friendlyError, type TxStatus } from "@hybridpay/sdk";

const MODAL_URL = process.env.NEXT_PUBLIC_MODAL_API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const DEV_TOKEN = process.env.NEXT_PUBLIC_API_TOKEN ?? "";

type ScenarioId = "fiat-ok" | "fiat-fail" | "fiat-timeout" | "crypto-wrong" | "contract-bad";
type Run = { id: number; scenario: ScenarioId; label: string; state: string; detail: string; simulated: boolean; at: string };

const SCENARIOS: { id: ScenarioId; bg: string; en: string }[] = [
  { id: "fiat-ok", bg: "Успешно фиат плащане (€10)", en: "Successful fiat payment (€10)" },
  { id: "fiat-fail", bg: "Отказано плащане (mock declined)", en: "Declined payment (mock declined)" },
  { id: "fiat-timeout", bg: "Timeout → UNKNOWN (query-original)", en: "Timeout → UNKNOWN (query-original)" },
  { id: "crypto-wrong", bg: "Грешна крипто мрежа (отхвърлено)", en: "Wrong crypto network (rejected)" },
  { id: "contract-bad", bg: "Договор с грешка (валидаторът хваща)", en: "Contract with error (validator catches)" },
];

export default function Simulator() {
  const [locale, setLocale] = useState<"bg" | "en">("bg");
  const [tenant] = useState("demo-tenant");
  const [runs, setRuns] = useState<Run[]>([]);
  const [busy, setBusy] = useState<ScenarioId | null>(null);
  const modal = useMemo(() => new ModalBackendClient({ baseUrl: MODAL_URL, tenantId: tenant, token: DEV_TOKEN || undefined }), [tenant]);
  let seq = runs.length + 1;

  async function runScenario(s: ScenarioId) {
    if (busy) return;
    setBusy(s);
    const at = new Date().toLocaleTimeString();
    const label = SCENARIOS.find((x) => x.id === s)![locale];
    try {
      if (s === "fiat-ok" || s === "fiat-fail" || s === "fiat-timeout") {
        const suffix = s === "fiat-ok" ? "sim-ok" : s === "fiat-fail" ? "simfail" : "simtimeout";
        const r = await modal.fiatSimulate({ amountMinor: "1000", instructionId: `sim-${Date.now()}-${suffix}`, currency: "EUR" }, `sim-${Date.now()}-${s}`);
        push({ scenario: s, label, state: (r.data as TxStatus).state, detail: JSON.stringify(r.data), simulated: false, at });
      } else if (s === "crypto-wrong") {
        try {
          await modal.cryptoSimulate({ amountMinor: "50000", instructionId: `sim-${Date.now()}`, address: "tb1qwrong-mainnet-address" }, `sim-${Date.now()}-cry`);
          push({ scenario: s, label, state: "UNEXPECTED-OK", detail: "backend accepted a wrong-network address (should not happen)", simulated: false, at });
        } catch (e) {
          push({ scenario: s, label, state: "REJECTED-AS-EXPECTED", detail: friendlyError(e, locale), simulated: false, at });
        }
      } else {
        const r = await modal.validateContract({ amountMinor: "not-a-number", beneficiaries: [], conditions: [{ type: "evilEval" }], executionModel: "pay-after-condition" });
        push({ scenario: s, label, state: (r.data as { ok: boolean }).ok ? "UNEXPECTED-OK" : "INVALID-AS-EXPECTED", detail: JSON.stringify(r.data), simulated: false, at });
      }
    } catch (e) {
      // Offline fallback: clearly labeled LOCAL simulation so humans can still click through the UI.
      const local: Record<ScenarioId, string> = {
        "fiat-ok": "AUTHORIZED (local simulation — backend offline)", "fiat-fail": "FAILED mock declined (local simulation)",
        "fiat-timeout": "UNKNOWN query-original (local simulation)", "crypto-wrong": "REJECTED-AS-EXPECTED wrong-network (local simulation)",
        "contract-bad": "INVALID-AS-EXPECTED validator errors (local simulation)",
      };
      push({ scenario: s, label, state: local[s], detail: `${friendlyError(e, locale)} · Показана е локална симулация, защото backend-ът на ${MODAL_URL} не отговаря.`, simulated: true, at });
    } finally { setBusy(null); }
  }
  function push(r: Omit<Run, "id">) { setRuns((prev) => [{ ...r, id: seq++ }, ...prev].slice(0, 20)); }

  return (
    <main style={{ fontFamily: "system-ui", padding: 24, maxWidth: 760 }}>
      <div style={{ background: "#111", color: "#fff", padding: 8, borderRadius: 8 }}>
        {locale === "bg" ? "СИМУЛАТОР — само пробни транзакции, без реални пари." : "SIMULATOR — trial transactions only, no real money."}
      </div>
      <div style={{ marginTop: 8 }}>
        <button onClick={() => setLocale(locale === "bg" ? "en" : "bg")}>{locale === "bg" ? "EN" : "БГ"}</button>
        <a href="/" style={{ marginLeft: 12 }}>{locale === "bg" ? "← Обратно към терминала" : "← Back to terminal"}</a>
      </div>
      <h1>{locale === "bg" ? "Визуален симулатор за пробни тестове" : "Visual simulator for trial tests"}</h1>
      <p style={{ color: "#555" }}>Modal: {MODAL_URL} · {locale === "bg" ? "Всеки сценарий е безопасен — sandbox/testnet или локална симулация." : "Every scenario is safe — sandbox/testnet or local simulation."}</p>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
        {SCENARIOS.map((s) => (
          <button key={s.id} disabled={busy !== null} onClick={() => runScenario(s.id)}>
            {busy === s.id ? "…" : s[locale]}
          </button>
        ))}
        <button disabled={runs.length === 0} onClick={() => setRuns([])}>{locale === "bg" ? "Изчисти" : "Clear"}</button>
      </div>
      {runs.length === 0 && <p style={{ color: "#666" }}>{locale === "bg" ? "Няма изпълнения — натиснете сценарий." : "No runs yet — press a scenario."}</p>}
      {runs.map((r) => (
        <div key={r.id} style={{ border: "1px solid #ddd", borderRadius: 8, padding: 12, marginTop: 12, background: r.simulated ? "#fffbeb" : "#f8fafc" }}>
          <strong>#{r.id} {r.label}</strong> <code>{r.state}</code> <span style={{ color: "#666", fontSize: 12 }}>{r.at}{r.simulated ? " · LOCAL" : ""}</span>
          <pre style={{ whiteSpace: "pre-wrap", fontSize: 12 }}>{r.detail}</pre>
        </div>
      ))}
    </main>
  );
}

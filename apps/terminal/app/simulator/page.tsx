"use client";
import { useEffect, useMemo, useState } from "react";
import { ModalBackendClient, friendlyError, type TxStatus } from "@hybridpay/sdk";
import {
  errorToResult, headline, localDemoResult, successToResult,
  type ExecutionMode, type ScenarioId, type UnifiedResult,
} from "../../src/simulator-results";

const MODAL_URL = process.env.NEXT_PUBLIC_MODAL_API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const DEV_TOKEN = process.env.NEXT_PUBLIC_API_TOKEN ?? "";

type Run = UnifiedResult & { id: number; label: string };

const SCENARIOS: { id: ScenarioId; bg: string; en: string }[] = [
  { id: "fiat-ok", bg: "Успешно фиат плащане (€10)", en: "Successful fiat payment (€10)" },
  { id: "fiat-fail", bg: "Отказано плащане (mock declined)", en: "Declined payment (mock declined)" },
  { id: "fiat-timeout", bg: "Timeout → UNKNOWN (query-original)", en: "Timeout → UNKNOWN (query-original)" },
  { id: "crypto-wrong", bg: "Грешна крипто мрежа (отхвърлено)", en: "Wrong crypto network (rejected)" },
  { id: "contract-bad", bg: "Договор с грешка (валидаторът хваща)", en: "Contract with error (validator catches)" },
];

export default function Simulator() {
  const [locale] = useState<"bg" | "en">("en");
  const [tenant] = useState("demo-tenant");
  // Token lives in memory only (useState) — never localStorage. Public builds
  // bake no default token: paste the operator token from the Modal Secret.
  const [token, setToken] = useState(DEV_TOKEN);
  const [tokenInput, setTokenInput] = useState("");
  const [runs, setRuns] = useState<Run[]>([]);
  const [busy, setBusy] = useState<ScenarioId | null>(null);
  // Explicit execution mode — Backend is the default; Local demo never
  // triggers silently and its results are always labeled LOCAL_SIMULATION.
  const [mode, setMode] = useState<ExecutionMode>("backend");
  const [health, setHealth] = useState("checking…");
  const modal = useMemo(() => new ModalBackendClient({ baseUrl: MODAL_URL, tenantId: tenant, token: token || undefined }), [tenant, token]);
  useEffect(() => {
    modal.health().then(
      (r) => { const d = r.data as { liveMode?: string; sandbox?: boolean }; setHealth(`reachable · liveMode ${d.liveMode ?? "?"} · sandbox ${String(d.sandbox ?? "?")}`); },
      (e) => setHealth(`UNREACHABLE · ${friendlyError(e, locale)}`),
    );
  }, [modal]);
  let seq = runs.length + 1;

  async function runScenario(s: ScenarioId) {
    if (busy) return;
    setBusy(s);
    const stamp = new Date().toLocaleTimeString();
    const label = SCENARIOS.find((x) => x.id === s)![locale];
    // Local demo mode: deterministic, no network, always labeled.
    if (mode === "local") {
      push({ ...localDemoResult(s, stamp), id: seq++, label });
      setBusy(null);
      return;
    }
    try {
      if (s === "fiat-ok" || s === "fiat-fail" || s === "fiat-timeout") {
        const suffix = s === "fiat-ok" ? "sim-ok" : s === "fiat-fail" ? "simfail" : "simtimeout";
        // Unique idempotency key per run: no auto-retry, no accidental 409.
        // On ambiguous timeouts reuse the SAME key — never mint a new payment.
        const r = await modal.fiatSimulate({ amountMinor: "1000", instructionId: `sim-${Date.now()}-${suffix}`, currency: "EUR" }, `sim-${Date.now()}-${s}`);
        push({ ...successToResult(s, r.data as unknown as Record<string, unknown>, stamp), id: seq++, label });
      } else if (s === "crypto-wrong") {
        try {
          const r = await modal.cryptoSimulate({ amountMinor: "50000", instructionId: `sim-${Date.now()}`, address: "tb1qwrong-mainnet-address" }, `sim-${Date.now()}-cry`);
          push({ ...successToResult(s, r.data as unknown as Record<string, unknown>, stamp), id: seq++, label });
        } catch (e) {
          push({ ...errorToResult(s, e, stamp), id: seq++, label });
        }
      } else {
        const r = await modal.validateContract({ amountMinor: "not-a-number", beneficiaries: [], conditions: [{ type: "evilEval" }], executionModel: "pay-after-condition" });
        push({ ...successToResult(s, ((r.data ?? {}) as unknown as Record<string, unknown>), stamp), id: seq++, label });
      }
    } catch (e) {
      // Backend error RESPONSE (401/409/422/502/…) or transport failure —
      // classified by errorToResult, never presented as "backend is fine".
      push({ ...errorToResult(s, e, stamp), id: seq++, label });
    } finally { setBusy(null); }
  }
  function push(r: Run) { setRuns((prev) => [r, ...prev].slice(0, 20)); }

  return (
    <main style={{ fontFamily: "system-ui", padding: 24, maxWidth: 820 }}>
      <div style={{ background: "#111", color: "#fff", padding: 8, borderRadius: 8 }}>
        {locale === "bg" ? "СИМУЛАТОР — само пробни транзакции, без реални пари." : "SIMULATOR — trial transactions only, no real money."}
      </div>
      <div style={{ marginTop: 8 }}>
        <a href="/">{locale === "bg" ? "← Обратно към терминала" : "← Back to terminal"}</a>
      </div>
      <h1>{locale === "bg" ? "Визуален симулатор за пробни тестове" : "Visual simulator for trial tests"}</h1>
      <p style={{ color: "#555" }}>Modal: {MODAL_URL} · backend: <code>{health}</code> · {locale === "bg" ? "Всеки сценарий е безопасен — sandbox/testnet или изрично обозначена локална симулация." : "Every scenario is safe — sandbox/testnet or explicitly labeled local simulation."}</p>
      <fieldset style={{ marginTop: 8, border: "1px solid #ddd", borderRadius: 8, padding: 8 }}>
        <legend>Execution mode</legend>
        <label style={{ display: "flex", gap: 6, alignItems: "center", marginTop: 4 }}>
          <input type="radio" name="exec-mode" checked={mode === "backend"} onChange={() => setMode("backend")} />
          Backend sandbox (default — real HTTP to the Modal backend; failures shown as-is, no silent fallback)
        </label>
        <label style={{ display: "flex", gap: 6, alignItems: "center", marginTop: 4 }}>
          <input type="radio" name="exec-mode" checked={mode === "local"} onChange={() => setMode("local")} />
          Local demo (explicit — deterministic, no network; every result labeled LOCAL_SIMULATION)
        </label>
      </fieldset>
      <div style={{ marginTop: 8, display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
        <label>Token: <input type="password" value={tokenInput} onChange={(e) => setTokenInput(e.target.value)} autoComplete="off" placeholder={token ? "••••••" : "operator token"} /></label>
        <button onClick={() => { setToken(tokenInput.trim()); setTokenInput(""); }}>Sign in</button>
        <button onClick={() => { setToken(""); setTokenInput(""); }}>Logout</button>
        <span style={{ color: token ? "#15803d" : "#b45309" }}>{token ? "signed in" : "no token — backend scenarios will return 401"}</span>
      </div>
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
        <div key={r.id} style={{ border: "1px solid #ddd", borderRadius: 8, padding: 12, marginTop: 12, background: r.executionSource === "LOCAL_SIMULATION" ? "#fffbeb" : r.testOutcome === "PASSED" ? "#f0fdf4" : "#fef2f2" }}>
          <strong>#{r.id} {r.label}</strong> <span style={{ color: "#666", fontSize: 12 }}>{r.timestamp}{r.executionSource === "LOCAL_SIMULATION" ? " · LOCAL" : ""}</span>
          <p style={{ margin: "6px 0", fontWeight: 600 }}>{headline(r)}</p>
          <dl style={{ display: "grid", gridTemplateColumns: "150px 1fr", gap: "2px 8px", fontSize: 12, margin: 0 }}>
            <dt>scenarioId</dt><dd><code>{r.scenarioId}</code></dd>
            <dt>transactionId</dt><dd><code>{r.transactionId ?? "—"}</code></dd>
            <dt>paymentState</dt><dd><code>{r.paymentState}</code></dd>
            <dt>testOutcome</dt><dd><code>{r.testOutcome}</code></dd>
            <dt>executionSource</dt><dd><code>{r.executionSource}</code></dd>
            <dt>providerReference</dt><dd><code>{r.providerReference ?? "—"}</code></dd>
            <dt>errorCode</dt><dd><code>{r.errorCode ?? "—"}</code></dd>
            <dt>sandbox</dt><dd><code>{String(r.sandbox)}</code></dd>
          </dl>
          <pre style={{ whiteSpace: "pre-wrap", fontSize: 12, marginTop: 6 }}>{r.userMessage}</pre>
        </div>
      ))}
    </main>
  );
}

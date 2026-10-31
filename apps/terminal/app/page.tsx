"use client";
import { useState } from "react";
import { dict, type Locale } from "../src/i18n";

export default function Home() {
  const [locale, setLocale] = useState<Locale>("bg");
  const [amount, setAmount] = useState("10.00");
  const [qr, setQr] = useState<string | null>(null);
  const t = dict[locale];
  async function create() {
    const [eur, cents = "00"] = amount.split(".");
    const minor = `${eur}${cents.padEnd(2, "0").slice(0, 2)}`;
    const o = await fetch("http://localhost:3001/v1/orders", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Tenant-Id": "demo-tenant", "Idempotency-Key": `ui-${Date.now()}` },
      body: JSON.stringify({ storeId: "store-1", denomination: "fiat:EUR", totalMinor: minor }),
    }).then((r) => r.json());
    const tok = await fetch(`http://localhost:3001/v1/orders/${o.id}/checkout-token`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Tenant-Id": "demo-tenant" },
      body: JSON.stringify({ agreementVersion: 1 }),
    }).then((r) => r.json());
    setQr(tok.qrPayload);
  }
  return (
    <main style={{ fontFamily: "system-ui", padding: 24, maxWidth: 640 }}>
      <button onClick={() => setLocale(locale === "bg" ? "en" : "bg")}>{locale === "bg" ? "EN" : "БГ"}</button>
      <h1>HybridPay Terminal — {t.newOrder}</h1>
      <label>{t.amount}: <input value={amount} onChange={(e) => setAmount(e.target.value)} /></label>
      <button onClick={create}>{t.create}</button>
      {qr && (<div><p>{t.scan}</p><code style={{ wordBreak: "break-all" }}>{qr}</code>
        <p><strong>{t.receipt}</strong></p></div>)}
    </main>
  );
}

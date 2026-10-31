"use client";
import * as React from "react";
import { ModalBackendClient, ApiError, friendlyError } from "@hybridpay/sdk";
import { FIAT_CURRENCIES } from "../currencies";
import { Alert } from "./ui/feedback";
import { Button } from "./ui/button";
import { Card, CardTitle } from "./ui/card";
import { Field, Input, Select } from "./ui/field";

export function FiatPayForm({ modal, locale, compact }: { modal: ModalBackendClient; locale: "bg" | "en"; compact?: boolean }) {
  const [ccy, setCcy] = React.useState("EUR");
  const [amt, setAmt] = React.useState("1000");
  const [ins, setIns] = React.useState(`demo-${Date.now().toString(36)}`);
  const [out, setOut] = React.useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = React.useState(false);

  async function submit() {
    if (busy || !/^\d+$/.test(amt)) { if (!/^\d+$/.test(amt)) setOut({ ok: false, text: locale === "bg" ? "Сумата трябва да е цяло число (minor units)." : "Amount must be an integer (minor units)." }); return; }
    setBusy(true); setOut(null);
    try {
      const created = await modal.fiatCreate({ amountMinor: amt, instructionId: ins, currency: ccy }, `ui-${Date.now()}`);
      const pid = (created.data as { paymentId: string }).paymentId;
      const confirmed = await modal.fiatConfirm(pid);
      setOut({ ok: true, text: `${pid} → ${(confirmed.data as { state: string }).state}` });
    } catch (e) {
      const r = e instanceof ApiError && e.retryable;
      setOut({ ok: false, text: friendlyError(e, locale) + (r ? (locale === "bg" ? " — безопасно е да опитате отново." : " — safe to retry.") : "") });
    } finally { setBusy(false); }
  }

  return (
    <Card>
      <CardTitle>{locale === "bg" ? "💶 Фиатно плащане (sandbox)" : "💶 Fiat payment (sandbox)"}</CardTitle>
      <div className={compact ? "" : "grid grid-cols-1 gap-3 md:grid-cols-3"}>
        <Field label={locale === "bg" ? "Валута" : "Currency"}>
          <Select value={ccy} onChange={(e) => setCcy(e.target.value)}>
            {FIAT_CURRENCIES.map((c) => <option key={c.code} value={c.code}>{c.code} — {locale === "bg" ? c.nameBg : c.nameEn} ({c.symbol})</option>)}
          </Select>
        </Field>
        <Field label={locale === "bg" ? "Сума (minor units)" : "Amount (minor units)"}>
          <Input value={amt} onChange={(e) => setAmt(e.target.value)} inputMode="numeric" />
        </Field>
        <Field label="Instruction ID">
          <Input value={ins} onChange={(e) => setIns(e.target.value)} />
        </Field>
      </div>
      <Button disabled={busy} onClick={submit} aria-live="polite">
        {busy ? (locale === "bg" ? "Работи…" : "Working…") : (locale === "bg" ? "Създай и потвърди" : "Create & confirm")}
      </Button>
      {out && <div className="mt-3"><Alert tone={out.ok ? "ok" : "danger"}>{out.text}</Alert></div>}
    </Card>
  );
}

"use client";
import { User } from "lucide-react";
import Link from "next/link";
import * as React from "react";
import AssistantPanel from "../../src/AssistantPanel";
import DashboardPanel from "../../src/DashboardPanel";
import { FiatPayForm } from "../../src/components/fiat-pay-form";
import { Shell } from "../../src/components/shell";
import { useSession } from "../../src/components/session";
import { Card, CardTitle } from "../../src/components/ui/card";
import { Tabs } from "../../src/components/ui/tabs";

export default function PersonalPage() {
  const [locale, setLocale] = React.useState<"bg" | "en">("bg");
  const s = useSession();
  const [view, setView] = React.useState("pay");
  const t = (bg: string, en: string) => (locale === "bg" ? bg : en);

  return (
    <Shell locale={locale} role={s.role}>
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <h1 className="flex items-center gap-2 text-2xl font-extrabold"><User aria-hidden /> {t("Личен портфейл", "Personal Wallet")}</h1>
        <span className="rounded-full bg-[rgb(var(--info-bg))] px-2.5 py-0.5 text-xs font-bold text-[rgb(var(--info))]">SANDBOX</span>
        <button onClick={() => setLocale(locale === "bg" ? "en" : "bg")} className="ml-auto rounded-full border border-line px-3 py-1 text-sm font-semibold">
          {locale === "bg" ? "EN" : "БГ"}
        </button>
      </div>
      <p className="muted mb-2">{t("Плащайте и следете вашата активност — само вашите данни, без реални пари.", "Pay and track your activity — only your data, no real money.")}</p>

      <div className="mb-3 flex items-center gap-2">
        <label className="text-sm font-semibold">{t("Тенант", "Tenant")}: <input value={s.tenant} onChange={(e) => s.setTenant(e.target.value)} autoComplete="off" className="rounded-[10px] border border-line bg-surface px-3 py-2" /></label>
        <Link href="/#order" className="text-sm underline">{t("QR каса (терминал) →", "QR checkout (terminal) →")}</Link>
      </div>

      <Tabs label="personal views" value={view} onChange={setView} tabs={[
        { id: "pay", label: t("Плати", "Pay") },
        { id: "activity", label: t("Моите плащания", "My activity") },
        { id: "assistant", label: t("Асистент", "Assistant") },
      ]} />

      {view === "pay" && (
        <div className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-2">
          <FiatPayForm modal={s.modal} locale={locale} compact />
          <Card>
            <CardTitle>{t("Крипто (testnet)", "Crypto (testnet)")}</CardTitle>
            <p className="muted text-sm">{t("За Sepolia ETH използвайте EVM таба на терминала с вашия портфейл — ключовете не напускат устройството.", "For Sepolia ETH use the terminal EVM tab with your wallet — keys never leave your device.")}</p>
            <p className="mt-2 text-sm"><Link className="underline" href="/#evm">→ {t("Към EVM", "To EVM")}</Link></p>
          </Card>
        </div>
      )}
      {view === "activity" && (
        <Card>
          <CardTitle>{t("Моите плащания", "My activity")}</CardTitle>
          <DashboardPanel modal={s.modal} locale={locale} />
        </Card>
      )}
      {view === "assistant" && (
        <Card>
          <AssistantPanel modal={s.modal} locale={locale} />
        </Card>
      )}
    </Shell>
  );
}

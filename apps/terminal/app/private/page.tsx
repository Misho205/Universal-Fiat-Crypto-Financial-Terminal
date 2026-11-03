"use client";
import { LockKeyhole } from "lucide-react";
import * as React from "react";
import { useSession } from "../../src/components/session";
import { Shell } from "../../src/components/shell";
import { Button } from "../../src/components/ui/button";
import { Alert } from "../../src/components/ui/feedback";
import { Field, Input } from "../../src/components/ui/field";
import { AccessGate, EnvBadge, SectionCard, TenantRoleStrip, WorkspaceHeader } from "../../src/components/workspace";

/** Private Workspace: staff-only surface with the same sign-in model as Banking.
 * Token lives in memory only (useSession) — never localStorage, never baked in. */
export default function PrivatePage() {
  const [locale] = React.useState<"bg" | "en">("en");
  const s = useSession();
  const isAdmin = s.role === "admin";
  const t = (bg: string, en: string) => (locale === "bg" ? bg : en);

  return (
    <Shell locale={locale} role={s.role}>
      <WorkspaceHeader
        eyebrow={t("Частен терминал", "Private terminal")}
        title={t("Частен работен плот", "Private Workspace")}
        description={t("Служебен достъп — четенето работи с operator токен, чувствителните действия искат admin.",
          "Staff access — reading works with an operator token, sensitive actions need admin.")}
        badge={<span className="flex gap-2"><EnvBadge tone="sandbox">SANDBOX</EnvBadge><EnvBadge tone="admin">PRIVATE</EnvBadge></span>}
        status={{ tenant: s.tenant, role: s.role, backend: "modal sandbox" }}
      />
      {/* Same gate as Banking: shows only until an admin token is signed in. */}
      <AccessGate isAdmin={isAdmin} signIn={(v) => s.signIn(v)}
        label={t("Пълен достъп изисква admin токен. Четенето работи с operator токен.",
          "Full access requires an admin token. Reading works with an operator token.")} />

      <TenantRoleStrip tenant={s.tenant} role={s.role} isAdmin={isAdmin} />
      <div className="mb-3 flex flex-wrap items-end gap-2">
        <Field label={t("Тенант", "Tenant")}>
          <Input value={s.tenant} onChange={(e) => s.setTenant(e.target.value)} autoComplete="off" />
        </Field>
      </div>

      {/* Same sign-in card as Banking → Administration: token input + Sign in / Log out. */}
      <SignInCard
        modal={s.modal} tenant={s.tenant} role={s.role} isAdmin={isAdmin}
        tokenInput={s.tokenInput} setTokenInput={s.setTokenInput}
        onSign={() => { s.signIn(s.tokenInput); }} onLogout={s.logout} locale={locale} />
    </Shell>
  );
}

function SignInCard({ modal, tenant, role, isAdmin, tokenInput, setTokenInput, onSign, onLogout, locale }: {
  modal: { health: () => Promise<{ data: unknown }> }; tenant: string; role: string; isAdmin: boolean;
  tokenInput: string; setTokenInput: (v: string) => void;
  onSign: () => void; onLogout: () => void; locale: "bg" | "en";
}) {
  const [health, setHealth] = React.useState("");
  React.useEffect(() => {
    modal.health().then(
      (r) => setHealth(JSON.stringify(r.data)),
      (e) => setHealth(String(e).slice(0, 160)),
    );
  }, [modal]);
  return (
    <SectionCard title={locale === "bg" ? "Организация и вход" : "Organization & sign-in"}>
      <p className="text-sm">{locale === "bg" ? "Тенант" : "Tenant"}: <code>{tenant}</code></p>
      <p className="text-sm">{locale === "bg" ? "Роля" : "Role"}: <code>{role}</code> {isAdmin ? "(admin)" : "(operator)"}</p>
      <p className="text-sm">Backend health: <code>{health || "—"}</code></p>
      <div className="mt-2 flex flex-wrap items-center gap-2">
        <span className="flex items-center gap-1.5 text-sm font-semibold">
          <LockKeyhole size={15} aria-hidden />{locale === "bg" ? "Токен за вход" : "Sign-in token"}
        </span>
        <input type="password" value={tokenInput} onChange={(e) => setTokenInput(e.target.value)}
          placeholder={locale === "bg" ? "операторски или admin токен" : "operator or admin token"}
          aria-label={locale === "bg" ? "Токен за вход" : "Sign-in token"} autoComplete="off"
          className="rounded-[10px] border border-line bg-surface px-3 py-2" />
        <Button size="sm" onClick={onSign}>{locale === "bg" ? "Вход" : "Sign in"}</Button>
        <Button size="sm" variant="secondary" onClick={onLogout}>{locale === "bg" ? "Изход" : "Log out"}</Button>
      </div>
      {!tokenInput && !isAdmin && (
        <div className="mt-2">
          <Alert tone="warn">{locale === "bg"
            ? "Без вход заявките връщат 401. Поставете операторския токен от Modal Secret-а hybridpay-test."
            : "Without sign-in, requests return 401. Paste the operator token from the hybridpay-test Modal Secret."}</Alert>
        </div>
      )}
      <p className="muted mt-2 text-xs">{locale === "bg"
        ? "Токенът стои само в паметта на браузъра — никога в localStorage и никога в готовия bundle."
        : "The token lives only in browser memory — never in localStorage and never in the built bundle."}
</p>
    </SectionCard>
  );
}

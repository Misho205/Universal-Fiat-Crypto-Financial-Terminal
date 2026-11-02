"use client";
import { ArrowLeftRight, FlaskConical, Home, Landmark, LayoutDashboard, User } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import * as React from "react";
import { BRAND, isEmbedMode } from "../brand";
import { cn } from "../lib/cn";
import { ThemeToggle } from "./ui/theme-toggle";

const NAV = [
  { href: "/", labelEn: "Terminal", labelBg: "Терминал", icon: Home },
  { href: "/banking", labelEn: "Banking", labelBg: "Банкиране", icon: Landmark, admin: true },
  { href: "/personal", labelEn: "Personal", labelBg: "Лично", icon: User },
  { href: "/design-system", labelEn: "Design system", labelBg: "Дизайн система", icon: LayoutDashboard },
  { href: "/simulator", labelEn: "Simulator", labelBg: "Симулатор", icon: FlaskConical },
];

export function Shell({ children, locale = "en", role = "—" }: { children: React.ReactNode; locale?: string; role?: string }) {
  const path = usePathname();
  const [embed, setEmbed] = React.useState(false);
  React.useEffect(() => { setEmbed(isEmbedMode()); }, []);
  const brandName = BRAND.logoText || BRAND.name;
  if (embed) {
    return (
      <div className="min-h-screen bg-bg text-ink">
        <main id="main" className="mx-auto max-w-6xl px-4 pb-10 pt-4">{children}</main>
      </div>
    );
  }
  return (
    <div className="min-h-screen bg-bg text-ink">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:rounded focus:bg-surface focus:p-2">
        {locale === "bg" ? "Към съдържанието" : "Skip to content"}
      </a>
      <header className="border-b border-line bg-surface/95 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center gap-3 px-4 py-3">
          <Link href="/" className="brand-lockup flex items-center gap-2 font-extrabold" aria-label={`${brandName} Terminal`}>
            <span className="brand-mark flex h-8 w-8 items-center justify-center rounded-xl bg-brand-900 text-white dark:bg-brand-100" aria-hidden>
              <ArrowLeftRight size={17} />
            </span>
            {brandName}
          </Link>
          <span className="env-badge rounded-full bg-[rgb(var(--warn-bg))] px-2.5 py-0.5 text-xs font-bold text-[rgb(var(--warn))]">SANDBOX</span>
          <div className="ml-auto flex items-center gap-2">
            <span className="role-chip text-xs text-muted">role: <code>{role}</code></span>
            <ThemeToggle locale={locale} />
          </div>
        </div>
        <nav aria-label={locale === "bg" ? "Основна навигация" : "Primary"} className="mx-auto flex max-w-6xl gap-1 overflow-x-auto px-4 pb-3">
          {NAV.map((n) => {
            const active = path === n.href || (n.href !== "/" && path.startsWith(n.href));
            const Icon = n.icon;
            return (
              <Link key={n.href} href={n.href} aria-current={active ? "page" : undefined}
                className={cn("flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-sm font-semibold transition-colors",
                  active ? "border-brand-900 bg-brand-900 text-white dark:bg-brand-100" : "border-line bg-surface text-ink hover:border-brand-600")}>
                <Icon size={15} aria-hidden />{locale === "bg" ? n.labelBg : n.labelEn}
                {n.admin && <span className="text-[10px] opacity-70">ADMIN</span>}
              </Link>
            );
          })}
        </nav>
      </header>
      <main id="main" className="mx-auto max-w-6xl px-4 pb-16 pt-6">{children}</main>
      <footer className="border-t border-line py-4 text-center text-xs text-muted">
        {brandName} sandbox — {locale === "bg" ? "без реални пари. Техническата бележка НЕ е фискален бон." : "no real money. Technical receipt is NOT a fiscal receipt."}
        {BRAND.supportUrl && <> · <a className="underline" href={BRAND.supportUrl}>{locale === "bg" ? "Поддръжка" : "Support"}</a></>}
      </footer>
    </div>
  );
}

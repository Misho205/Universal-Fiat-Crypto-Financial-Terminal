"use client";
import { ArrowLeftRight, Bot, FileText, FlaskConical, Home, Landmark, LayoutDashboard, Scale, User, Wallet } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "../lib/cn";
import { ThemeToggle } from "./ui/theme-toggle";

const NAV = [
  { href: "/", labelEn: "Terminal", labelBg: "Терминал", icon: Home },
  { href: "/banking", labelEn: "Banking", labelBg: "Банкиране", icon: Landmark, admin: true },
  { href: "/personal", labelEn: "Personal", labelBg: "Лично", icon: User },
  { href: "/design-system", labelEn: "Design system", labelBg: "Дизайн система", icon: LayoutDashboard },
  { href: "/simulator", labelEn: "Simulator", labelBg: "Симулатор", icon: FlaskConical },
];

export function Shell({ children, locale = "bg", role = "—" }: { children: React.ReactNode; locale?: string; role?: string }) {
  const path = usePathname();
  return (
    <div className="min-h-screen bg-bg text-ink">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:rounded focus:bg-surface focus:p-2">
        {locale === "bg" ? "Към съдържанието" : "Skip to content"}
      </a>
      <header className="border-b border-line bg-surface">
        <div className="mx-auto flex max-w-6xl items-center gap-3 px-4 py-3">
          <Link href="/" className="flex items-center gap-2 font-extrabold" aria-label="HybridPay Terminal">
            <ArrowLeftRight size={20} aria-hidden /> HybridPay
          </Link>
          <span className="rounded-full bg-[rgb(var(--warn-bg))] px-2.5 py-0.5 text-xs font-bold text-[rgb(var(--warn))]">SANDBOX</span>
          <div className="ml-auto flex items-center gap-2">
            <span className="text-xs text-muted">role: <code>{role}</code></span>
            <ThemeToggle locale={locale} />
          </div>
        </div>
        <nav aria-label={locale === "bg" ? "Основна навигация" : "Primary"} className="mx-auto flex max-w-6xl gap-1 overflow-x-auto px-4 pb-3">
          {NAV.map((n) => {
            const active = path === n.href || (n.href !== "/" && path.startsWith(n.href));
            const Icon = n.icon;
            return (
              <Link key={n.href} href={n.href} aria-current={active ? "page" : undefined}
                className={cn("flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-sm font-semibold",
                  active ? "border-brand-900 bg-brand-900 text-white dark:bg-brand-100" : "border-line bg-surface text-ink")}>
                <Icon size={15} aria-hidden />{locale === "bg" ? n.labelBg : n.labelEn}
                {n.admin && <span className="text-[10px] opacity-70">ADMIN</span>}
              </Link>
            );
          })}
        </nav>
      </header>
      <main id="main" className="mx-auto max-w-6xl px-4 pb-16 pt-6">{children}</main>
      <footer className="border-t border-line py-4 text-center text-xs text-muted">
        HybridPay sandbox — {locale === "bg" ? "без реални пари. Техническата бележка НЕ е фискален бон." : "no real money. Technical receipt is NOT a fiscal receipt."}
      </footer>
    </div>
  );
}

export const workspaceIcons = { FileText, Wallet, Bot, Scale };

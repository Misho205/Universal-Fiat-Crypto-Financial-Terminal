"use client";
import { Moon, Sun } from "lucide-react";
import { useTheme } from "next-themes";
import * as React from "react";

export function ThemeToggle({ locale = "en" }: { locale?: string }) {
  const { theme, setTheme, resolvedTheme } = useTheme();
  const [mounted, setMounted] = React.useState(false);
  React.useEffect(() => setMounted(true), []);
  const dark = (theme === "system" ? resolvedTheme : theme) === "dark";
  return (
    <button onClick={() => setTheme(dark ? "light" : "dark")}
      aria-label={locale === "bg" ? "Превключи тема" : "Toggle theme"}
      aria-pressed={dark}
      className="rounded-full border border-line bg-surface p-2 text-ink">
      {mounted ? (dark ? <Sun size={18} aria-hidden /> : <Moon size={18} aria-hidden />) : <span aria-hidden>○</span>}
    </button>
  );
}

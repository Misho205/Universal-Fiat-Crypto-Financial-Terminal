"use client";
import * as React from "react";
import { cn } from "../../lib/cn";

/** Keyboard-operable tabs: arrows move, Home/End jump, roving tabindex. */
export function Tabs({ tabs, value, onChange, label }: {
  tabs: { id: string; label: string }[]; value: string; onChange: (id: string) => void; label: string;
}) {
  const refs = React.useRef<(HTMLButtonElement | null)[]>([]);
  function onKey(e: React.KeyboardEvent, i: number) {
    let n: number | null = null;
    if (e.key === "ArrowRight") n = (i + 1) % tabs.length;
    if (e.key === "ArrowLeft") n = (i - 1 + tabs.length) % tabs.length;
    if (e.key === "Home") n = 0;
    if (e.key === "End") n = tabs.length - 1;
    if (n !== null) { e.preventDefault(); onChange(tabs[n].id); refs.current[n]?.focus(); }
  }
  return (
    <div role="tablist" aria-label={label} className="flex flex-wrap gap-2">
      {tabs.map((t, i) => (
        <button key={t.id} ref={(el) => { refs.current[i] = el; }} role="tab" aria-selected={value === t.id}
          tabIndex={value === t.id ? 0 : -1} onKeyDown={(e) => onKey(e, i)} onClick={() => onChange(t.id)}
          className={cn("rounded-full border px-3.5 py-2 text-sm font-semibold",
            value === t.id ? "border-brand-900 bg-brand-900 text-white dark:bg-brand-100" : "border-line bg-surface text-ink")}>
          {t.label}
        </button>
      ))}
    </div>
  );
}

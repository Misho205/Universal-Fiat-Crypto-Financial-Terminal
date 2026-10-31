"use client";
import * as React from "react";
import { cn } from "../../lib/cn";

/** Accessible dialog: Escape closes, focus moves in/out, aria-modal. No animation clutter. */
export function Dialog({ open, onClose, title, children, labelledBy }: {
  open: boolean; onClose: () => void; title: string; children: React.ReactNode; labelledBy?: string;
}) {
  const ref = React.useRef<HTMLDivElement>(null);
  const titleId = labelledBy ?? React.useId();
  React.useEffect(() => {
    if (!open) return;
    const prev = document.activeElement as HTMLElement | null;
    ref.current?.querySelector<HTMLElement>("[data-autofocus]")?.focus()
      ?? ref.current?.querySelector<HTMLElement>("button")?.focus();
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", onKey);
    return () => { document.removeEventListener("keydown", onKey); prev?.focus(); };
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div ref={ref} role="dialog" aria-modal="true" aria-labelledby={titleId}
        className="w-full max-w-md rounded-2xl border border-line bg-surface p-5 shadow-pop">
        <h2 id={titleId} className="mb-3 text-lg font-bold">{title}</h2>
        {children}
      </div>
    </div>
  );
}

/** Confirmation dialog for money-affecting actions. Destructive actions need explicit confirm. */
export function ConfirmDialog({ open, onClose, onConfirm, title, body, confirmLabel, danger }: {
  open: boolean; onClose: () => void; onConfirm: () => void; title: string; body: string;
  confirmLabel: string; danger?: boolean;
}) {
  return (
    <Dialog open={open} onClose={onClose} title={title}>
      <p className="muted mb-4">{body}</p>
      <div className="flex justify-end gap-2">
        <button onClick={onClose} className="rounded-[10px] border border-line px-4 py-2 text-sm font-semibold">Cancel</button>
        <button data-autofocus onClick={() => { onConfirm(); onClose(); }}
          className={cn("rounded-[10px] px-4 py-2 text-sm font-semibold text-white",
            danger ? "bg-[rgb(var(--danger))]" : "bg-brand-600")}>{confirmLabel}</button>
      </div>
    </Dialog>
  );
}

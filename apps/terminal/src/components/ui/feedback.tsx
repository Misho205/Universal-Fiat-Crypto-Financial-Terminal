import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "../../lib/cn";

const alertVariants = cva("rounded-xl border p-3 text-sm", {
  variants: {
    tone: {
      info: "border-[rgb(var(--info)/0.35)] bg-[rgb(var(--info-bg))] text-[rgb(var(--info))]",
      ok: "border-[rgb(var(--ok)/0.35)] bg-[rgb(var(--ok-bg))] text-[rgb(var(--ok))]",
      warn: "border-[rgb(var(--warn)/0.35)] bg-[rgb(var(--warn-bg))] text-[rgb(var(--warn))]",
      danger: "border-[rgb(var(--danger)/0.35)] bg-[rgb(var(--danger-bg))] text-[rgb(var(--danger))]",
    },
  },
  defaultVariants: { tone: "info" },
});

export function Alert({ className, tone, role, ...props }: React.HTMLAttributes<HTMLDivElement> & VariantProps<typeof alertVariants> & { role?: string }) {
  const danger = tone === "danger" || tone === "warn";
  return <div role={role ?? (danger ? "alert" : "status")} className={cn(alertVariants({ tone }), className)} {...props} />;
}

export function Skeleton({ className, label = "Loading" }: { className?: string; label?: string }) {
  return <div role="status" aria-label={label} className={cn("animate-pulse rounded-lg bg-[rgb(var(--line))]", className ?? "h-4 w-full")} />;
}

export function EmptyState({ title, body }: { title: string; body?: string }) {
  return (
    <div className="rounded-xl border border-dashed border-line p-6 text-center">
      <p className="font-semibold">{title}</p>
      {body && <p className="muted mt-1 text-sm">{body}</p>}
    </div>
  );
}

import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "../../lib/cn";
import { stateTone, type StateTone } from "../../tokens";

const badgeVariants = cva(
  "inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-semibold",
  {
    variants: {
      tone: {
        ok: "bg-[rgb(var(--ok-bg))] text-[rgb(var(--ok))]",
        warn: "bg-[rgb(var(--warn-bg))] text-[rgb(var(--warn))]",
        danger: "bg-[rgb(var(--danger-bg))] text-[rgb(var(--danger))]",
        info: "bg-[rgb(var(--info-bg))] text-[rgb(var(--info))]",
        muted: "bg-[rgb(var(--line))] text-[rgb(var(--muted))]",
      } satisfies Record<StateTone, string>,
    },
    defaultVariants: { tone: "muted" },
  }
);

export function Badge({ className, tone, ...props }: React.HTMLAttributes<HTMLSpanElement> & VariantProps<typeof badgeVariants>) {
  return <span className={cn(badgeVariants({ tone }), className)} {...props} />;
}

/** Accessible status badge: icon dot + text label (never color alone). */
export function StatusBadge({ state, className }: { state: string; className?: string }) {
  const tone = stateTone(state);
  const dot = tone === "ok" ? "●" : tone === "warn" ? "◐" : tone === "danger" ? "■" : tone === "info" ? "○" : "–";
  return (
    <span className={cn(badgeVariants({ tone }), className)} aria-label={`status: ${state}`}>
      <span aria-hidden="true">{dot}</span> {state}
    </span>
  );
}

/** Sandbox vs live marker — simulated payments are always labeled. */
export function SandboxBadge({ sandbox = true }: { sandbox?: boolean }) {
  return sandbox ? (
    <span className={cn(badgeVariants({ tone: "warn" }))} title="Simulated/testnet — no real money">
      ◐ SANDBOX
    </span>
  ) : (
    <span className={cn(badgeVariants({ tone: "danger" }))} title="Real funds">
      ■ LIVE
    </span>
  );
}

"use client";
import type { LucideIcon } from "lucide-react";
import { Building2, ShieldCheck, UserRound } from "lucide-react";
import * as React from "react";
import { cn } from "../lib/cn";
import { Alert } from "./ui/feedback";

/* ---------- Workspace header: eyebrow + title + status strip ---------- */

export function WorkspaceHeader({ eyebrow, title, description, badge, status }: {
  eyebrow: string; title: string; description: string;
  badge?: React.ReactNode; status?: { tenant: string; role: string; backend: string };
}) {
  return (
    <div className="ws-hero">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="ws-eyebrow">{eyebrow}</p>
          <h1 className="ws-title">{title}</h1>
          <p className="ws-sub">{description}</p>
        </div>
        {badge}
      </div>
      {status && (
        <dl className="ws-status" aria-label="Workspace status">
          <div><dt>Tenant</dt><dd><code>{status.tenant}</code></dd></div>
          <div><dt>Role</dt><dd><code>{status.role}</code></dd></div>
          <div><dt>Backend</dt><dd><code>{status.backend}</code></dd></div>
        </dl>
      )}
    </div>
  );
}

export function EnvBadge({ tone, children }: { tone: "sandbox" | "admin" | "live"; children: React.ReactNode }) {
  return (
    <span className={cn("env-badge",
      tone === "sandbox" && "env-sandbox", tone === "admin" && "env-admin", tone === "live" && "env-live")}>
      {children}
    </span>
  );
}

/* ---------- Section navigation (icon tabs, professional labels) ---------- */

export interface Section { id: string; label: string; icon: LucideIcon; adminOnly?: boolean }

export function SectionNav<T extends string>({ label, sections, value, onChange, lockedAdmin }: {
  label: string; sections: Section[]; value: T; onChange: (v: T) => void; lockedAdmin?: boolean;
}) {
  return (
    <nav aria-label={label} className="ws-nav">
      <ul>
        {sections.map((s) => {
          const Icon = s.icon;
          const active = value === s.id;
          const locked = !!s.adminOnly && lockedAdmin;
          return (
            <li key={s.id}>
              <button type="button" aria-current={active ? "page" : undefined}
                onClick={() => onChange(s.id as T)}
                className={cn("ws-nav-item", active && "ws-nav-active")}>
                <Icon size={16} aria-hidden />
                <span>{s.label}</span>
                {locked && <span className="ws-lock" title="Requires admin token">🔒</span>}
              </button>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}

/* ---------- KPI cards ---------- */

export function KpiCard({ label, value, sub, icon: Icon, tone }: {
  label: string; value: string | number; sub?: string; icon?: LucideIcon; tone?: "ok" | "warn" | "danger" | "info";
}) {
  return (
    <div className={cn("kpi", tone && `kpi-${tone}`)}>
      <div className="kpi-top">
        <p className="kpi-label">{label}</p>
        {Icon && <Icon size={18} aria-hidden className="kpi-icon" />}
      </div>
      <p className="kpi-value num">{value}</p>
      {sub && <p className="kpi-sub">{sub}</p>}
    </div>
  );
}

export function KpiGrid({ children }: { children: React.ReactNode }) {
  return <div className="kpi-grid">{children}</div>;
}

/* ---------- Section card with header + optional actions ---------- */

export function SectionCard({ title, hint, actions, children, wide }: {
  title: string; hint?: string; actions?: React.ReactNode; children: React.ReactNode; wide?: boolean;
}) {
  return (
    <section className={cn("ws-card", wide && "ws-card-wide")} aria-label={title}>
      <div className="ws-card-head">
        <div>
          <h2 className="ws-card-title">{title}</h2>
          {hint && <p className="ws-card-hint">{hint}</p>}
        </div>
        {actions && <div className="ws-card-actions">{actions}</div>}
      </div>
      <div className="ws-card-body">{children}</div>
    </section>
  );
}

/* ---------- Status timeline for payment/agreement detail ---------- */

const STATE_ORDER = ["requested", "created", "pending", "conditions_pending", "eligible_for_execution",
  "succeeded", "confirmed", "completed", "failed", "canceled", "refunded", "expired", "disputed", "replaced", "unknown"];

export function StatusTimeline({ state }: { state: string }) {
  const idx = STATE_ORDER.indexOf(state);
  const terminal = ["succeeded", "confirmed", "completed", "failed", "canceled", "refunded", "expired"];
  const steps = ["Initiated", "Processing", terminal.includes(state) ? `Terminal · ${state}` : "Awaiting outcome"];
  return (
    <ol className="timeline" aria-label={`Status timeline, current state ${state}`}>
      {steps.map((s, i) => (
        <li key={s} aria-current={i === steps.length - 1 ? "step" : undefined}
          className={cn("timeline-step", i < steps.length - 1 && "timeline-done", i === steps.length - 1 && "timeline-now")}>
          <span className="timeline-dot" aria-hidden />
          <span>{s}</span>
        </li>
      ))}
      {idx === -1 && <li className="timeline-step"><span>{`state: ${state}`}</span></li>}
    </ol>
  );
}

/* ---------- Access gate notice ---------- */

export function AccessGate({ isAdmin, signIn, label }: {
  isAdmin: boolean; signIn: (v: string) => void; label: string;
}) {
  const [v, setV] = React.useState("");
  if (isAdmin) return null;
  return (
    <Alert tone="warn" className="ws-gate">
      <span className="flex items-center gap-1.5 font-semibold"><ShieldCheck size={15} aria-hidden />{label}</span>
      <span className="mt-2 flex gap-2">
        <input type="password" value={v} onChange={(e) => setV(e.target.value)} placeholder="Admin token"
          aria-label="Admin token" className="ws-gate-input" />
        <button type="button" className="ws-gate-btn" onClick={() => { signIn(v); setV(""); }}>Sign in</button>
      </span>
    </Alert>
  );
}

export function TenantRoleStrip({ tenant, role, isAdmin }: { tenant: string; role: string; isAdmin: boolean }) {
  return (
    <p className="ws-context" aria-label="Tenant and role context">
      <span className="ws-context-item"><Building2 size={13} aria-hidden /> Tenant <code>{tenant}</code></span>
      <span className="ws-context-item"><UserRound size={13} aria-hidden /> Role <code>{role}</code>{isAdmin ? " · admin" : " · operator"}</span>
    </p>
  );
}

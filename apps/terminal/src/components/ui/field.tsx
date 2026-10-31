import * as React from "react";
import { cn } from "../../lib/cn";

export function Field({ label, error, hint, children, htmlFor }: {
  label: string; error?: string; hint?: string; children: React.ReactNode; htmlFor?: string;
}) {
  const id = htmlFor ?? React.useId();
  return (
    <div className="mb-3">
      <label htmlFor={id} className="mb-1 block text-sm font-semibold">{label}</label>
      {React.isValidElement(children)
        ? React.cloneElement(children as React.ReactElement<{ id?: string; "aria-invalid"?: boolean; "aria-describedby"?: string }>,
          { id, "aria-invalid": !!error, "aria-describedby": error ? `${id}-err` : undefined })
        : children}
      {hint && !error && <p className="muted mt-1 text-xs">{hint}</p>}
      {error && <p id={`${id}-err`} role="alert" className="mt-1 text-xs font-semibold text-[rgb(var(--danger))]">{error}</p>}
    </div>
  );
}

export const inputCls = "w-full rounded-[10px] border border-line bg-surface px-3 py-2 text-ink";

export function Input({ className, ...props }: React.InputHTMLAttributes<HTMLInputElement>) {
  return <input className={cn(inputCls, className)} {...props} />;
}
export function Select({ className, ...props }: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return <select className={cn(inputCls, className)} {...props} />;
}
export function Textarea({ className, ...props }: React.TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea className={cn(inputCls, className)} {...props} />;
}

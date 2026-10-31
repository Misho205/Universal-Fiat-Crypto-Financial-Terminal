import * as React from "react";
import { cn } from "../../lib/cn";

export function TableWrap({ children, label }: { children: React.ReactNode; label: string }) {
  return (
    <div className="overflow-x-auto rounded-xl border border-line" role="region" aria-label={label} tabIndex={0}>
      <table className="w-full border-collapse text-left text-sm">{children}</table>
    </div>
  );
}
export function Th({ className, ...props }: React.ThHTMLAttributes<HTMLTableCellElement>) {
  return <th className={cn("border-b border-line bg-[rgb(var(--bg))] px-3 py-2 font-semibold", className)} scope="col" {...props} />;
}
export function Td({ className, ...props }: React.TdHTMLAttributes<HTMLTableCellElement>) {
  return <td className={cn("border-b border-line px-3 py-2 align-top", className)} {...props} />;
}

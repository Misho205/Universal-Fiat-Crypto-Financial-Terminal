import * as React from "react";
import { cn } from "../../lib/cn";

export function Card({ className, ...props }: React.HTMLAttributes<HTMLElement>) {
  return <section className={cn("rounded-2xl border border-line bg-surface p-5 shadow-card", className)} {...props} />;
}
export function CardTitle({ className, ...props }: React.HTMLAttributes<HTMLHeadingElement>) {
  return <h2 className={cn("mb-3 text-lg font-bold", className)} {...props} />;
}

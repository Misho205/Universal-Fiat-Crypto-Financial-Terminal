import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "../../lib/cn";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 rounded-[10px] px-4 py-2 text-sm font-semibold transition-colors focus-visible:outline-[3px] focus-visible:outline-offset-2 disabled:cursor-not-allowed disabled:opacity-60",
  {
    variants: {
      variant: {
        primary: "bg-brand-600 text-white hover:bg-brand-700 dark:bg-brand-600 dark:hover:bg-brand-700",
        secondary: "border border-line bg-surface text-ink hover:bg-brand-50 dark:hover:bg-brand-50",
        ghost: "text-brand-600 hover:bg-brand-50 dark:hover:bg-brand-50",
        danger: "bg-danger text-white hover:opacity-90",
      },
      size: { sm: "px-3 py-1.5 text-xs", md: "px-4 py-2 text-sm", lg: "px-5 py-2.5 text-base" },
    },
    defaultVariants: { variant: "primary", size: "md" },
  }
);

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement>, VariantProps<typeof buttonVariants> {}

export function Button({ className, variant, size, ...props }: ButtonProps) {
  return <button className={cn(buttonVariants({ variant, size }), className)} {...props} />;
}
export { buttonVariants };

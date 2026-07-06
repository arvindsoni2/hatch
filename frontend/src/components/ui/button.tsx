import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";
import { LoaderCircle } from "lucide-react";

const buttonVariants = cva(
  "hatch-interactive inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-[var(--radius-control)] text-sm font-semibold transition-[background-color,border-color,color,box-shadow,opacity,transform] disabled:pointer-events-none disabled:opacity-50",
  {
    variants: {
      variant: {
        default:     "bg-[var(--accent)] text-[var(--on-accent)] hover:bg-[var(--accent-hover)] shadow-sm",
        destructive: "bg-[var(--danger)] text-[var(--on-danger)] hover:opacity-90",
        success:     "bg-[var(--success)] text-[var(--on-success)] hover:opacity-90",
        outline:     "border border-[var(--border)] bg-[var(--surface)] hover:bg-[var(--surface-2)] text-[var(--text)]",
        secondary:   "bg-[var(--surface-2)] text-[var(--text)] hover:bg-[var(--surface-3)]",
        ghost:       "hover:bg-[var(--surface-2)] text-[var(--text)]",
        link:        "text-[var(--accent)] underline-offset-4 hover:underline",
      },
      size: {
        default: "min-h-11 px-4 py-2 sm:min-h-10",
        sm:      "min-h-11 px-3 sm:min-h-9",
        lg:      "min-h-12 px-6",
        icon:    "h-11 w-11 p-0 sm:h-10 sm:w-10",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  },
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  loading?: boolean;
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ children, className, disabled, loading = false, variant, size, ...props }, ref) => (
    <button
      aria-busy={loading || undefined}
      className={cn(buttonVariants({ variant, size, className }))}
      disabled={disabled || loading}
      ref={ref}
      {...props}
    >
      {loading ? <LoaderCircle aria-hidden="true" className="h-4 w-4 animate-spin" /> : null}
      {children}
    </button>
  ),
);
Button.displayName = "Button";

export { Button, buttonVariants };

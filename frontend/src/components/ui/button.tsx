import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center whitespace-nowrap rounded-md text-sm font-medium ring-offset-background transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50",
  {
    variants: {
      variant: {
        default:     "bg-[var(--accent)] text-[var(--on-accent)] hover:bg-[var(--accent-hover)] shadow-sm",
        destructive: "bg-[var(--danger)] text-white hover:opacity-90",
        outline:     "border border-[var(--border)] bg-[var(--surface)] hover:bg-[var(--surface-2)] text-[var(--text)]",
        secondary:   "bg-[var(--surface-2)] text-[var(--text)] hover:bg-[var(--surface-3)]",
        ghost:       "hover:bg-[var(--surface-2)] text-[var(--text)]",
        link:        "text-[var(--accent)] underline-offset-4 hover:underline",
      },
      size: {
        default: "h-10 px-4 py-2",
        sm:      "h-9 rounded-md px-3",
        lg:      "h-11 rounded-md px-8",
        icon:    "h-10 w-10",
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
  asChild?: boolean;
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, ...props }, ref) => (
    <button className={cn(buttonVariants({ variant, size, className }))} ref={ref} {...props} />
  ),
);
Button.displayName = "Button";

export { Button, buttonVariants };

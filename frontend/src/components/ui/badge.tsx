import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold transition-colors focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2",
  {
    variants: {
      variant: {
        default: "bg-brand-100 text-brand-800 border border-brand-200",
        outside: "bg-emerald-100 text-emerald-800 border border-emerald-200",
        inside: "bg-red-100 text-red-800 border border-red-200",
        unknown: "bg-gray-100 text-gray-700 border border-gray-200",
        source: "bg-slate-100 text-slate-700 border border-slate-200",
        skill: "bg-indigo-50 text-indigo-700 border border-indigo-100",
        secondary: "bg-slate-100 text-slate-700 border border-slate-200",
        destructive: "bg-red-500 text-white",
        outline: "text-slate-700 border border-slate-300",
        "priority-urgent": "bg-red-100 text-red-800 border border-red-200",
        "priority-high": "bg-amber-100 text-amber-800 border border-amber-200",
        "priority-normal": "bg-slate-100 text-slate-700 border border-slate-200",
        "priority-low": "bg-green-50 text-green-700 border border-green-100",
        "status-interview": "bg-amber-100 text-amber-800 border border-amber-200",
        "status-offered": "bg-emerald-100 text-emerald-800 border border-emerald-200",
        "status-applied": "bg-blue-100 text-blue-800 border border-blue-200",
        "status-discovered": "bg-slate-100 text-slate-600 border border-slate-200",
        "status-shortlisted": "bg-purple-100 text-purple-800 border border-purple-200",
        "status-accepted": "bg-green-100 text-green-800 border border-green-200",
        "status-rejected": "bg-red-100 text-red-700 border border-red-200",
        "status-withdrawn": "bg-gray-100 text-gray-600 border border-gray-200",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  },
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return (
    <div className={cn(badgeVariants({ variant }), className)} {...props} />
  );
}

export { Badge, badgeVariants };

"use client";

import * as React from "react";
import * as DialogPrimitive from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import { cn } from "@/lib/utils";
import { DialogDescription, DialogTitle } from "@/components/ui/dialog";

export const Sheet = DialogPrimitive.Root;
export const SheetTrigger = DialogPrimitive.Trigger;
export const SheetClose = DialogPrimitive.Close;
export { DialogTitle as SheetTitle, DialogDescription as SheetDescription };

interface SheetContentProps
  extends React.ComponentPropsWithoutRef<typeof DialogPrimitive.Content> {
  closeLabel?: string;
  preventClose?: boolean;
}

export const SheetContent = React.forwardRef<
  React.ElementRef<typeof DialogPrimitive.Content>,
  SheetContentProps
>(
  (
    {
      children,
      className,
      closeLabel = "Close panel",
      preventClose = false,
      onEscapeKeyDown,
      onInteractOutside,
      ...props
    },
    ref,
  ) => (
    <DialogPrimitive.Portal>
      <DialogPrimitive.Overlay className="fixed inset-0 z-[100] bg-black/60 backdrop-blur-sm" />
      <DialogPrimitive.Content
        className={cn(
          "fixed inset-y-0 right-0 z-[101] flex h-[100dvh] w-full max-w-2xl flex-col overflow-hidden overscroll-contain border-l border-[var(--border)] bg-[var(--surface)] pb-[env(safe-area-inset-bottom)] text-[var(--text)] shadow-[var(--shadow-lg)]",
          className,
        )}
        onEscapeKeyDown={(event) => {
          if (preventClose) event.preventDefault();
          onEscapeKeyDown?.(event);
        }}
        onInteractOutside={(event) => {
          if (preventClose) event.preventDefault();
          onInteractOutside?.(event);
        }}
        ref={ref}
        {...props}
      >
        {children}
        <DialogPrimitive.Close
          aria-label={closeLabel}
          className="hatch-interactive absolute right-3 top-3 z-10 inline-flex h-11 w-11 items-center justify-center rounded-[var(--radius-control)] text-[var(--text-muted)] hover:bg-[var(--surface-2)] hover:text-[var(--text)]"
          disabled={preventClose}
          type="button"
        >
          <X aria-hidden="true" className="h-5 w-5" />
        </DialogPrimitive.Close>
      </DialogPrimitive.Content>
    </DialogPrimitive.Portal>
  ),
);
SheetContent.displayName = "SheetContent";

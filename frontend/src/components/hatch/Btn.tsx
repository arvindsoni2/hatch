"use client";

import { Button, type ButtonProps } from "@/components/ui/button";
import { Icon } from "@/components/ui/icon";
import { cn } from "@/lib/utils";

type BtnKind = "primary" | "soft" | "ghost" | "success";
type BtnSize = "sm" | "md";

interface BtnProps
  extends Omit<ButtonProps, "children" | "size" | "variant"> {
  children: React.ReactNode;
  kind?: BtnKind;
  size?: BtnSize;
  icon?: string;
  iconR?: string;
  full?: boolean;
}

const VARIANTS: Record<BtnKind, ButtonProps["variant"]> = {
  primary: "default",
  soft: "secondary",
  ghost: "outline",
  success: "success",
};

export function Btn({
  children,
  kind = "primary",
  size = "md",
  icon,
  iconR,
  full = false,
  className,
  ...props
}: BtnProps) {
  const iconSize = size === "sm" ? 15 : 16;

  return (
    <Button
      className={cn(full && "w-full", className)}
      size={size === "sm" ? "sm" : "default"}
      variant={VARIANTS[kind]}
      {...props}
    >
      {icon ? <Icon name={icon} size={iconSize} strokeWidth={2.2} /> : null}
      {children}
      {iconR ? <Icon name={iconR} size={iconSize} strokeWidth={2.2} /> : null}
    </Button>
  );
}

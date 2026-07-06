import { Icon, type IconProps } from "@/components/ui/icon";

/**
 * Compatibility adapter for existing Hatch screens.
 * New components should import Icon from components/ui/icon directly.
 */
export function HatchIcon(props: IconProps) {
  return <Icon {...props} />;
}

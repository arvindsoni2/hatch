import type { CSSProperties } from "react";
import {
  ArrowRight, Bell, BriefcaseBusiness, Building2, CalendarDays, Check,
  ChevronLeft, ChevronRight, CircleCheck, CircleHelp, Clock3, Compass,
  ExternalLink, FileText, House, Layers3, LockKeyhole, MapPin, Mic, Moon,
  Plus, Search, Send, Settings, SlidersHorizontal, Sun, Target, Trash2,
  TrendingUp, UserRound, X, Zap, type LucideIcon,
} from "lucide-react";

const ICONS: Record<string, LucideIcon> = {
  arrowR: ArrowRight,
  bell: Bell,
  briefcase: BriefcaseBusiness,
  building: Building2,
  calendar: CalendarDays,
  check: Check,
  checkCircle: CircleCheck,
  chevronL: ChevronLeft,
  chevronR: ChevronRight,
  clock: Clock3,
  compass: Compass,
  externalLink: ExternalLink,
  fileText: FileText,
  home: House,
  layers: Layers3,
  lock: LockKeyhole,
  mapPin: MapPin,
  mic: Mic,
  moon: Moon,
  plus: Plus,
  search: Search,
  send: Send,
  settings: Settings,
  sliders: SlidersHorizontal,
  sun: Sun,
  target: Target,
  trash: Trash2,
  trending: TrendingUp,
  user: UserRound,
  x: X,
  zap: Zap,
};

export interface IconProps {
  name: string;
  size?: number;
  color?: string;
  strokeWidth?: number;
  style?: CSSProperties;
  label?: string;
}

export function Icon({
  name,
  size = 18,
  color = "currentColor",
  strokeWidth = 2,
  style,
  label,
}: IconProps) {
  const Glyph = ICONS[name] ?? CircleHelp;

  return (
    <Glyph
      aria-hidden={label ? undefined : true}
      aria-label={label}
      color={color}
      focusable="false"
      size={size}
      strokeWidth={strokeWidth}
      style={{ flexShrink: 0, ...style }}
    />
  );
}

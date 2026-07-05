"use client";
import { usePathname } from 'next/navigation';
import { HatchNav, type HatchTab } from './HatchNav';
import { HatchSidebar } from './HatchSidebar';

export function deriveTab(pathname: string): HatchTab | null {
  if (pathname.startsWith('/today'))   return 'today';
  if (pathname.startsWith('/stream'))  return 'stream';
  if (pathname.startsWith('/tracker')) return 'tracker';
  if (pathname.startsWith('/tailor'))  return 'tailor';
  if (pathname.startsWith('/prep'))    return 'prep';
  return null;
}

interface HatchNavShellProps {
  readyCount?: number;
}

export function HatchNavShell({ readyCount = 0 }: HatchNavShellProps) {
  const pathname = usePathname();
  const activeTab = deriveTab(pathname);
  return (
    <>
      <HatchSidebar activeTab={activeTab} readyCount={readyCount} />
      <HatchNav activeTab={activeTab} />
    </>
  );
}

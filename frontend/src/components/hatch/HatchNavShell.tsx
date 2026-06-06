"use client";
import { usePathname } from 'next/navigation';
import { HatchNav, type HatchTab } from './HatchNav';
import { HatchSidebar } from './HatchSidebar';

function deriveTab(pathname: string): HatchTab {
  if (pathname.startsWith('/stream'))  return 'stream';
  if (pathname.startsWith('/tracker')) return 'tracker';
  if (pathname.startsWith('/prep'))    return 'prep';
  return 'today';
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

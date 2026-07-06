"use client";
import { useEffect, useState } from 'react';
import { usePathname } from 'next/navigation';
import { HatchTopBar } from './HatchTopBar';
import { fetchProfileStatus } from '@/lib/api';
import { PRODUCT_ROUTES } from '@/lib/product-routes';

const ROUTE_LABELS: Record<string, { title: string; sub?: string }> = {
  '/today':        { title: 'Today' },
  [PRODUCT_ROUTES.pipeline.href]:      { title: PRODUCT_ROUTES.pipeline.label },
  [PRODUCT_ROUTES.applications.href]:  { title: PRODUCT_ROUTES.applications.label },
  [PRODUCT_ROUTES.interviewPrep.href]: { title: PRODUCT_ROUTES.interviewPrep.label },
  '/tailor':       { title: 'CV Studio', sub: 'Create a tailored CV and application pack' },
  '/settings/resume':  { title: 'Master CV' },
  '/settings/profile': { title: 'Profile' },
  '/settings/ai':      { title: 'AI Provider' },
  '/settings/system':  { title: 'System Logs' },
  '/settings/security': { title: 'Security' },
  '/settings':         { title: 'Profile' },
  [PRODUCT_ROUTES.interviewCoach.href]: { title: PRODUCT_ROUTES.interviewCoach.label },
  [PRODUCT_ROUTES.jobs.href]:           { title: PRODUCT_ROUTES.jobs.label },
  '/analytics':    { title: 'Analytics' },
  '/calendar':     { title: 'Calendar' },
};

function deriveLabels(pathname: string): { title: string; sub?: string } {
  for (const [prefix, label] of Object.entries(ROUTE_LABELS)) {
    if (pathname.startsWith(prefix)) return label;
  }
  return { title: 'Hatch' };
}

export function HatchTopBarSlot() {
  const pathname = usePathname();
  const [name, setName] = useState('there');
  const [role, setRole] = useState<string | undefined>(undefined);
  const { title, sub } = deriveLabels(pathname);

  useEffect(() => {
    fetchProfileStatus()
      .then((s) => {
        if (s.candidate_name) setName(s.candidate_name);
        if (s.target_roles?.length) setRole(s.target_roles[0]);
      })
      .catch(() => {/* backend offline — keep fallback */});
  }, []);

  return <HatchTopBar name={name} role={role} pageTitle={title} pageSub={sub} />;
}

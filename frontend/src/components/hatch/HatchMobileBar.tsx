"use client";
import { useEffect, useState } from 'react';
import { NotificationBell } from '@/components/NotificationBell';
import { ThemeToggle } from '@/components/ThemeToggle';
import { UserMenu } from './UserMenu';
import { fetchProfileStatus } from '@/lib/api';

export function HatchMobileBar() {
  const [name, setName] = useState('Account');
  const [role, setRole] = useState<string | undefined>(undefined);

  useEffect(() => {
    fetchProfileStatus()
      .then((status) => {
        if (status.candidate_name) setName(status.candidate_name);
        if (status.target_roles?.length) setRole(status.target_roles[0]);
      })
      .catch(() => {});
  }, []);

  return (
    <div
      className="md:hidden flex items-center justify-between sticky top-0 z-30 px-4"
      style={{
        height: 52,
        background: 'var(--bg)',
        borderBottom: '1px solid var(--border)',
        flexShrink: 0,
      }}
    >
      <span style={{ fontSize: 18, fontWeight: 800, letterSpacing: '-0.03em', color: 'var(--accent)' }}>H</span>
      <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
        <ThemeToggle />
        <NotificationBell />
        <UserMenu name={name} role={role} />
      </div>
    </div>
  );
}

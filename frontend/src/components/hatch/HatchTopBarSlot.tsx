"use client";
import { useEffect, useState } from 'react';
import { HatchTopBar } from './HatchTopBar';
import { fetchProfileStatus } from '@/lib/api';

export function HatchTopBarSlot() {
  const [name, setName] = useState('there');
  const [role, setRole] = useState<string | undefined>(undefined);

  useEffect(() => {
    fetchProfileStatus()
      .then((s) => {
        if (s.candidate_name) setName(s.candidate_name);
        if (s.target_roles?.length) setRole(s.target_roles[0]);
      })
      .catch(() => {/* backend offline — keep fallback */});
  }, []);

  return <HatchTopBar name={name} role={role} />;
}

"use client";
import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Icon } from '@/components/ui/icon';
import { NotificationBell } from '@/components/NotificationBell';
import { UserMenu } from './UserMenu';

interface HatchTopBarProps {
  name: string;
  role?: string;
  onSearch?: (query: string) => void;
}

function getGreeting(): string {
  const h = new Date().getHours();
  if (h < 12) return 'Good morning';
  if (h < 17) return 'Good afternoon';
  return 'Good evening';
}

export function HatchTopBar({ name, role, onSearch }: HatchTopBarProps) {
  const [greeting, setGreeting] = useState('Welcome');
  const [searchQuery, setSearchQuery] = useState('');
  const router = useRouter();

  useEffect(() => {
    setGreeting(getGreeting());
  }, []);

  function submitSearch(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const query = searchQuery.trim();
    if (!query) return;
    if (onSearch) {
      onSearch(query);
      return;
    }
    router.push(`/jobs?view=all&search=${encodeURIComponent(query)}`);
  }

  return (
    <header
      className="hidden md:flex items-center gap-4 sticky top-0 z-30"
      style={{
        background: 'var(--bg)',
        borderBottom: '1px solid var(--border)',
        padding: '0 32px',
        height: 60,
        flexShrink: 0,
      }}
    >
      {/* Utility context. Route content owns the page title and H1. */}
      <div className="flex-1 min-w-0">
        <span style={{ fontSize: 13, color: 'var(--text-muted)' }}>
          {greeting}, {name}
        </span>
      </div>

      {/* Search */}
      <form className="relative" style={{ width: 240 }} role="search" onSubmit={submitSearch}>
        <Icon
          name="search"
          size={15}
          color="var(--text-muted)"
          style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)' }}
        />
        <input
          type="search"
          placeholder="Search roles…"
          aria-label="Search roles"
          value={searchQuery}
          onChange={(event) => setSearchQuery(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Escape') setSearchQuery('');
          }}
          style={{
            width: '100%',
            padding: '7px 10px 7px 32px',
            borderRadius: 9,
            background: 'var(--surface-2)',
            border: '1px solid var(--border)',
            color: 'var(--text)',
            fontSize: 13,
            outline: 'none',
          }}
        />
      </form>

      <NotificationBell />
      <UserMenu name={name} role={role} />
    </header>
  );
}

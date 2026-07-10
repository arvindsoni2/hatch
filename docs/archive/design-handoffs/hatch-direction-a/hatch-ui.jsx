// hatch-ui.jsx — Shared Hatch design tokens + primitives (dark system)
// Exact tokens lifted from frontend/src/app/globals.css (dark theme).
// Exports to window so other babel scripts can use the bare identifiers.

const HT = {
  bg: '#0b0b0f', bgEl: '#101014',
  surface: '#16161c', s2: '#1d1d25', s3: '#24242e',
  border: '#26262f', borderStrong: '#32323d', borderSubtle: '#1d1d25',
  text: '#f1f1f4', dim: '#a8a8b3', muted: '#74747f',
  accent: '#5b9bff', accentHover: '#7ab0ff',
  accentSoft: 'rgba(91,155,255,0.14)', accentSoftStrong: 'rgba(91,155,255,0.22)',
  success: '#3ddc97', successSoft: 'rgba(61,220,151,0.14)',
  danger: '#ff6b6b', dangerSoft: 'rgba(255,107,107,0.14)',
  warning: '#f5b950', warningSoft: 'rgba(245,185,80,0.14)',
  purple: '#b794ff', purpleSoft: 'rgba(183,148,255,0.14)',
  font: "'Inter',-apple-system,system-ui,sans-serif",
  mono: "'Roboto Mono',ui-monospace,monospace",
};

// The four agents — each owns a colour. Together they form the pipeline
// spectrum (blue → purple → green → amber) that every screen reuses so the
// Scout→Score→Tailor→Coach journey is legible at a glance.
const AGENTS = {
  scout:  { key: 'scout',  name: 'Scout',  color: HT.accent,  soft: HT.accentSoft,  role: 'Finds roles',      icon: 'compass' },
  scorer: { key: 'scorer', name: 'Scorer', color: HT.purple,  soft: HT.purpleSoft,  role: 'Ranks matches',    icon: 'target' },
  tailor: { key: 'tailor', name: 'Tailor', color: HT.success, soft: HT.successSoft, role: 'Writes your CV',   icon: 'fileText' },
  coach:  { key: 'coach',  name: 'Coach',  color: HT.warning, soft: HT.warningSoft, role: 'Preps interviews', icon: 'mic' },
};
const PIPE = ['scout', 'scorer', 'tailor', 'coach'];

// ── Icons — minimal stroke set ────────────────────────────────────────────────
const ICONS = {
  bell: <><path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/></>,
  search: <><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></>,
  check: <path d="M20 6 9 17l-5-5"/>,
  checkCircle: <><circle cx="12" cy="12" r="10"/><path d="m9 12 2 2 4-4"/></>,
  chevronR: <path d="m9 18 6-6-6-6"/>,
  arrowR: <><path d="M5 12h14"/><path d="m12 5 7 7-7 7"/></>,
  clock: <><circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/></>,
  fileText: <><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/><path d="M9 13h6M9 17h4"/></>,
  send: <><path d="M22 2 11 13"/><path d="M22 2 15 22l-4-9-9-4z"/></>,
  target: <><circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1.5" fill="currentColor"/></>,
  mic: <><rect x="9" y="2" width="6" height="12" rx="3"/><path d="M5 10a7 7 0 0 0 14 0"/><path d="M12 17v4"/></>,
  compass: <><circle cx="12" cy="12" r="10"/><polygon points="16.24 7.76 14.12 14.12 7.76 16.24 9.88 9.88"/></>,
  layers: <><polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/><polyline points="2 12 12 17 22 12"/></>,
  home: <><path d="m3 9 9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></>,
  inbox: <><polyline points="22 12 16 12 14 15 10 15 8 12 2 12"/><path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z"/></>,
  user: <><circle cx="12" cy="7" r="4"/><path d="M5.5 21a6.5 6.5 0 0 1 13 0"/></>,
  mapPin: <><path d="M20 10c0 6-8 12-8 12s-8-6-8-12a8 8 0 0 1 16 0z"/><circle cx="12" cy="10" r="3"/></>,
  briefcase: <><rect x="2" y="7" width="20" height="14" rx="2"/><path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16"/></>,
  calendar: <><rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/></>,
  zap: <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>,
  x: <path d="M18 6 6 18M6 6l12 12"/>,
  plus: <path d="M12 5v14M5 12h14"/>,
  more: <><circle cx="12" cy="12" r="1.3" fill="currentColor"/><circle cx="19" cy="12" r="1.3" fill="currentColor"/><circle cx="5" cy="12" r="1.3" fill="currentColor"/></>,
  filter: <path d="M22 3H2l8 9.46V19l4 2v-8.54z"/>,
  sliders: <><line x1="4" y1="21" x2="4" y2="14"/><line x1="4" y1="10" x2="4" y2="3"/><line x1="12" y1="21" x2="12" y2="12"/><line x1="12" y1="8" x2="12" y2="3"/><line x1="20" y1="21" x2="20" y2="16"/><line x1="20" y1="12" x2="20" y2="3"/><circle cx="4" cy="12" r="2" fill="currentColor"/><circle cx="12" cy="10" r="2" fill="currentColor"/><circle cx="20" cy="14" r="2" fill="currentColor"/></>,
  externalLink: <><path d="M15 3h6v6"/><path d="M10 14 21 3"/><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/></>,
  building: <><rect x="4" y="3" width="16" height="18" rx="1.5"/><path d="M9 21v-4h6v4"/><path d="M8 7h.5M12 7h.5M16 7h.5M8 11h.5M12 11h.5M16 11h.5"/></>,
  pound: <path d="M18 7c0-2.2-1.8-4-4-4S10 4.8 10 7v4H7m0 0h8m-8 0v3c0 1.7-1 3-2 4h12"/>,
  message: <path d="M21 11.5a8.38 8.38 0 0 1-8.5 8.5 8.5 8.5 0 0 1-3.9-.9L3 21l1.9-5.6A8.5 8.5 0 0 1 12.5 3 8.38 8.38 0 0 1 21 11.5z"/>,
  trending: <><polyline points="22 7 13.5 15.5 8.5 10.5 2 17"/><polyline points="16 7 22 7 22 13"/></>,
  pause: <><rect x="6" y="4" width="4" height="16" rx="1"/><rect x="14" y="4" width="4" height="16" rx="1"/></>,
};

function Icon({ name, size = 18, color = 'currentColor', sw = 2, fill = 'none', style }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill={fill} stroke={color}
      strokeWidth={sw} strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0, ...style }}>
      {ICONS[name]}
    </svg>
  );
}

// ── Small primitives ──────────────────────────────────────────────────────────

function Dot({ color, size = 8, pulse = false }) {
  return (
    <span style={{ position: 'relative', width: size, height: size, flexShrink: 0, display: 'inline-block' }}>
      {pulse && <span style={{ position: 'absolute', inset: -3, borderRadius: 999, background: color, opacity: 0.25 }} />}
      <span style={{ position: 'absolute', inset: 0, borderRadius: 999, background: color }} />
    </span>
  );
}

function Chip({ children, color = HT.dim, bg = HT.s2, icon, style }) {
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 4,
      padding: '3px 8px', borderRadius: 999, fontSize: 11.5, fontWeight: 600,
      letterSpacing: '0.01em', color, background: bg, whiteSpace: 'nowrap', ...style,
    }}>
      {icon && <Icon name={icon} size={11} color={color} sw={2.4} />}
      {children}
    </span>
  );
}

// Score pill, colour-graded vs threshold (like ScoreBadge.tsx)
function ScorePill({ score, threshold = 0.75, size = 'md' }) {
  const pct = Math.round(score * 100);
  const c = score >= threshold ? HT.success : score >= threshold * 0.66 ? HT.warning : HT.muted;
  const soft = score >= threshold ? HT.successSoft : score >= threshold * 0.66 ? HT.warningSoft : HT.s2;
  const big = size === 'lg';
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
      minWidth: big ? 54 : 42, padding: big ? '6px 10px' : '3px 7px', borderRadius: 8,
      fontFamily: HT.mono, fontWeight: 700, fontSize: big ? 17 : 12.5,
      color: c, background: soft,
    }}>{pct}%</span>
  );
}

// Agent avatar — rounded square in agent colour with its icon
function AgentBadge({ agent, size = 30, ring = false }) {
  const a = AGENTS[agent];
  return (
    <span style={{
      width: size, height: size, borderRadius: size * 0.3, flexShrink: 0,
      display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
      background: a.soft, color: a.color,
      boxShadow: ring ? `0 0 0 3px ${a.soft}` : 'none',
    }}>
      <Icon name={a.icon} size={size * 0.52} color={a.color} sw={2.1} />
    </span>
  );
}

// The signature element: a horizontal Scout→Score→Tailor→Coach track that
// shows where a single role currently sits. `stage` = index reached (0-3),
// `pct` optional score to print on the Scorer node.
function StageTrack({ stage = 0, pct, compact = false, labels = true }) {
  const r = compact ? 9 : 11;
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6, width: '100%' }}>
      <div style={{ display: 'flex', alignItems: 'center' }}>
        {PIPE.map((k, i) => {
          const a = AGENTS[k];
          const done = i < stage;
          const here = i === stage;
          const reached = i <= stage;
          return (
            <React.Fragment key={k}>
              <div style={{
                width: r * 2, height: r * 2, borderRadius: 999, flexShrink: 0,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                background: reached ? a.soft : HT.s2,
                boxShadow: here ? `0 0 0 3px ${a.soft}` : 'none',
                border: reached ? `1.5px solid ${a.color}` : `1.5px solid ${HT.border}`,
              }}>
                <Icon name={done ? 'check' : a.icon} size={compact ? 10 : 12}
                  color={reached ? a.color : HT.muted} sw={2.4} />
              </div>
              {i < PIPE.length - 1 && (
                <div style={{ flex: 1, height: 2, background: i < stage ? AGENTS[PIPE[i + 1]].color : HT.border, opacity: i < stage ? 0.5 : 1 }} />
              )}
            </React.Fragment>
          );
        })}
      </div>
      {labels && (
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 9.5, fontWeight: 600, letterSpacing: '0.02em' }}>
          {PIPE.map((k, i) => (
            <span key={k} style={{ color: i <= stage ? AGENTS[k].color : HT.muted, width: r * 2, textAlign: 'center' }}>
              {k === 'scorer' && pct != null && i === stage ? `${pct}%` : AGENTS[k].name}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

function Btn({ children, kind = 'primary', icon, iconR, full = false, size = 'md', style, onClick }) {
  const pad = size === 'sm' ? '8px 12px' : '11px 16px';
  const fs = size === 'sm' ? 13 : 14;
  const styles = {
    primary: { background: HT.accent, color: '#fff', border: 'none' },
    soft: { background: HT.s2, color: HT.text, border: `1px solid ${HT.border}` },
    ghost: { background: 'transparent', color: HT.dim, border: `1px solid ${HT.border}` },
    success: { background: HT.success, color: '#06231a', border: 'none' },
  }[kind];
  return (
    <button onClick={onClick} style={{
      display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: 7,
      padding: pad, borderRadius: 10, fontSize: fs, fontWeight: 600, fontFamily: HT.font,
      cursor: 'pointer', whiteSpace: 'nowrap', width: full ? '100%' : 'auto', ...styles, ...style,
    }}>
      {icon && <Icon name={icon} size={fs + 2} color={styles.color} sw={2.2} />}
      {children}
      {iconR && <Icon name={iconR} size={fs + 2} color={styles.color} sw={2.2} />}
    </button>
  );
}

function Card({ children, style, accent }) {
  return (
    <div style={{
      background: HT.surface, border: `1px solid ${accent ? HT.accent : HT.border}`,
      borderRadius: 16, ...(accent ? { boxShadow: `0 0 0 3px ${HT.accentSoft}` } : {}), ...style,
    }}>{children}</div>
  );
}

// Avatar for the user
function UserAvatar({ size = 32, initials = 'AS' }) {
  return (
    <span style={{
      width: size, height: size, borderRadius: 999, flexShrink: 0,
      display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
      background: 'linear-gradient(135deg,#f97316,#ec4899)', color: '#fff',
      fontWeight: 700, fontSize: size * 0.36,
    }}>{initials}</span>
  );
}

// Phone screen shell: dark canvas with top inset (status bar) + optional tab bar
function Screen({ children, pad = 18, tabBar, scroll = false }) {
  return (
    <div style={{
      position: 'absolute', inset: 0, background: HT.bg, color: HT.text,
      fontFamily: HT.font, display: 'flex', flexDirection: 'column',
      letterSpacing: '-0.005em',
    }}>
      <div style={{ height: 56, flexShrink: 0 }} />
      <div style={{ flex: 1, overflow: scroll ? 'auto' : 'hidden', padding: `0 ${pad}px`, display: 'flex', flexDirection: 'column' }}>
        {children}
      </div>
      {tabBar}
      <div style={{ height: 30, flexShrink: 0 }} />
    </div>
  );
}

// Bottom tab bar — the new 4-tab IA that collapses Home/Inbox/Shortlist
function TabBar({ active = 'today', variant = 'a' }) {
  const tabs = [
    { key: 'today', label: 'Today', icon: 'home' },
    { key: 'stream', label: variant === 'b' ? 'Pipeline' : 'Stream', icon: 'layers' },
    { key: 'track', label: 'Tracker', icon: 'briefcase' },
    { key: 'prep', label: 'Prep', icon: 'mic' },
  ];
  return (
    <div style={{
      flexShrink: 0, display: 'flex', borderTop: `1px solid ${HT.border}`,
      background: HT.bgEl, padding: '8px 8px 4px',
    }}>
      {tabs.map((t) => {
        const on = t.key === active;
        return (
          <div key={t.key} style={{
            flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 3,
            color: on ? HT.accent : HT.muted,
          }}>
            <Icon name={t.icon} size={21} color={on ? HT.accent : HT.muted} sw={on ? 2.3 : 2} />
            <span style={{ fontSize: 10.5, fontWeight: on ? 700 : 500 }}>{t.label}</span>
          </div>
        );
      })}
    </div>
  );
}

Object.assign(window, {
  HT, AGENTS, PIPE, Icon, Dot, Chip, ScorePill, AgentBadge, StageTrack,
  Btn, Card, UserAvatar, Screen, TabBar,
});

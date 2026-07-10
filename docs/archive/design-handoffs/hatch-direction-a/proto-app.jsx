// proto-app.jsx — Direction A, interactive prototype (mobile).
// Reuses primitives from hatch-ui.jsx; adds app state, navigation, the approve
// loop, Tracker + Prep tabs, toasts. Mounted by Hatch Prototype.html inside an
// IOSDevice. Tweaks come in as props from the host Root.
const { useState, useRef, useEffect } = React;

// ── accent theming (mutates the shared HT token object) ───────────────────────
function hexA(hex, a) { const n = parseInt(hex.slice(1), 16); return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`; }
function applyAccent(hex) { HT.accent = hex; HT.accentHover = hex; HT.accentSoft = hexA(hex, 0.14); HT.accentSoftStrong = hexA(hex, 0.22); }

// ── seed data ─────────────────────────────────────────────────────────────────
const SEED = [
  { id: 'sa',  title: 'Solutions Architect',  company: 'Hays',         loc: 'London',    rate: '£600–675/day', score: 1.0,  ats: 95, state: 'ready' },
  { id: 'ta',  title: 'Technical Architect',  company: 'Yolk',         loc: 'Reading',   rate: '£700–800/day', score: 0.86, ats: 88, state: 'ready' },
  { id: 'swa', title: 'Software Architect',   company: 'BELCAN',       loc: 'Newcastle', rate: '£70/day',      score: 0.93, ats: 90, state: 'ready' },
  { id: 'soa', title: 'Solution Architect — On-Prem', company: 'Outsource UK', loc: 'Preston', rate: '£71–96/day', score: 0.90, state: 'tailoring' },
  { id: 'sv',  title: 'Service Architect',    company: 'Involved',     loc: 'London',    rate: '£600–675/day', score: 0.68, state: 'parked' },
];
const APPLIED_SEED = [
  { id: 'ca', title: 'Cloud Architect', company: 'Lloyds', loc: 'Remote', rate: '£650/day', score: 0.84 },
  { id: 'pa', title: 'Platform Architect', company: 'Sky', loc: 'Leeds', rate: '£600/day', score: 0.81 },
];
const INTERVIEW_SEED = [
  { id: 'la', title: 'Lead Architect', company: 'Capgemini', loc: 'London', rate: '£700/day', score: 0.91, when: 'Tue 9:00am' },
];

const stageOf = (it) => it.state === 'ready' ? 3 : it.state === 'tailoring' ? 2 : it.state === 'parked' ? 1 : 3;
const statusMeta = {
  ready:     { label: 'Ready for your approval', color: HT.success },
  tailoring: { label: 'Tailor is writing your CV…', color: HT.success },
  parked:    { label: 'Parked · just below your 75% bar', color: HT.warning },
  applied:   { label: 'Applied · awaiting reply', color: HT.accent },
  rejected:  { label: 'Dismissed', color: HT.muted },
};

// ── chrome ────────────────────────────────────────────────────────────────────
function Header({ title, sub, right }) {
  return (
    <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', padding: '8px 18px 14px' }}>
      <div>
        <div style={{ fontSize: 26, fontWeight: 700, letterSpacing: '-0.03em', color: HT.text }}>{title}</div>
        {sub && <div style={{ fontSize: 12.5, color: HT.muted, marginTop: 2 }}>{sub}</div>}
      </div>
      {right}
    </div>
  );
}

function NavBar({ active, onNav }) {
  const tabs = [['today', 'Today', 'home'], ['stream', 'Stream', 'layers'], ['track', 'Tracker', 'briefcase'], ['prep', 'Prep', 'mic']];
  return (
    <div style={{ flexShrink: 0, display: 'flex', borderTop: `1px solid ${HT.border}`, background: HT.bgEl, padding: '8px 8px 4px' }}>
      {tabs.map(([key, label, icon]) => {
        const on = key === active;
        return (
          <button key={key} onClick={() => onNav(key)} style={{
            flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 3,
            background: 'none', border: 'none', cursor: 'pointer', padding: '4px 0',
            color: on ? HT.accent : HT.muted,
          }}>
            <Icon name={icon} size={21} color={on ? HT.accent : HT.muted} sw={on ? 2.3 : 2} />
            <span style={{ fontSize: 10.5, fontWeight: on ? 700 : 500 }}>{label}</span>
          </button>
        );
      })}
    </div>
  );
}

function Toast({ msg }) {
  return (
    <div style={{ position: 'absolute', left: 16, right: 16, bottom: 96, zIndex: 80, display: 'flex', alignItems: 'center', gap: 10,
      padding: '12px 14px', borderRadius: 12, background: HT.s3, border: `1px solid ${HT.borderStrong}`, boxShadow: '0 12px 30px rgba(0,0,0,0.4)',
      animation: 'tRise .22s ease-out' }}>
      <span style={{ width: 22, height: 22, borderRadius: 999, background: HT.successSoft, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
        <Icon name="check" size={13} color={HT.success} />
      </span>
      <span style={{ fontSize: 12.5, color: HT.text, fontWeight: 500 }}>{msg}</span>
    </div>
  );
}

// ── TODAY ─────────────────────────────────────────────────────────────────────
function FunnelStep({ agent, count, last }) {
  return (
    <React.Fragment>
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 5, flex: 1 }}>
        <AgentBadge agent={agent} size={34} />
        <div style={{ fontFamily: HT.mono, fontSize: 18, fontWeight: 700, color: HT.text, lineHeight: 1 }}>{count}</div>
        <div style={{ fontSize: 10, fontWeight: 600, color: AGENTS[agent].color }}>{AGENTS[agent].name}</div>
      </div>
      {!last && <div style={{ display: 'flex', alignItems: 'center', paddingBottom: 28 }}><Icon name="chevronR" size={14} color={HT.borderStrong} sw={2.5} /></div>}
    </React.Fragment>
  );
}

function Today({ t, items, onReview, onNav, onPrep }) {
  const ready = items.filter((x) => x.state === 'ready');
  const cardPad = t.dense ? 12 : 15;
  return (
    <>
      <Header title="Today" sub="Thursday · 5 June" right={
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <div style={{ position: 'relative' }}>
            <Icon name="bell" size={20} color={HT.dim} />
            <span style={{ position: 'absolute', top: -2, right: -2, width: 7, height: 7, borderRadius: 999, background: HT.danger, border: `1.5px solid ${HT.bg}` }} />
          </div>
          <UserAvatar size={32} />
        </div>
      } />
      <div style={{ padding: '0 18px' }}>
        {/* briefing */}
        <Card style={{ padding: 16, marginBottom: t.dense ? 14 : 18 }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
              <Dot color={HT.success} size={8} pulse />
              <span style={{ fontSize: 12.5, fontWeight: 600, color: HT.text }}>Agents active</span>
            </div>
            <span style={{ fontSize: 11, color: HT.muted }}>last run 3h ago</span>
          </div>
          <p style={{ margin: 0, fontSize: 14.5, lineHeight: 1.55, color: HT.dim }}>
            {t.voice
              ? <>Overnight I moved <strong style={{ color: HT.text }}>75 new roles</strong> down the pipeline. <strong style={{ color: HT.success }}>{ready.length} are tailored</strong> and waiting on your call.</>
              : <><strong style={{ color: HT.text }}>75 new roles</strong> processed overnight · <strong style={{ color: HT.success }}>{ready.length} tailored</strong> and ready for review.</>}
          </p>
          <div style={{ display: 'flex', alignItems: 'flex-start', marginTop: 16, padding: '4px 2px 0' }}>
            <FunnelStep agent="scout" count={75} />
            <FunnelStep agent="scorer" count={12} />
            <FunnelStep agent="tailor" count={ready.length} />
            <FunnelStep agent="coach" count={1} last />
          </div>
        </Card>

        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
          <span style={{ fontSize: 13, fontWeight: 700, color: HT.text, whiteSpace: 'nowrap' }}>Needs you</span>
          <Chip color={HT.accent} bg={HT.accentSoft}>{ready.length + 2}</Chip>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 12, paddingBottom: 18 }}>
          {/* approve */}
          {ready.length > 0 ? (
            <Card accent style={{ padding: cardPad }}>
              <div style={{ display: 'flex', gap: 11, marginBottom: 12 }}>
                <AgentBadge agent="tailor" size={34} ring />
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 15, fontWeight: 700, color: HT.text }}>{ready.length} application{ready.length !== 1 ? 's' : ''} ready to send</div>
                  <div style={{ fontSize: 12, color: HT.muted, marginTop: 1 }}>{t.voice ? 'I drafted a CV + cover letter for each' : 'CV + cover letter drafted for each'}</div>
                </div>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginBottom: 13 }}>
                {ready.map((it) => (
                  <button key={it.id} onClick={() => onReview([it.id])} style={{ display: 'flex', alignItems: 'center', gap: 9, padding: '7px 9px', borderRadius: 9, background: HT.s2, border: 'none', cursor: 'pointer', textAlign: 'left' }}>
                    <ScorePill score={it.score} />
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontSize: 12.5, fontWeight: 600, color: HT.text, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{it.title}</div>
                      <div style={{ fontSize: 10.5, color: HT.muted }}>{it.company}</div>
                    </div>
                    <Chip color={HT.success} bg={HT.successSoft} icon="check">ATS {it.ats}</Chip>
                  </button>
                ))}
              </div>
              <Btn kind="primary" full iconR="arrowR" onClick={() => onReview(ready.map((r) => r.id))}>Review &amp; approve</Btn>
            </Card>
          ) : (
            <Card style={{ padding: 16, textAlign: 'center' }}>
              <div style={{ width: 38, height: 38, borderRadius: 999, margin: '0 auto 10px', display: 'flex', alignItems: 'center', justifyContent: 'center', background: HT.successSoft }}>
                <Icon name="checkCircle" size={20} color={HT.success} />
              </div>
              <div style={{ fontSize: 14, fontWeight: 700, color: HT.text }}>Approval queue clear</div>
              <div style={{ fontSize: 12, color: HT.muted, marginTop: 2 }}>Everything you approved is on its way.</div>
            </Card>
          )}

          {/* interview prep */}
          <div onClick={() => { onNav('prep'); }} style={{ cursor: 'pointer' }}>
            <Card style={{ padding: cardPad }}>
              <div style={{ display: 'flex', gap: 11 }}>
                <AgentBadge agent="coach" size={34} />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 15, fontWeight: 700, color: HT.text, whiteSpace: 'nowrap' }}>Interview Tuesday, 9am</div>
                  <div style={{ fontSize: 12, color: HT.dim, marginTop: 3 }}>Lead Architect · Capgemini · in 3 days</div>
                  <div style={{ fontSize: 12, color: HT.muted, marginTop: 1 }}>{t.voice ? 'I prepped 12 questions + STAR answers' : 'Coach prepped 12 questions + STAR answers'}</div>
                  <div style={{ marginTop: 11 }}><Btn kind="soft" size="sm" iconR="arrowR">Review prep</Btn></div>
                </div>
              </div>
            </Card>
          </div>

          {/* follow-ups */}
          <Card style={{ padding: '13px 15px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 11 }}>
              <div style={{ width: 34, height: 34, borderRadius: 10, flexShrink: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', background: HT.dangerSoft }}>
                <Icon name="clock" size={17} color={HT.danger} />
              </div>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 14, fontWeight: 700, color: HT.text }}>2 follow-ups overdue</div>
                <div style={{ fontSize: 11.5, color: HT.muted, marginTop: 1 }}>Sent 12 &amp; 14 days ago — no reply yet</div>
              </div>
              <Icon name="chevronR" size={18} color={HT.muted} />
            </div>
          </Card>
        </div>
      </div>
    </>
  );
}

// ── STREAM ────────────────────────────────────────────────────────────────────
function StreamCard({ it, onReview, onApprove }) {
  const ready = it.state === 'ready';
  const m = statusMeta[it.state];
  return (
    <Card accent={ready} style={{ padding: 14 }}>
      <button onClick={() => onReview([it.id])} style={{ width: '100%', textAlign: 'left', background: 'none', border: 'none', padding: 0, cursor: 'pointer' }}>
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10, marginBottom: 10 }}>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <span style={{ fontSize: 14.5, fontWeight: 700, color: HT.text, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{it.title}</span>
              <Icon name="externalLink" size={12} color={HT.muted} />
            </div>
            <div style={{ fontSize: 11.5, color: HT.muted, marginTop: 3 }}>{it.company} · {it.loc} · <span style={{ color: HT.dim, fontWeight: 600 }}>{it.rate}</span></div>
          </div>
          <ScorePill score={it.score} />
        </div>
        <StageTrack stage={stageOf(it)} pct={Math.round(it.score * 100)} />
      </button>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginTop: 12 }}>
        <span style={{ fontSize: 11.5, fontWeight: 600, color: m.color, display: 'inline-flex', alignItems: 'center', gap: 5 }}>
          {ready && <Dot color={m.color} size={6} pulse />}{m.label}
        </span>
        {ready
          ? <Btn kind="success" size="sm" icon="check" onClick={() => onApprove(it.id)}>Approve</Btn>
          : <Icon name="chevronR" size={16} color={HT.muted} />}
      </div>
    </Card>
  );
}

function Stream({ items, onReview, onApprove }) {
  const [filter, setFilter] = useState('ready');
  const counts = {
    all: items.filter((x) => x.state !== 'applied' && x.state !== 'rejected').length,
    ready: items.filter((x) => x.state === 'ready').length,
    tailoring: items.filter((x) => x.state === 'tailoring').length,
    parked: items.filter((x) => x.state === 'parked').length,
  };
  const filtered = items.filter((x) => {
    if (x.state === 'applied' || x.state === 'rejected') return false;
    if (filter === 'all') return true;
    return x.state === filter;
  });
  const chips = [['all', 'All', counts.all], ['ready', 'Ready', counts.ready], ['tailoring', 'Tailoring', counts.tailoring], ['parked', 'Parked', counts.parked]];
  return (
    <>
      <Header title="Stream" sub="Every role · every stage" right={
        <div style={{ display: 'flex', gap: 10 }}>
          {['search', 'sliders'].map((ic) => <div key={ic} style={{ width: 36, height: 36, borderRadius: 10, display: 'flex', alignItems: 'center', justifyContent: 'center', background: HT.surface, border: `1px solid ${HT.border}` }}><Icon name={ic} size={17} color={HT.dim} /></div>)}
        </div>
      } />
      <div style={{ padding: '0 18px' }}>
        <div style={{ display: 'flex', gap: 8, marginBottom: 14, overflowX: 'auto', paddingBottom: 2 }}>
          {chips.map(([key, label, n]) => {
            const on = key === filter;
            return (
              <button key={key} onClick={() => setFilter(key)} style={{
                display: 'inline-flex', alignItems: 'center', gap: 6, padding: '7px 12px', borderRadius: 999, cursor: 'pointer',
                fontSize: 12.5, fontWeight: 600, whiteSpace: 'nowrap',
                background: on ? HT.accentSoft : HT.surface, color: on ? HT.accent : HT.dim,
                border: `1px solid ${on ? 'transparent' : HT.border}`,
              }}>{label}<span style={{ fontFamily: HT.mono, fontSize: 11, opacity: 0.8 }}>{n}</span></button>
            );
          })}
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 11, paddingBottom: 18 }}>
          {filtered.length ? filtered.map((it) => <StreamCard key={it.id} it={it} onReview={onReview} onApprove={onApprove} />)
            : <div style={{ textAlign: 'center', padding: '40px 0', color: HT.muted, fontSize: 13 }}>Nothing in this stage right now.</div>}
        </div>
      </div>
    </>
  );
}

// ── TRACKER ───────────────────────────────────────────────────────────────────
function Tracker({ items }) {
  const applied = [...APPLIED_SEED, ...items.filter((x) => x.state === 'applied')];
  const discovered = items.filter((x) => ['ready', 'tailoring', 'parked'].includes(x.state));
  const cols = [
    { key: 'disc', label: 'Discovered', color: HT.accent, list: discovered },
    { key: 'app', label: 'Applied', color: HT.purple, list: applied },
    { key: 'int', label: 'Interview', color: HT.warning, list: INTERVIEW_SEED },
    { key: 'off', label: 'Offered', color: HT.success, list: [] },
  ];
  return (
    <>
      <Header title="Tracker" sub="Your pipeline, every stage" right={<UserAvatar size={32} />} />
      <div style={{ display: 'flex', gap: 12, overflowX: 'auto', padding: '0 18px 18px', alignItems: 'flex-start' }}>
        {cols.map((c) => (
          <div key={c.key} style={{ width: 230, flexShrink: 0, background: HT.bgEl, border: `1px solid ${HT.border}`, borderRadius: 14, padding: 10 }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '4px 6px 10px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
                <Dot color={c.color} size={7} />
                <span style={{ fontSize: 12.5, fontWeight: 700, color: HT.text }}>{c.label}</span>
              </div>
              <span style={{ fontFamily: HT.mono, fontSize: 11.5, color: HT.muted }}>{c.list.length}</span>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {c.list.length ? c.list.map((it) => (
                <div key={it.id} style={{ background: HT.surface, border: `1px solid ${HT.border}`, borderRadius: 11, padding: 11 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, alignItems: 'flex-start' }}>
                    <span style={{ fontSize: 13, fontWeight: 600, color: HT.text }}>{it.title}</span>
                    <ScorePill score={it.score} />
                  </div>
                  <div style={{ fontSize: 11, color: HT.muted, marginTop: 4 }}>{it.company} · {it.loc}</div>
                  {it.when && <div style={{ marginTop: 8 }}><Chip color={HT.warning} bg={HT.warningSoft} icon="calendar">{it.when}</Chip></div>}
                </div>
              )) : (
                <div style={{ border: `1.5px dashed ${HT.border}`, borderRadius: 11, padding: '20px 10px', textAlign: 'center', fontSize: 11.5, color: HT.muted }}>Nothing here yet</div>
              )}
            </div>
          </div>
        ))}
      </div>
    </>
  );
}

// ── PREP ──────────────────────────────────────────────────────────────────────
const PREP_SESSIONS = [
  { id: 'la', title: 'Lead Architect', company: 'Capgemini', status: 'ready', when: 'Tue 9:00am' },
  { id: 'sa', title: 'Solutions Architect', company: 'Hays', status: 'progress' },
  { id: 'po', title: 'Product Owner', company: 'TCS', status: 'generating' },
];
const STATUS_PILL = {
  ready: { label: 'Prep ready', color: HT.success, soft: HT.successSoft },
  progress: { label: 'In progress', color: HT.accent, soft: HT.accentSoft },
  generating: { label: 'Generating…', color: HT.warning, soft: HT.warningSoft },
};

function Prep({ onOpen }) {
  return (
    <>
      <Header title="Prep" sub="AI mock-interview coaching" right={<Btn kind="soft" size="sm" icon="plus">New</Btn>} />
      <div style={{ padding: '0 18px 18px', display: 'flex', flexDirection: 'column', gap: 11 }}>
        {PREP_SESSIONS.map((s) => {
          const p = STATUS_PILL[s.status];
          return (
            <button key={s.id} onClick={() => s.status === 'ready' && onOpen(s.id)} style={{ background: 'none', border: 'none', padding: 0, cursor: s.status === 'ready' ? 'pointer' : 'default', textAlign: 'left' }}>
              <Card style={{ padding: 15 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                  <AgentBadge agent="coach" size={34} />
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 14.5, fontWeight: 700, color: HT.text }}>{s.title}</div>
                    <div style={{ fontSize: 12, color: HT.muted, marginTop: 1 }}>{s.company}{s.when ? ` · ${s.when}` : ''}</div>
                  </div>
                  <Chip color={p.color} bg={p.soft} icon={s.status === 'generating' ? 'clock' : undefined}>{p.label}</Chip>
                  {s.status === 'ready' && <Icon name="chevronR" size={17} color={HT.muted} />}
                </div>
              </Card>
            </button>
          );
        })}
      </div>
    </>
  );
}

// ── overlays ──────────────────────────────────────────────────────────────────
function Overlay({ children }) {
  return <div style={{ position: 'absolute', inset: 0, zIndex: 70, background: HT.bg, color: HT.text, fontFamily: HT.font, display: 'flex', flexDirection: 'column', animation: 'ovRise .2s ease-out' }}>{children}</div>;
}

function DimBar({ label, val }) {
  const c = val >= 0.85 ? HT.success : val >= 0.7 ? HT.accent : HT.warning;
  return (
    <div style={{ flex: 1 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
        <span style={{ fontSize: 10, color: HT.muted, fontWeight: 600 }}>{label}</span>
        <span style={{ fontSize: 10, color: HT.dim, fontFamily: HT.mono, fontWeight: 700 }}>{Math.round(val * 100)}</span>
      </div>
      <div style={{ height: 4, borderRadius: 999, background: HT.s2, overflow: 'hidden' }}><div style={{ width: `${val * 100}%`, height: '100%', background: c }} /></div>
    </div>
  );
}

function ReviewOverlay({ t, queue, idx, items, onAct, onClose }) {
  const [tab, setTab] = useState('cv');
  const it = items.find((x) => x.id === queue[idx]) || {};
  const dims = { Skills: 0.92, Experience: 0.85, Rate: 0.9, Location: 0.8 };
  return (
    <Overlay>
      <div style={{ height: 56, flexShrink: 0 }} />
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0 18px 12px' }}>
        <div style={{ width: 34, height: 34, borderRadius: 10, display: 'flex', alignItems: 'center', justifyContent: 'center', background: HT.surface, border: `1px solid ${HT.border}` }} />
        <span style={{ fontSize: 13, fontWeight: 600, color: HT.dim, whiteSpace: 'nowrap' }}>Application {idx + 1} of {queue.length}</span>
        <button onClick={onClose} style={{ width: 34, height: 34, borderRadius: 10, display: 'flex', alignItems: 'center', justifyContent: 'center', background: HT.surface, border: `1px solid ${HT.border}`, cursor: 'pointer' }}><Icon name="x" size={16} color={HT.dim} /></button>
      </div>
      <div style={{ flex: 1, overflow: 'auto', padding: '0 18px' }}>
        <div style={{ fontSize: 22, fontWeight: 700, letterSpacing: '-0.02em', marginTop: 4 }}>{it.title}</div>
        <div style={{ fontSize: 13, color: HT.dim, marginTop: 4 }}>{it.company} · {it.loc} · <span style={{ color: HT.text, fontWeight: 600 }}>{it.rate}</span></div>
        <Card style={{ padding: 15, marginTop: 16 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 13, marginBottom: 14 }}>
            <ScorePill score={it.score} size="lg" />
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 13.5, fontWeight: 700 }}>{it.score >= 0.9 ? 'Excellent match' : 'Strong match for you'}</div>
              <div style={{ fontSize: 11.5, color: HT.muted }}>Scored by Scorer across 4 dimensions</div>
            </div>
          </div>
          <div style={{ display: 'flex', gap: 12 }}>{Object.entries(dims).map(([k, v]) => <DimBar key={k} label={k} val={v} />)}</div>
        </Card>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', margin: '18px 0 10px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}><AgentBadge agent="tailor" size={26} /><span style={{ fontSize: 13, fontWeight: 700, whiteSpace: 'nowrap' }}>Tailored by Tailor</span></div>
          <Chip color={HT.success} bg={HT.successSoft} icon="checkCircle">ATS {it.ats}%</Chip>
        </div>
        <div style={{ display: 'flex', gap: 6, marginBottom: 10 }}>
          {[['cv', 'CV'], ['cl', 'Cover letter']].map(([k, l]) => (
            <button key={k} onClick={() => setTab(k)} style={{ flex: 1, padding: 8, borderRadius: 9, cursor: 'pointer', fontSize: 12.5, fontWeight: tab === k ? 700 : 600,
              background: tab === k ? HT.accentSoft : HT.surface, color: tab === k ? HT.accent : HT.dim, border: `1px solid ${tab === k ? 'transparent' : HT.border}` }}>{l}</button>
          ))}
        </div>
        <div style={{ background: '#f7f7f4', borderRadius: 12, padding: 18, display: 'flex', flexDirection: 'column', gap: 10 }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
            <div style={{ height: 10, width: '46%', borderRadius: 3, background: '#2a2a30' }} />
            <div style={{ height: 5, width: '64%', borderRadius: 3, background: '#bcbcc4' }} />
          </div>
          <div style={{ height: 1, background: '#e2e2dc' }} />
          {(tab === 'cv'
            ? [['Profile', ['92%', '88%', '70%']], ['Experience', ['96%', '82%', '90%', '60%']], ['Skills', ['78%', '85%']]]
            : [['Dear Hiring Manager', ['90%', '84%', '74%', '88%']], ['', ['80%', '92%', '64%']]]
          ).map(([h, ws], hi) => (
            <div key={hi} style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
              {h && <div style={{ height: 6, width: h.length > 12 ? 130 : 70, borderRadius: 3, background: HT.accent }} />}
              {ws.map((w, i) => <div key={i} style={{ height: 4.5, width: w, borderRadius: 3, background: '#d2d2cb' }} />)}
            </div>
          ))}
        </div>
        <div style={{ display: 'flex', gap: 9, alignItems: 'flex-start', margin: '16px 0 18px', padding: 12, borderRadius: 12, background: HT.accentSoft }}>
          <Icon name="arrowR" size={16} color={HT.accent} style={{ marginTop: 1 }} />
          <span style={{ fontSize: 12, color: HT.dim, lineHeight: 1.5 }}>Approve and it moves to <strong style={{ color: HT.text }}>Applied</strong>. The moment you mark an interview, <strong style={{ color: HT.warning }}>Coach</strong> starts prepping automatically.</span>
        </div>
      </div>
      <div style={{ flexShrink: 0, display: 'flex', gap: 10, padding: '12px 18px', borderTop: `1px solid ${HT.border}`, background: HT.bgEl }}>
        <Btn kind="ghost" style={{ flex: '0 0 auto', padding: '11px 18px' }} icon="x" onClick={() => onAct('reject')}>Reject</Btn>
        <Btn kind="primary" style={{ flex: 1 }} iconR="send" onClick={() => onAct('approve')}>Approve &amp; apply</Btn>
      </div>
      <div style={{ height: 30, flexShrink: 0 }} />
    </Overlay>
  );
}

const QUESTIONS = [
  { q: 'Walk me through a complex migration you led end-to-end.', cat: 'Behavioural', star: true },
  { q: 'How do you choose between on-prem and cloud for a regulated client?', cat: 'Technical' },
  { q: 'Tell me about a time a stakeholder disagreed with your design.', cat: 'Behavioural' },
  { q: 'How do you keep a multi-team delivery aligned to one architecture?', cat: 'Leadership' },
];

function PrepOverlay({ onClose }) {
  const [open, setOpen] = useState(0);
  return (
    <Overlay>
      <div style={{ height: 56, flexShrink: 0 }} />
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '0 18px 14px' }}>
        <button onClick={onClose} style={{ width: 34, height: 34, borderRadius: 10, display: 'flex', alignItems: 'center', justifyContent: 'center', background: HT.surface, border: `1px solid ${HT.border}`, cursor: 'pointer' }}><Icon name="chevronR" size={17} color={HT.dim} style={{ transform: 'scaleX(-1)' }} /></button>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 17, fontWeight: 700 }}>Lead Architect · Capgemini</div>
          <div style={{ fontSize: 11.5, color: HT.muted }}>Tuesday 9:00am · prepped by Coach</div>
        </div>
        <AgentBadge agent="coach" size={32} />
      </div>
      <div style={{ flex: 1, overflow: 'auto', padding: '0 18px 18px' }}>
        <Card style={{ padding: 14, marginBottom: 16 }}>
          <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: '0.06em', color: HT.muted, marginBottom: 8 }}>COMPANY RESEARCH</div>
          <p style={{ margin: 0, fontSize: 12.5, lineHeight: 1.55, color: HT.dim }}>Capgemini's UK arm is scaling cloud-migration delivery for financial-services clients. Expect emphasis on <strong style={{ color: HT.text }}>regulated workloads, hybrid landing zones</strong>, and stakeholder leadership.</p>
        </Card>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
          <span style={{ fontSize: 13, fontWeight: 700 }}>12 likely questions</span>
          <Btn kind="soft" size="sm" icon="calendar">Add to calendar</Btn>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {QUESTIONS.map((item, i) => {
            const isOpen = open === i;
            return (
              <Card key={i} style={{ padding: 0, overflow: 'hidden' }}>
                <button onClick={() => setOpen(isOpen ? -1 : i)} style={{ width: '100%', display: 'flex', alignItems: 'flex-start', gap: 10, padding: 13, background: 'none', border: 'none', cursor: 'pointer', textAlign: 'left' }}>
                  <span style={{ fontFamily: HT.mono, fontSize: 12, fontWeight: 700, color: HT.muted, marginTop: 1 }}>{String(i + 1).padStart(2, '0')}</span>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontSize: 13, fontWeight: 600, color: HT.text, lineHeight: 1.4 }}>{item.q}</div>
                    <Chip color={HT.purple} bg={HT.purpleSoft} style={{ marginTop: 7 }}>{item.cat}</Chip>
                  </div>
                  <Icon name="chevronR" size={15} color={HT.muted} style={{ transform: isOpen ? 'rotate(90deg)' : 'none', marginTop: 2 }} />
                </button>
                {isOpen && (
                  <div style={{ padding: '0 13px 13px 39px' }}>
                    <div style={{ padding: 11, borderRadius: 10, background: HT.s2, borderLeft: `2px solid ${HT.success}` }}>
                      <div style={{ fontSize: 10.5, fontWeight: 700, letterSpacing: '0.05em', color: HT.success, marginBottom: 5 }}>STAR ANSWER · from your story bank</div>
                      <p style={{ margin: 0, fontSize: 12, lineHeight: 1.55, color: HT.dim }}>At a UK bank I led a 14-month migration of 40+ services to a hybrid landing zone — cut release time 60% and passed audit with zero findings. I'd frame the situation, the architecture decisions, and the measurable result.</p>
                    </div>
                  </div>
                )}
              </Card>
            );
          })}
        </div>
      </div>
      <div style={{ height: 30, flexShrink: 0 }} />
    </Overlay>
  );
}

// ── PhoneApp ──────────────────────────────────────────────────────────────────
function PhoneApp({ t }) {
  const [tab, setTab] = useState('today');
  const [items, setItems] = useState(SEED);
  const [review, setReview] = useState(null);
  const [prep, setPrep] = useState(null);
  const [toast, setToast] = useState(null);
  const tRef = useRef();
  const showToast = (m) => { setToast(m); clearTimeout(tRef.current); tRef.current = setTimeout(() => setToast(null), 2600); };

  const approve = (id) => { setItems((xs) => xs.map((x) => x.id === id ? { ...x, state: 'applied' } : x)); showToast('Applied · Coach preps when you mark an interview'); };
  const reject = (id) => { setItems((xs) => xs.map((x) => x.id === id ? { ...x, state: 'rejected' } : x)); showToast('Dismissed'); };
  const openReview = (ids) => ids.length && setReview({ queue: ids, idx: 0 });
  const reviewAct = (act) => {
    const cur = review.queue[review.idx];
    act === 'approve' ? approve(cur) : reject(cur);
    const ni = review.idx + 1;
    ni >= review.queue.length ? setReview(null) : setReview({ ...review, idx: ni });
  };

  return (
    <div style={{ position: 'absolute', inset: 0, background: HT.bg, color: HT.text, fontFamily: HT.font, display: 'flex', flexDirection: 'column', letterSpacing: '-0.005em' }}>
      <div style={{ height: 56, flexShrink: 0 }} />
      <div style={{ flex: 1, overflow: 'auto' }}>
        {tab === 'today' && <Today t={t} items={items} onReview={openReview} onNav={setTab} onPrep={() => setPrep('la')} />}
        {tab === 'stream' && <Stream items={items} onReview={openReview} onApprove={approve} />}
        {tab === 'track' && <Tracker items={items} />}
        {tab === 'prep' && <Prep onOpen={() => setPrep('la')} />}
      </div>
      <NavBar active={tab} onNav={setTab} />
      <div style={{ height: 30, flexShrink: 0 }} />

      {toast && <Toast msg={toast} />}
      {review && <ReviewOverlay t={t} queue={review.queue} idx={review.idx} items={items} onAct={reviewAct} onClose={() => setReview(null)} />}
      {prep && <PrepOverlay onClose={() => setPrep(null)} />}
    </div>
  );
}

Object.assign(window, { PhoneApp, applyAccent });

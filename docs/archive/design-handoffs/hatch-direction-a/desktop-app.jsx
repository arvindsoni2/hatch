// desktop-app.jsx — Direction A, desktop layout (sidebar-led, matches original Hatch).
// Reuses primitives from hatch-ui.jsx. Self-contained data model + approve loop.
const { useState, useRef } = React;

// ── data ──────────────────────────────────────────────────────────────────────
const D_SEED = [
  { id: 'sa',  title: 'Solutions Architect',  company: 'Hays',         loc: 'London',    rate: '£600–675/day', score: 1.0,  ats: 95, state: 'ready', age: '3h' },
  { id: 'ta',  title: 'Technical Architect',  company: 'Yolk',         loc: 'Reading',   rate: '£700–800/day', score: 0.86, ats: 88, state: 'ready', age: '3h' },
  { id: 'swa', title: 'Software Architect',   company: 'BELCAN',       loc: 'Newcastle', rate: '£70/day',      score: 0.93, ats: 90, state: 'ready', age: '5h' },
  { id: 'soa', title: 'Solution Architect — On-Prem', company: 'Outsource UK', loc: 'Preston', rate: '£71–96/day', score: 0.90, state: 'tailoring', age: '1h' },
  { id: 'ea',  title: 'Enterprise Architect', company: 'Version 1',    loc: 'Manchester', rate: '£650/day',    score: 0.79, state: 'tailoring', age: '2h' },
  { id: 'sv',  title: 'Service Architect',    company: 'Involved',     loc: 'London',    rate: '£600–675/day', score: 0.68, state: 'parked', age: '6h' },
  { id: 'da',  title: 'Data Architect',       company: 'Reed',         loc: 'Bristol',   rate: '£550/day',     score: 0.64, state: 'parked', age: '8h' },
];
const D_APPLIED = [
  { id: 'ca', title: 'Cloud Architect', company: 'Lloyds', loc: 'Remote', rate: '£650/day', score: 0.84, when: 'Sent 2d ago' },
  { id: 'pa', title: 'Platform Architect', company: 'Sky', loc: 'Leeds', rate: '£600/day', score: 0.81, when: 'Sent 4d ago' },
];
const D_INTERVIEW = [{ id: 'la', title: 'Lead Architect', company: 'Capgemini', loc: 'London', rate: '£700/day', score: 0.91, when: 'Tue 9:00am' }];

const dStage = (it) => it.state === 'tailoring' ? 2 : it.state === 'parked' ? 1 : 3;
const dStatus = {
  ready: { label: 'Ready to send', color: HT.success },
  tailoring: { label: 'Tailoring…', color: HT.success },
  parked: { label: 'Below match bar', color: HT.warning },
  applied: { label: 'Applied', color: HT.accent },
  rejected: { label: 'Dismissed', color: HT.muted },
};

// ── activity feed seed ──────────────────────────────────────────────────────
const ACTIVITY = [
  { agent: 'tailor', time: '7:05am', text: 'Drafted CV + cover letter for 3 strong matches', tag: 'ATS 88–95%' },
  { agent: 'scorer', time: '6:18am', text: 'Ranked 75 roles — 12 cleared your 75% bar', tag: '12 passed' },
  { agent: 'scout',  time: '6:02am', text: 'Scanned 6 boards, found 75 new architect roles', tag: '6 boards' },
  { agent: 'coach',  time: 'Yesterday', text: 'Prepped 12 interview questions for Capgemini', tag: 'Tue 9am' },
];

// ── sidebar ───────────────────────────────────────────────────────────────────
function Logo() {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
      <div style={{ width: 30, height: 30, borderRadius: 9, background: HT.accent, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
        <Icon name="layers" size={17} color="#fff" sw={2.3} />
      </div>
      <span style={{ fontSize: 18, fontWeight: 800, letterSpacing: '-0.02em', color: HT.text }}>Hatch</span>
    </div>
  );
}

function Sidebar({ active, onNav, badges }) {
  const nav = [['today', 'Today', 'home'], ['stream', 'Stream', 'layers'], ['track', 'Tracker', 'briefcase'], ['prep', 'Prep', 'mic']];
  return (
    <div style={{ width: 248, flexShrink: 0, background: HT.bgEl, borderRight: `1px solid ${HT.border}`, display: 'flex', flexDirection: 'column', padding: '22px 16px' }}>
      <div style={{ padding: '0 8px 24px' }}><Logo /></div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
        {nav.map(([key, label, icon]) => {
          const on = key === active;
          return (
            <button key={key} onClick={() => onNav(key)} style={{
              display: 'flex', alignItems: 'center', gap: 12, padding: '10px 12px', borderRadius: 10, cursor: 'pointer',
              background: on ? HT.accentSoft : 'transparent', border: 'none', textAlign: 'left',
              color: on ? HT.accent : HT.dim, fontSize: 14, fontWeight: on ? 700 : 500, fontFamily: HT.font,
            }}>
              <Icon name={icon} size={19} color={on ? HT.accent : HT.muted} sw={on ? 2.3 : 2} />
              <span style={{ flex: 1 }}>{label}</span>
              {badges[key] > 0 && (
                <span style={{ fontFamily: HT.mono, fontSize: 11, fontWeight: 700, minWidth: 20, textAlign: 'center', padding: '2px 6px', borderRadius: 999,
                  background: on ? HT.accent : HT.s3, color: on ? '#fff' : HT.dim }}>{badges[key]}</span>
              )}
            </button>
          );
        })}
      </div>

      {/* agent status card */}
      <div style={{ marginTop: 'auto', background: HT.surface, border: `1px solid ${HT.border}`, borderRadius: 14, padding: 14 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 7, marginBottom: 12 }}>
          <Dot color={HT.success} size={7} pulse />
          <span style={{ fontSize: 12, fontWeight: 700, color: HT.text, whiteSpace: 'nowrap' }}>Agents running</span>
          <span style={{ marginLeft: 'auto', fontSize: 10.5, color: HT.muted }}>3h ago</span>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 9 }}>
          {PIPE.map((k) => (
            <div key={k} style={{ display: 'flex', alignItems: 'center', gap: 9 }}>
              <AgentBadge agent={k} size={22} />
              <span style={{ fontSize: 11.5, color: HT.dim, fontWeight: 500 }}>{AGENTS[k].name}</span>
              <span style={{ marginLeft: 'auto', fontSize: 10.5, color: HT.muted }}>{AGENTS[k].role}</span>
            </div>
          ))}
        </div>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginTop: 14, padding: '4px 6px' }}>
        <UserAvatar size={30} />
        <div style={{ minWidth: 0 }}>
          <div style={{ fontSize: 12.5, fontWeight: 600, color: HT.text }}>Arvind Soni</div>
          <div style={{ fontSize: 10.5, color: HT.muted, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>Solutions Architect</div>
        </div>
        <Icon name="more" size={16} color={HT.muted} style={{ marginLeft: 'auto' }} />
      </div>
    </div>
  );
}

// ── topbar ────────────────────────────────────────────────────────────────────
function TopBar({ title, sub }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '22px 32px 0' }}>
      <div>
        <h1 style={{ margin: 0, fontSize: 28, fontWeight: 800, letterSpacing: '-0.03em', color: HT.text }}>{title}</h1>
        {sub && <div style={{ fontSize: 13, color: HT.muted, marginTop: 3 }}>{sub}</div>}
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 9, width: 240, padding: '9px 13px', borderRadius: 11, background: HT.surface, border: `1px solid ${HT.border}` }}>
          <Icon name="search" size={16} color={HT.muted} />
          <span style={{ fontSize: 13, color: HT.muted }}>Search roles…</span>
        </div>
        <div style={{ position: 'relative', width: 40, height: 40, borderRadius: 11, display: 'flex', alignItems: 'center', justifyContent: 'center', background: HT.surface, border: `1px solid ${HT.border}` }}>
          <Icon name="bell" size={18} color={HT.dim} />
          <span style={{ position: 'absolute', top: 9, right: 9, width: 7, height: 7, borderRadius: 999, background: HT.danger, border: `1.5px solid ${HT.surface}` }} />
        </div>
      </div>
    </div>
  );
}

// ── hero pipeline rail (the seamless flow, front and centre) ──────────────────
function PipelineRail({ items, onJump }) {
  const counts = {
    scout: 75,
    scorer: 12,
    tailor: items.filter((x) => x.state === 'ready' || x.state === 'tailoring').length,
    coach: 1,
  };
  const sub = { scout: 'found today', scorer: 'cleared your bar', tailor: 'in tailoring', coach: 'interview prep' };
  return (
    <div style={{ display: 'flex', alignItems: 'stretch', background: HT.surface, border: `1px solid ${HT.border}`, borderRadius: 18, padding: '20px 8px', marginBottom: 22 }}>
      {PIPE.map((k, i) => {
        const a = AGENTS[k];
        const last = i === PIPE.length - 1;
        return (
          <React.Fragment key={k}>
            <button onClick={() => onJump(k)} style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 8, padding: '4px 12px', background: 'none', border: 'none', cursor: 'pointer' }}>
              <AgentBadge agent={k} size={42} />
              <div style={{ fontFamily: HT.mono, fontSize: 30, fontWeight: 800, color: HT.text, lineHeight: 1 }}>{counts[k]}</div>
              <div style={{ fontSize: 13, fontWeight: 700, color: a.color }}>{a.name}</div>
              <div style={{ fontSize: 11, color: HT.muted }}>{sub[k]}</div>
            </button>
            {!last && (
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', paddingTop: 18, color: HT.borderStrong }}>
                <Icon name="arrowR" size={18} color={HT.borderStrong} sw={2.2} />
                <div style={{ fontSize: 9.5, color: HT.muted, marginTop: 6, fontStyle: 'italic' }}>{[63, 9, 2][i]} →</div>
              </div>
            )}
          </React.Fragment>
        );
      })}
    </div>
  );
}

// ── TODAY ─────────────────────────────────────────────────────────────────────
function DToday({ t, items, onReview, onNav }) {
  const ready = items.filter((x) => x.state === 'ready');
  return (
    <div style={{ padding: '22px 32px 32px', overflow: 'auto', flex: 1 }}>
      <PipelineRail items={items} onJump={() => onNav('stream')} />

      <div style={{ display: 'grid', gridTemplateColumns: '1.55fr 1fr', gap: 22, alignItems: 'start' }}>
        {/* left — needs you */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 9 }}>
            <span style={{ fontSize: 15, fontWeight: 700, color: HT.text, whiteSpace: 'nowrap' }}>Needs you</span>
            <Chip color={HT.accent} bg={HT.accentSoft}>{ready.length + 2} items</Chip>
          </div>

          {ready.length > 0 ? (
            <Card accent style={{ padding: 20 }}>
              <div style={{ display: 'flex', gap: 13, marginBottom: 16 }}>
                <AgentBadge agent="tailor" size={40} ring />
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 17, fontWeight: 700, color: HT.text }}>{ready.length} applications ready to send</div>
                  <div style={{ fontSize: 13, color: HT.muted, marginTop: 2 }}>{t.voice ? 'I tailored a CV + cover letter for each. Your call.' : 'CV + cover letter tailored for each.'}</div>
                </div>
                <Btn kind="primary" iconR="arrowR" onClick={() => onReview(ready.map((r) => r.id))}>Review all</Btn>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {ready.map((it) => (
                  <button key={it.id} onClick={() => onReview([it.id])} style={{ display: 'flex', alignItems: 'center', gap: 13, padding: '11px 13px', borderRadius: 11, background: HT.s2, border: 'none', cursor: 'pointer', textAlign: 'left' }}>
                    <ScorePill score={it.score} />
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontSize: 14, fontWeight: 600, color: HT.text }}>{it.title}</div>
                      <div style={{ fontSize: 11.5, color: HT.muted }}>{it.company} · {it.loc} · {it.rate}</div>
                    </div>
                    <Chip color={HT.success} bg={HT.successSoft} icon="check">ATS {it.ats}</Chip>
                    <Icon name="chevronR" size={17} color={HT.muted} />
                  </button>
                ))}
              </div>
            </Card>
          ) : (
            <Card style={{ padding: 28, textAlign: 'center' }}>
              <div style={{ width: 44, height: 44, borderRadius: 999, margin: '0 auto 12px', display: 'flex', alignItems: 'center', justifyContent: 'center', background: HT.successSoft }}>
                <Icon name="checkCircle" size={24} color={HT.success} />
              </div>
              <div style={{ fontSize: 16, fontWeight: 700, color: HT.text }}>Approval queue clear</div>
              <div style={{ fontSize: 13, color: HT.muted, marginTop: 3 }}>Everything you approved is on its way. Scout keeps hunting.</div>
            </Card>
          )}

          {/* interview prep */}
          <Card style={{ padding: 18 }}>
            <div style={{ display: 'flex', gap: 13, alignItems: 'center' }}>
              <AgentBadge agent="coach" size={40} />
              <div style={{ flex: 1 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 9 }}>
                  <span style={{ fontSize: 16, fontWeight: 700, color: HT.text }}>Interview Tuesday, 9:00am</span>
                  <Chip color={HT.warning} bg={HT.warningSoft}>in 3 days</Chip>
                </div>
                <div style={{ fontSize: 13, color: HT.dim, marginTop: 2 }}>Lead Architect · Capgemini — {t.voice ? 'I prepped 12 questions + STAR answers' : 'Coach prepped 12 questions + STAR answers'}</div>
              </div>
              <Btn kind="soft" iconR="arrowR" onClick={() => onNav('prep')}>Review prep</Btn>
            </div>
          </Card>

          {/* follow ups */}
          <Card style={{ padding: 18 }}>
            <div style={{ display: 'flex', gap: 13, alignItems: 'center' }}>
              <div style={{ width: 40, height: 40, borderRadius: 12, flexShrink: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', background: HT.dangerSoft }}>
                <Icon name="clock" size={20} color={HT.danger} />
              </div>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 16, fontWeight: 700, color: HT.text }}>2 follow-ups overdue</div>
                <div style={{ fontSize: 12.5, color: HT.muted, marginTop: 1 }}>Lloyds &amp; Sky — sent 12 &amp; 14 days ago, no reply</div>
              </div>
              <Btn kind="ghost" iconR="send">Nudge both</Btn>
            </div>
          </Card>
        </div>

        {/* right — activity */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <span style={{ fontSize: 15, fontWeight: 700, color: HT.text }}>Agent activity</span>
          <Card style={{ padding: 6 }}>
            {ACTIVITY.map((a, i) => (
              <div key={i} style={{ display: 'flex', gap: 12, padding: '13px 12px', borderBottom: i < ACTIVITY.length - 1 ? `1px solid ${HT.borderSubtle}` : 'none' }}>
                <AgentBadge agent={a.agent} size={30} />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
                    <span style={{ fontSize: 12.5, fontWeight: 700, color: AGENTS[a.agent].color }}>{AGENTS[a.agent].name}</span>
                    <span style={{ fontSize: 10.5, color: HT.muted }}>{a.time}</span>
                  </div>
                  <div style={{ fontSize: 12.5, color: HT.dim, marginTop: 3, lineHeight: 1.45 }}>{a.text}</div>
                  <Chip color={HT.dim} bg={HT.s2} style={{ marginTop: 7 }}>{a.tag}</Chip>
                </div>
              </div>
            ))}
          </Card>

          {/* week stats */}
          <Card style={{ padding: 18 }}>
            <div style={{ fontSize: 12.5, fontWeight: 700, color: HT.text, marginBottom: 14 }}>This week</div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
              {[['Applied', '14', HT.accent], ['Interviews', '2', HT.warning], ['Response rate', '21%', HT.success], ['Avg match', '83%', HT.purple]].map(([l, v, c]) => (
                <div key={l}>
                  <div style={{ fontFamily: HT.mono, fontSize: 24, fontWeight: 800, color: c, lineHeight: 1 }}>{v}</div>
                  <div style={{ fontSize: 11.5, color: HT.muted, marginTop: 4 }}>{l}</div>
                </div>
              ))}
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}

// ── STREAM (table) ──────────────────────────────────────────────────────────
function DStream({ items, onReview, onApprove }) {
  const [filter, setFilter] = useState('all');
  const visible = items.filter((x) => !['applied', 'rejected'].includes(x.state));
  const counts = {
    all: visible.length,
    ready: visible.filter((x) => x.state === 'ready').length,
    tailoring: visible.filter((x) => x.state === 'tailoring').length,
    parked: visible.filter((x) => x.state === 'parked').length,
  };
  const rows = visible.filter((x) => filter === 'all' || x.state === filter);
  const chips = [['all', 'All'], ['ready', 'Ready'], ['tailoring', 'Tailoring'], ['parked', 'Parked']];
  return (
    <div style={{ padding: '20px 32px 32px', overflow: 'auto', flex: 1 }}>
      <div style={{ display: 'flex', gap: 9, marginBottom: 18 }}>
        {chips.map(([key, label]) => {
          const on = key === filter;
          return (
            <button key={key} onClick={() => setFilter(key)} style={{
              display: 'inline-flex', alignItems: 'center', gap: 7, padding: '8px 14px', borderRadius: 999, cursor: 'pointer',
              fontSize: 13, fontWeight: 600, background: on ? HT.accentSoft : HT.surface, color: on ? HT.accent : HT.dim,
              border: `1px solid ${on ? 'transparent' : HT.border}`,
            }}>{label}<span style={{ fontFamily: HT.mono, fontSize: 11.5, opacity: 0.8 }}>{counts[key]}</span></button>
          );
        })}
      </div>

      <Card style={{ padding: 0, overflow: 'hidden' }}>
        {/* header row */}
        <div style={{ display: 'grid', gridTemplateColumns: '2.4fr 0.7fr 2fr 1.4fr 1fr', gap: 16, padding: '13px 20px', borderBottom: `1px solid ${HT.border}`, fontSize: 11, fontWeight: 700, letterSpacing: '0.04em', color: HT.muted }}>
          <span>ROLE</span><span>MATCH</span><span>PIPELINE STAGE</span><span>STATUS</span><span style={{ textAlign: 'right' }}>ACTION</span>
        </div>
        {rows.map((it, i) => {
          const m = dStatus[it.state];
          const ready = it.state === 'ready';
          return (
            <div key={it.id} style={{ display: 'grid', gridTemplateColumns: '2.4fr 0.7fr 2fr 1.4fr 1fr', gap: 16, padding: '15px 20px', alignItems: 'center', borderBottom: i < rows.length - 1 ? `1px solid ${HT.borderSubtle}` : 'none', cursor: 'pointer', background: ready ? HT.accentSoft : 'transparent' }}
              onClick={() => onReview([it.id])}>
              <div style={{ minWidth: 0 }}>
                <div style={{ fontSize: 14, fontWeight: 700, color: HT.text }}>{it.title}</div>
                <div style={{ fontSize: 11.5, color: HT.muted, marginTop: 2 }}>{it.company} · {it.loc} · <span style={{ color: HT.dim, fontWeight: 600 }}>{it.rate}</span></div>
              </div>
              <ScorePill score={it.score} />
              <div style={{ paddingRight: 8 }}><StageTrack stage={dStage(it)} pct={Math.round(it.score * 100)} labels={false} compact /></div>
              <span style={{ fontSize: 12, fontWeight: 600, color: m.color, display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                {ready && <Dot color={m.color} size={6} pulse />}{m.label}
              </span>
              <div style={{ display: 'flex', justifyContent: 'flex-end' }} onClick={(e) => e.stopPropagation()}>
                {ready ? <Btn kind="success" size="sm" icon="check" onClick={() => onApprove(it.id)}>Approve</Btn>
                  : <Btn kind="ghost" size="sm" iconR="chevronR" onClick={() => onReview([it.id])}>Open</Btn>}
              </div>
            </div>
          );
        })}
        {!rows.length && <div style={{ padding: '48px', textAlign: 'center', color: HT.muted, fontSize: 13 }}>Nothing in this stage right now.</div>}
      </Card>
    </div>
  );
}

// ── TRACKER (kanban) ──────────────────────────────────────────────────────────
function DTracker({ items }) {
  const cols = [
    { key: 'disc', label: 'Discovered', color: HT.accent, list: items.filter((x) => ['ready', 'tailoring', 'parked'].includes(x.state)) },
    { key: 'app', label: 'Applied', color: HT.purple, list: [...D_APPLIED, ...items.filter((x) => x.state === 'applied')] },
    { key: 'int', label: 'Interview', color: HT.warning, list: D_INTERVIEW },
    { key: 'off', label: 'Offered', color: HT.success, list: [] },
  ];
  return (
    <div style={{ padding: '22px 32px 32px', overflow: 'auto', flex: 1 }}>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 18, alignItems: 'start' }}>
        {cols.map((c) => (
          <div key={c.key} style={{ background: HT.bgEl, border: `1px solid ${HT.border}`, borderRadius: 16, padding: 13 }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '4px 6px 12px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <Dot color={c.color} size={8} />
                <span style={{ fontSize: 13.5, fontWeight: 700, color: HT.text }}>{c.label}</span>
              </div>
              <span style={{ fontFamily: HT.mono, fontSize: 12, color: HT.muted }}>{c.list.length}</span>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {c.list.length ? c.list.map((it) => (
                <div key={it.id} style={{ background: HT.surface, border: `1px solid ${HT.border}`, borderRadius: 12, padding: 13 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, alignItems: 'flex-start' }}>
                    <span style={{ fontSize: 13.5, fontWeight: 600, color: HT.text }}>{it.title}</span>
                    <ScorePill score={it.score} />
                  </div>
                  <div style={{ fontSize: 11.5, color: HT.muted, marginTop: 5 }}>{it.company} · {it.loc}</div>
                  {it.when && <div style={{ marginTop: 9 }}><Chip color={c.key === 'int' ? HT.warning : HT.muted} bg={c.key === 'int' ? HT.warningSoft : HT.s2} icon={c.key === 'int' ? 'calendar' : 'clock'}>{it.when}</Chip></div>}
                </div>
              )) : (
                <div style={{ border: `1.5px dashed ${HT.border}`, borderRadius: 12, padding: '28px 12px', textAlign: 'center', fontSize: 12, color: HT.muted }}>Nothing here yet</div>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── PREP (master-detail) ────────────────────────────────────────────────────
const D_PREP = [
  { id: 'la', title: 'Lead Architect', company: 'Capgemini', status: 'ready', when: 'Tue 9:00am' },
  { id: 'sa', title: 'Solutions Architect', company: 'Hays', status: 'progress' },
  { id: 'po', title: 'Product Owner', company: 'TCS', status: 'generating' },
];
const D_PILL = {
  ready: { label: 'Prep ready', color: HT.success, soft: HT.successSoft },
  progress: { label: 'In progress', color: HT.accent, soft: HT.accentSoft },
  generating: { label: 'Generating…', color: HT.warning, soft: HT.warningSoft },
};
const D_QUESTIONS = [
  { q: 'Walk me through a complex migration you led end-to-end.', cat: 'Behavioural' },
  { q: 'How do you choose between on-prem and cloud for a regulated client?', cat: 'Technical' },
  { q: 'Tell me about a time a stakeholder disagreed with your design.', cat: 'Behavioural' },
  { q: 'How do you keep a multi-team delivery aligned to one architecture?', cat: 'Leadership' },
];

function DPrep() {
  const [sel, setSel] = useState('la');
  const [open, setOpen] = useState(0);
  const cur = D_PREP.find((s) => s.id === sel);
  return (
    <div style={{ flex: 1, display: 'grid', gridTemplateColumns: '320px 1fr', minHeight: 0 }}>
      {/* list */}
      <div style={{ borderRight: `1px solid ${HT.border}`, padding: '20px 16px', overflow: 'auto' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0 6px 12px' }}>
          <span style={{ fontSize: 13, fontWeight: 700, color: HT.text }}>Sessions</span>
          <Btn kind="soft" size="sm" icon="plus">New</Btn>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {D_PREP.map((s) => {
            const p = D_PILL[s.status];
            const on = s.id === sel;
            return (
              <button key={s.id} onClick={() => s.status === 'ready' && setSel(s.id)} style={{
                display: 'flex', alignItems: 'center', gap: 11, padding: 12, borderRadius: 12, cursor: s.status === 'ready' ? 'pointer' : 'default', textAlign: 'left',
                background: on ? HT.accentSoft : HT.surface, border: `1px solid ${on ? 'transparent' : HT.border}`,
              }}>
                <AgentBadge agent="coach" size={30} />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 13.5, fontWeight: 700, color: HT.text }}>{s.title}</div>
                  <div style={{ fontSize: 11, color: HT.muted }}>{s.company}{s.when ? ` · ${s.when}` : ''}</div>
                </div>
                <span style={{ width: 8, height: 8, borderRadius: 999, background: p.color, flexShrink: 0 }} />
              </button>
            );
          })}
        </div>
      </div>

      {/* detail */}
      <div style={{ padding: '24px 32px', overflow: 'auto' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 13, marginBottom: 20 }}>
          <AgentBadge agent="coach" size={40} />
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 20, fontWeight: 700, color: HT.text }}>{cur.title} · {cur.company}</div>
            <div style={{ fontSize: 12.5, color: HT.muted, marginTop: 2 }}>{cur.when || 'No date yet'} · prepped by Coach</div>
          </div>
          <Btn kind="soft" icon="calendar">Add to calendar</Btn>
        </div>

        <Card style={{ padding: 18, marginBottom: 22 }}>
          <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: '0.06em', color: HT.muted, marginBottom: 9 }}>COMPANY RESEARCH</div>
          <p style={{ margin: 0, fontSize: 13.5, lineHeight: 1.6, color: HT.dim }}>Capgemini's UK arm is scaling cloud-migration delivery for financial-services clients. Expect emphasis on <strong style={{ color: HT.text }}>regulated workloads, hybrid landing zones</strong>, and cross-team stakeholder leadership. Your Lloyds migration is the strongest story to lead with.</p>
        </Card>

        <div style={{ fontSize: 15, fontWeight: 700, color: HT.text, marginBottom: 12 }}>12 likely questions</div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 9 }}>
          {D_QUESTIONS.map((item, i) => {
            const isOpen = open === i;
            return (
              <Card key={i} style={{ padding: 0, overflow: 'hidden' }}>
                <button onClick={() => setOpen(isOpen ? -1 : i)} style={{ width: '100%', display: 'flex', alignItems: 'flex-start', gap: 13, padding: 16, background: 'none', border: 'none', cursor: 'pointer', textAlign: 'left' }}>
                  <span style={{ fontFamily: HT.mono, fontSize: 13, fontWeight: 700, color: HT.muted }}>{String(i + 1).padStart(2, '0')}</span>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontSize: 14, fontWeight: 600, color: HT.text }}>{item.q}</div>
                    <Chip color={HT.purple} bg={HT.purpleSoft} style={{ marginTop: 8 }}>{item.cat}</Chip>
                  </div>
                  <Icon name="chevronR" size={16} color={HT.muted} style={{ transform: isOpen ? 'rotate(90deg)' : 'none', marginTop: 2 }} />
                </button>
                {isOpen && (
                  <div style={{ padding: '0 16px 16px 46px' }}>
                    <div style={{ padding: 14, borderRadius: 11, background: HT.s2, borderLeft: `2px solid ${HT.success}` }}>
                      <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: '0.05em', color: HT.success, marginBottom: 6 }}>STAR ANSWER · from your story bank</div>
                      <p style={{ margin: 0, fontSize: 13, lineHeight: 1.6, color: HT.dim }}>At a UK bank I led a 14-month migration of 40+ services to a hybrid landing zone — cut release time 60% and passed audit with zero findings. Frame the situation, your architecture decisions, the team you aligned, and the measurable result.</p>
                    </div>
                  </div>
                )}
              </Card>
            );
          })}
        </div>
      </div>
    </div>
  );
}

// ── REVIEW modal ──────────────────────────────────────────────────────────────
function DDimBar({ label, val }) {
  const c = val >= 0.85 ? HT.success : val >= 0.7 ? HT.accent : HT.warning;
  return (
    <div style={{ flex: 1 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 5 }}>
        <span style={{ fontSize: 11, color: HT.muted, fontWeight: 600 }}>{label}</span>
        <span style={{ fontSize: 11, color: HT.dim, fontFamily: HT.mono, fontWeight: 700 }}>{Math.round(val * 100)}</span>
      </div>
      <div style={{ height: 5, borderRadius: 999, background: HT.s2, overflow: 'hidden' }}><div style={{ width: `${val * 100}%`, height: '100%', background: c }} /></div>
    </div>
  );
}

function DReview({ t, queue, idx, items, onAct, onClose }) {
  const [tab, setTab] = useState('cv');
  const it = items.find((x) => x.id === queue[idx]) || {};
  const dims = { Skills: 0.92, Experience: 0.85, Rate: 0.9, Location: 0.8 };
  return (
    <div onClick={onClose} style={{ position: 'fixed', inset: 0, zIndex: 90, background: 'rgba(5,5,8,0.7)', backdropFilter: 'blur(4px)', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 40, animation: 'ovRise .18s ease-out' }}>
      <div onClick={(e) => e.stopPropagation()} style={{ width: 920, maxWidth: '100%', maxHeight: '90vh', background: HT.bg, border: `1px solid ${HT.borderStrong}`, borderRadius: 20, display: 'flex', flexDirection: 'column', overflow: 'hidden', boxShadow: '0 30px 80px rgba(0,0,0,0.6)' }}>
        {/* header */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '18px 24px', borderBottom: `1px solid ${HT.border}` }}>
          <div>
            <div style={{ fontSize: 20, fontWeight: 700, color: HT.text }}>{it.title}</div>
            <div style={{ fontSize: 13, color: HT.dim, marginTop: 2 }}>{it.company} · {it.loc} · <span style={{ color: HT.text, fontWeight: 600 }}>{it.rate}</span></div>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
            <span style={{ fontSize: 12.5, color: HT.muted }}>Application {idx + 1} of {queue.length}</span>
            <button onClick={onClose} style={{ width: 34, height: 34, borderRadius: 10, display: 'flex', alignItems: 'center', justifyContent: 'center', background: HT.surface, border: `1px solid ${HT.border}`, cursor: 'pointer' }}><Icon name="x" size={16} color={HT.dim} /></button>
          </div>
        </div>

        {/* body — 2 col */}
        <div style={{ flex: 1, display: 'grid', gridTemplateColumns: '1fr 1.1fr', minHeight: 0 }}>
          {/* left: score + why */}
          <div style={{ padding: 24, borderRight: `1px solid ${HT.border}`, overflow: 'auto' }}>
            <Card style={{ padding: 18 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 14, marginBottom: 16 }}>
                <ScorePill score={it.score} size="lg" />
                <div>
                  <div style={{ fontSize: 14, fontWeight: 700, color: HT.text }}>{it.score >= 0.9 ? 'Excellent match' : 'Strong match'}</div>
                  <div style={{ fontSize: 12, color: HT.muted }}>Scored by Scorer · 4 dimensions</div>
                </div>
              </div>
              <div style={{ display: 'flex', gap: 14 }}>{Object.entries(dims).map(([k, v]) => <DDimBar key={k} label={k} val={v} />)}</div>
            </Card>
            <div style={{ fontSize: 12.5, fontWeight: 700, color: HT.text, margin: '20px 0 10px' }}>Why you're a fit</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 9 }}>
              {['8 of 10 must-have skills matched', 'Day rate within your £600–700 target', 'Hybrid London — inside your commute radius'].map((r) => (
                <div key={r} style={{ display: 'flex', gap: 10, alignItems: 'flex-start' }}>
                  <Icon name="checkCircle" size={16} color={HT.success} style={{ marginTop: 1 }} />
                  <span style={{ fontSize: 12.5, color: HT.dim, lineHeight: 1.45 }}>{r}</span>
                </div>
              ))}
            </div>
            <div style={{ display: 'flex', gap: 10, alignItems: 'flex-start', marginTop: 20, padding: 13, borderRadius: 12, background: HT.accentSoft }}>
              <Icon name="arrowR" size={15} color={HT.accent} style={{ marginTop: 1 }} />
              <span style={{ fontSize: 12, color: HT.dim, lineHeight: 1.5 }}>Approve → moves to <strong style={{ color: HT.text }}>Applied</strong>. Mark an interview and <strong style={{ color: HT.warning }}>Coach</strong> preps automatically.</span>
            </div>
          </div>

          {/* right: docs */}
          <div style={{ padding: 24, overflow: 'auto', background: HT.bgEl }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}><AgentBadge agent="tailor" size={26} /><span style={{ fontSize: 13, fontWeight: 700, color: HT.text }}>Tailored by Tailor</span></div>
              <Chip color={HT.success} bg={HT.successSoft} icon="checkCircle">ATS {it.ats}%</Chip>
            </div>
            <div style={{ display: 'flex', gap: 7, marginBottom: 12 }}>
              {[['cv', 'CV'], ['cl', 'Cover letter']].map(([k, l]) => (
                <button key={k} onClick={() => setTab(k)} style={{ flex: 1, padding: 9, borderRadius: 9, cursor: 'pointer', fontSize: 13, fontWeight: tab === k ? 700 : 600, background: tab === k ? HT.accentSoft : HT.surface, color: tab === k ? HT.accent : HT.dim, border: `1px solid ${tab === k ? 'transparent' : HT.border}` }}>{l}</button>
              ))}
            </div>
            <div style={{ background: '#f7f7f4', borderRadius: 12, padding: 22, display: 'flex', flexDirection: 'column', gap: 11 }}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                <div style={{ height: 12, width: '46%', borderRadius: 3, background: '#2a2a30' }} />
                <div style={{ height: 6, width: '64%', borderRadius: 3, background: '#bcbcc4' }} />
              </div>
              <div style={{ height: 1, background: '#e2e2dc' }} />
              {(tab === 'cv'
                ? [['Profile', ['92%', '88%', '70%']], ['Experience', ['96%', '82%', '90%', '60%']], ['Skills', ['78%', '85%']]]
                : [['Dear Hiring Manager', ['90%', '84%', '74%', '88%']], ['', ['80%', '92%', '64%', '70%']]]
              ).map(([h, ws], hi) => (
                <div key={hi} style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                  {h && <div style={{ height: 7, width: h.length > 12 ? 150 : 80, borderRadius: 3, background: HT.accent }} />}
                  {ws.map((w, i) => <div key={i} style={{ height: 5, width: w, borderRadius: 3, background: '#d2d2cb' }} />)}
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* footer */}
        <div style={{ display: 'flex', gap: 12, padding: '16px 24px', borderTop: `1px solid ${HT.border}`, background: HT.bgEl }}>
          <Btn kind="ghost" icon="x" onClick={() => onAct('reject')}>Reject</Btn>
          <div style={{ flex: 1 }} />
          <Btn kind="soft" icon="fileText">Edit CV</Btn>
          <Btn kind="primary" iconR="send" onClick={() => onAct('approve')}>Approve &amp; apply</Btn>
        </div>
      </div>
    </div>
  );
}

function DToast({ msg }) {
  return (
    <div style={{ position: 'fixed', left: '50%', bottom: 28, transform: 'translateX(-50%)', zIndex: 95, display: 'flex', alignItems: 'center', gap: 11, padding: '13px 18px', borderRadius: 12, background: HT.s3, border: `1px solid ${HT.borderStrong}`, boxShadow: '0 14px 36px rgba(0,0,0,0.5)', animation: 'tRise .22s ease-out' }}>
      <span style={{ width: 22, height: 22, borderRadius: 999, background: HT.successSoft, display: 'flex', alignItems: 'center', justifyContent: 'center' }}><Icon name="check" size={13} color={HT.success} /></span>
      <span style={{ fontSize: 13, color: HT.text, fontWeight: 500 }}>{msg}</span>
    </div>
  );
}

// ── DesktopApp ────────────────────────────────────────────────────────────────
function DesktopApp({ t }) {
  const [tab, setTab] = useState('today');
  const [items, setItems] = useState(D_SEED);
  const [review, setReview] = useState(null);
  const [toast, setToast] = useState(null);
  const tRef = useRef();
  const showToast = (m) => { setToast(m); clearTimeout(tRef.current); tRef.current = setTimeout(() => setToast(null), 2600); };

  const approve = (id) => { setItems((xs) => xs.map((x) => x.id === id ? { ...x, state: 'applied' } : x)); showToast('Applied · moved to Tracker → Applied'); };
  const reject = (id) => { setItems((xs) => xs.map((x) => x.id === id ? { ...x, state: 'rejected' } : x)); showToast('Dismissed'); };
  const openReview = (ids) => ids.length && setReview({ queue: ids, idx: 0 });
  const reviewAct = (act) => {
    const cur = review.queue[review.idx];
    act === 'approve' ? approve(cur) : reject(cur);
    const ni = review.idx + 1;
    ni >= review.queue.length ? setReview(null) : setReview({ ...review, idx: ni });
  };

  const ready = items.filter((x) => x.state === 'ready').length;
  const badges = { today: ready + 2, stream: items.filter((x) => !['applied', 'rejected'].includes(x.state)).length, track: 0, prep: 1 };
  const titles = {
    today: ['Good morning, Arvind', 'Thursday · 6 June — here\'s what your agents did overnight'],
    stream: ['Stream', 'Every role, every stage of the pipeline'],
    track: ['Tracker', 'Your applications across the funnel'],
    prep: ['Prep', 'AI mock-interview coaching by Coach'],
  };

  return (
    <div style={{ position: 'absolute', inset: 0, display: 'flex', background: HT.bg, color: HT.text, fontFamily: HT.font, letterSpacing: '-0.005em' }}>
      <Sidebar active={tab} onNav={setTab} badges={badges} />
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
        <TopBar title={titles[tab][0]} sub={titles[tab][1]} />
        {tab === 'today' && <DToday t={t} items={items} onReview={openReview} onNav={setTab} />}
        {tab === 'stream' && <DStream items={items} onReview={openReview} onApprove={approve} />}
        {tab === 'track' && <DTracker items={items} />}
        {tab === 'prep' && <DPrep />}
      </div>
      {review && <DReview t={t} queue={review.queue} idx={review.idx} items={items} onAct={reviewAct} onClose={() => setReview(null)} />}
      {toast && <DToast msg={toast} />}
    </div>
  );
}

Object.assign(window, { DesktopApp, applyAccentD: (typeof applyAccent !== 'undefined' ? applyAccent : null) });

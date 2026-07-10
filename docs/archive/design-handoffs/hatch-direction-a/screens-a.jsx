// screens-a.jsx — Direction A "The Briefing" (faithful evolution of dark Hatch)
// Uses primitives from hatch-ui.jsx (global identifiers).

// ── Shared bits ───────────────────────────────────────────────────────────────
function TopBar({ title, sub, right }) {
  return (
    <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', paddingTop: 8, paddingBottom: 14 }}>
      <div>
        <div style={{ fontSize: 26, fontWeight: 700, letterSpacing: '-0.03em', color: HT.text }}>{title}</div>
        {sub && <div style={{ fontSize: 12.5, color: HT.muted, marginTop: 2 }}>{sub}</div>}
      </div>
      {right}
    </div>
  );
}

function BellAvatar() {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
      <div style={{ position: 'relative' }}>
        <Icon name="bell" size={20} color={HT.dim} />
        <span style={{ position: 'absolute', top: -2, right: -2, width: 7, height: 7, borderRadius: 999, background: HT.danger, border: `1.5px solid ${HT.bg}` }} />
      </div>
      <UserAvatar size={32} />
    </div>
  );
}

// Funnel node used in the briefing card
function FunnelStep({ agent, count, last }) {
  const a = AGENTS[agent];
  return (
    <React.Fragment>
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 5, flex: 1 }}>
        <AgentBadge agent={agent} size={34} />
        <div style={{ fontFamily: HT.mono, fontSize: 18, fontWeight: 700, color: HT.text, lineHeight: 1 }}>{count}</div>
        <div style={{ fontSize: 10, fontWeight: 600, color: a.color }}>{a.name}</div>
      </div>
      {!last && (
        <div style={{ display: 'flex', alignItems: 'center', paddingBottom: 28, color: HT.muted }}>
          <Icon name="chevronR" size={14} color={HT.borderStrong} sw={2.5} />
        </div>
      )}
    </React.Fragment>
  );
}

// ── A1 · Today cockpit ────────────────────────────────────────────────────────
function ScreenA_Today() {
  return (
    <Screen scroll tabBar={<TabBar active="today" variant="a" />}>
      <TopBar title="Today" sub="Thursday · 5 June" right={<BellAvatar />} />

      {/* Briefing card — the agent speaks */}
      <Card style={{ padding: 16, marginBottom: 18 }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
            <Dot color={HT.success} size={8} pulse />
            <span style={{ fontSize: 12.5, fontWeight: 600, color: HT.text }}>Agents active</span>
          </div>
          <span style={{ fontSize: 11, color: HT.muted }}>last run 3h ago</span>
        </div>
        <p style={{ margin: 0, fontSize: 14.5, lineHeight: 1.55, color: HT.dim }}>
          Overnight I moved <strong style={{ color: HT.text }}>75 new roles</strong> down the pipeline.
          {' '}<strong style={{ color: HT.success }}>3 are tailored</strong> and waiting on your call.
        </p>
        {/* mini funnel */}
        <div style={{ display: 'flex', alignItems: 'flex-start', marginTop: 16, padding: '4px 2px 0' }}>
          <FunnelStep agent="scout" count={75} />
          <FunnelStep agent="scorer" count={12} />
          <FunnelStep agent="tailor" count={3} />
          <FunnelStep agent="coach" count={1} last />
        </div>
      </Card>

      {/* Needs you */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
        <span style={{ fontSize: 13, fontWeight: 700, color: HT.text, letterSpacing: '0.01em', whiteSpace: 'nowrap' }}>Needs you</span>
        <Chip color={HT.accent} bg={HT.accentSoft}>3</Chip>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        {/* Action 1 — approve (highlighted) */}
        <Card accent style={{ padding: 15 }}>
          <div style={{ display: 'flex', gap: 11, marginBottom: 12 }}>
            <AgentBadge agent="tailor" size={34} ring />
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 15, fontWeight: 700, color: HT.text }}>3 applications ready to send</div>
              <div style={{ fontSize: 12, color: HT.muted, marginTop: 1 }}>Tailor drafted a CV + cover letter for each</div>
            </div>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginBottom: 13 }}>
            {[['Solutions Architect', 'Hays', 1.0], ['Technical Architect', 'Yolk', 0.86], ['Software Architect', 'BELCAN', 0.93]].map(([t, c, s]) => (
              <div key={t} style={{ display: 'flex', alignItems: 'center', gap: 9, padding: '7px 9px', borderRadius: 9, background: HT.s2 }}>
                <ScorePill score={s} />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 12.5, fontWeight: 600, color: HT.text, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{t}</div>
                  <div style={{ fontSize: 10.5, color: HT.muted }}>{c}</div>
                </div>
                <Chip color={HT.success} bg={HT.successSoft} icon="check">ATS&nbsp;{Math.round(s * 90 + 5)}</Chip>
              </div>
            ))}
          </div>
          <Btn kind="primary" full iconR="arrowR">Review &amp; approve</Btn>
        </Card>

        {/* Action 2 — interview prep */}
        <Card style={{ padding: 15 }}>
          <div style={{ display: 'flex', gap: 11 }}>
            <AgentBadge agent="coach" size={34} />
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 15, fontWeight: 700, color: HT.text, whiteSpace: 'nowrap' }}>Interview Tuesday, 9am</div>
              <div style={{ fontSize: 12, color: HT.dim, marginTop: 3 }}>Solutions Architect · Hays · in 3 days</div>
              <div style={{ fontSize: 12, color: HT.muted, marginTop: 1 }}>Coach prepped 12 questions + STAR answers</div>
              <div style={{ marginTop: 11 }}>
                <Btn kind="soft" size="sm" iconR="arrowR">Review prep</Btn>
              </div>
            </div>
          </div>
        </Card>

        {/* Action 3 — follow ups */}
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

        <div style={{ height: 8 }} />
      </div>
    </Screen>
  );
}

// ── A2 · The Stream ───────────────────────────────────────────────────────────
function StreamCard({ title, company, loc, rate, score, stage, status, statusColor, ready }) {
  return (
    <Card accent={ready} style={{ padding: 14 }}>
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10, marginBottom: 10 }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span style={{ fontSize: 14.5, fontWeight: 700, color: HT.text, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{title}</span>
            <Icon name="externalLink" size={12} color={HT.muted} />
          </div>
          <div style={{ fontSize: 11.5, color: HT.muted, marginTop: 3, display: 'flex', alignItems: 'center', gap: 5, flexWrap: 'wrap' }}>
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 3 }}><Icon name="building" size={11} color={HT.muted} />{company}</span>
            <span>·</span>
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 3 }}><Icon name="mapPin" size={11} color={HT.muted} />{loc}</span>
            {rate && <><span>·</span><span style={{ color: HT.dim, fontWeight: 600 }}>{rate}</span></>}
          </div>
        </div>
        <ScorePill score={score} />
      </div>
      <StageTrack stage={stage} pct={Math.round(score * 100)} />
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginTop: 12 }}>
        <span style={{ fontSize: 11.5, fontWeight: 600, color: statusColor, display: 'inline-flex', alignItems: 'center', gap: 5 }}>
          {ready && <Dot color={statusColor} size={6} pulse />}
          {status}
        </span>
        {ready
          ? <Btn kind="success" size="sm" icon="check">Approve</Btn>
          : <Icon name="chevronR" size={16} color={HT.muted} />}
      </div>
    </Card>
  );
}

function ScreenA_Stream() {
  const filters = [['All', 23, false], ['Ready', 3, true], ['Tailoring', 2, false], ['Scored', 12, false], ['New', 6, false]];
  return (
    <Screen scroll tabBar={<TabBar active="stream" variant="a" />}>
      <TopBar title="Stream" sub="Every role · every stage" right={
        <div style={{ display: 'flex', gap: 10 }}>
          <div style={{ width: 36, height: 36, borderRadius: 10, display: 'flex', alignItems: 'center', justifyContent: 'center', background: HT.surface, border: `1px solid ${HT.border}` }}><Icon name="search" size={17} color={HT.dim} /></div>
          <div style={{ width: 36, height: 36, borderRadius: 10, display: 'flex', alignItems: 'center', justifyContent: 'center', background: HT.surface, border: `1px solid ${HT.border}` }}><Icon name="sliders" size={17} color={HT.dim} /></div>
        </div>
      } />

      {/* stage filter rail */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 14, overflow: 'hidden' }}>
        {filters.map(([label, n, on]) => (
          <span key={label} style={{
            display: 'inline-flex', alignItems: 'center', gap: 6, padding: '7px 12px', borderRadius: 999,
            fontSize: 12.5, fontWeight: 600, whiteSpace: 'nowrap',
            background: on ? HT.accentSoft : HT.surface, color: on ? HT.accent : HT.dim,
            border: `1px solid ${on ? 'transparent' : HT.border}`,
          }}>
            {label}
            <span style={{ fontFamily: HT.mono, fontSize: 11, opacity: 0.8 }}>{n}</span>
          </span>
        ))}
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 11 }}>
        <StreamCard title="Solutions Architect" company="Hays" loc="London" rate="£600–675/day" score={1.0} stage={3} ready status="Ready for your approval" statusColor={HT.success} />
        <StreamCard title="Technical Architect" company="Yolk" loc="Reading" rate="£700–800/day" score={0.86} stage={2} status="Tailor is writing your CV…" statusColor={HT.success} />
        <StreamCard title="Software Architect" company="BELCAN" loc="Newcastle" rate="£70/day" score={0.93} stage={1} status="Scored · queued for Tailor" statusColor={HT.purple} />
        <StreamCard title="Service Architect" company="Involved" loc="London" rate="£600–675/day" score={0.68} stage={1} status="Parked · just below your 75% bar" statusColor={HT.warning} />
        <div style={{ height: 8 }} />
      </div>
    </Screen>
  );
}

// ── A3 · Review (decision gate) ───────────────────────────────────────────────
function DimBar({ label, val }) {
  const c = val >= 0.85 ? HT.success : val >= 0.7 ? HT.accent : HT.warning;
  return (
    <div style={{ flex: 1 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
        <span style={{ fontSize: 10, color: HT.muted, fontWeight: 600 }}>{label}</span>
        <span style={{ fontSize: 10, color: HT.dim, fontFamily: HT.mono, fontWeight: 700 }}>{Math.round(val * 100)}</span>
      </div>
      <div style={{ height: 4, borderRadius: 999, background: HT.s2, overflow: 'hidden' }}>
        <div style={{ width: `${val * 100}%`, height: '100%', background: c, borderRadius: 999 }} />
      </div>
    </div>
  );
}

function DocLine({ w, strong }) {
  return <div style={{ height: strong ? 7 : 5, width: w, borderRadius: 3, background: strong ? HT.s3 : HT.s2 }} />;
}

function ScreenA_Review() {
  return (
    <div style={{ position: 'absolute', inset: 0, background: HT.bg, color: HT.text, fontFamily: HT.font, display: 'flex', flexDirection: 'column' }}>
      <div style={{ height: 56, flexShrink: 0 }} />
      {/* nav row */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0 18px 12px' }}>
        <div style={{ width: 34, height: 34, borderRadius: 10, display: 'flex', alignItems: 'center', justifyContent: 'center', background: HT.surface, border: `1px solid ${HT.border}` }}>
          <Icon name="chevronR" size={17} color={HT.dim} style={{ transform: 'scaleX(-1)' }} />
        </div>
        <span style={{ fontSize: 13, fontWeight: 600, color: HT.dim, whiteSpace: 'nowrap' }}>Application 1 of 3</span>
        <div style={{ width: 34, height: 34, borderRadius: 10, display: 'flex', alignItems: 'center', justifyContent: 'center', background: HT.surface, border: `1px solid ${HT.border}` }}>
          <Icon name="x" size={16} color={HT.dim} />
        </div>
      </div>

      <div style={{ flex: 1, overflow: 'auto', padding: '0 18px' }}>
        {/* job header */}
        <div style={{ fontSize: 22, fontWeight: 700, letterSpacing: '-0.02em', color: HT.text, marginTop: 4 }}>Solutions Architect</div>
        <div style={{ fontSize: 13, color: HT.dim, marginTop: 4, display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
          <span>Hays Specialist Recruitment</span><span>·</span><span>London</span><span>·</span>
          <span style={{ color: HT.text, fontWeight: 600 }}>£600–675/day</span>
        </div>

        {/* score block */}
        <Card style={{ padding: 15, marginTop: 16 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 13, marginBottom: 14 }}>
            <ScorePill score={0.88} size="lg" />
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 13.5, fontWeight: 700, color: HT.text }}>Strong match for you</div>
              <div style={{ fontSize: 11.5, color: HT.muted }}>Scored by Scorer across 4 dimensions</div>
            </div>
          </div>
          <div style={{ display: 'flex', gap: 12 }}>
            <DimBar label="Skills" val={0.92} />
            <DimBar label="Experience" val={0.85} />
            <DimBar label="Rate" val={0.9} />
            <DimBar label="Location" val={0.8} />
          </div>
        </Card>

        {/* tailored docs */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', margin: '18px 0 10px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <AgentBadge agent="tailor" size={26} />
            <span style={{ fontSize: 13, fontWeight: 700, color: HT.text, whiteSpace: 'nowrap' }}>Tailored by Tailor</span>
          </div>
          <Chip color={HT.success} bg={HT.successSoft} icon="checkCircle">ATS 90%</Chip>
        </div>

        {/* doc tabs */}
        <div style={{ display: 'flex', gap: 6, marginBottom: 10 }}>
          <span style={{ flex: 1, textAlign: 'center', padding: '8px', borderRadius: 9, fontSize: 12.5, fontWeight: 700, background: HT.accentSoft, color: HT.accent }}>CV</span>
          <span style={{ flex: 1, textAlign: 'center', padding: '8px', borderRadius: 9, fontSize: 12.5, fontWeight: 600, background: HT.surface, color: HT.dim, border: `1px solid ${HT.border}` }}>Cover letter</span>
        </div>

        {/* faux CV preview */}
        <div style={{ background: '#f7f7f4', borderRadius: 12, padding: 18, display: 'flex', flexDirection: 'column', gap: 10 }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
            <div style={{ height: 10, width: '46%', borderRadius: 3, background: '#2a2a30' }} />
            <div style={{ height: 5, width: '64%', borderRadius: 3, background: '#bcbcc4' }} />
          </div>
          <div style={{ height: 1, background: '#e2e2dc' }} />
          {[['Profile', ['92%', '88%', '70%']], ['Experience', ['96%', '82%', '90%', '60%']], ['Skills', ['78%', '85%']]].map(([h, ws]) => (
            <div key={h} style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
              <div style={{ height: 6, width: 70, borderRadius: 3, background: '#5b9bff' }} />
              {ws.map((w, i) => <div key={i} style={{ height: 4.5, width: w, borderRadius: 3, background: '#d2d2cb' }} />)}
            </div>
          ))}
        </div>

        {/* what's next */}
        <div style={{ display: 'flex', gap: 9, alignItems: 'flex-start', margin: '16px 0 18px', padding: 12, borderRadius: 12, background: HT.accentSoft }}>
          <Icon name="arrowR" size={16} color={HT.accent} style={{ marginTop: 1 }} />
          <span style={{ fontSize: 12, color: HT.dim, lineHeight: 1.5 }}>
            Approve and it moves to <strong style={{ color: HT.text }}>Applied</strong>. The moment you mark an interview, <strong style={{ color: HT.warning }}>Coach</strong> starts prepping automatically.
          </span>
        </div>
      </div>

      {/* sticky action bar */}
      <div style={{ flexShrink: 0, display: 'flex', gap: 10, padding: '12px 18px', borderTop: `1px solid ${HT.border}`, background: HT.bgEl }}>
        <Btn kind="ghost" style={{ flex: '0 0 auto', padding: '11px 18px' }} icon="x">Reject</Btn>
        <Btn kind="primary" style={{ flex: 1 }} iconR="send">Approve &amp; apply</Btn>
      </div>
      <div style={{ height: 30, flexShrink: 0 }} />
    </div>
  );
}

Object.assign(window, { ScreenA_Today, ScreenA_Stream, ScreenA_Review });

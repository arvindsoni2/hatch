// screens-b.jsx — Direction B "Mission Control" (bolder reimagining)
// The pipeline is drawn as one continuous living spine; agents speak in a feed.

// ── B1 · Pipeline spine ───────────────────────────────────────────────────────
function Station({ agent, headline, sub, count, cta, ctaColor, needsYou, transit, nextColor, nextName, first, last }) {
  const a = AGENTS[agent];
  return (
    <div style={{ display: 'flex', gap: 14, position: 'relative' }}>
      {/* rail */}
      <div style={{ position: 'relative', width: 46, flexShrink: 0 }}>
        {/* line below node toward next station */}
        {!last && (
          <div style={{ position: 'absolute', left: 22, top: 24, bottom: -22, width: 3, borderRadius: 2,
            background: `linear-gradient(${a.color}, ${nextColor})`, opacity: 0.4 }} />
        )}
        {/* transit beads on the line */}
        {!last && transit != null && (
          <div style={{ position: 'absolute', left: 14, top: 60, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4 }}>
            {[0, 1, 2].map((i) => <span key={i} style={{ width: 7, height: 7, borderRadius: 999, background: nextColor, opacity: 0.55 - i * 0.12 }} />)}
          </div>
        )}
        {/* node */}
        <div style={{
          position: 'relative', zIndex: 1, width: 46, height: 46, borderRadius: 999,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          background: a.soft, border: `2px solid ${a.color}`,
          boxShadow: needsYou ? `0 0 0 5px ${a.soft}` : 'none',
        }}>
          <Icon name={a.icon} size={21} color={a.color} sw={2.1} />
        </div>
      </div>

      {/* content */}
      <div style={{ flex: 1, paddingBottom: last ? 0 : 26, minWidth: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontSize: 13.5, fontWeight: 700, color: a.color, letterSpacing: '0.01em' }}>{a.name}</span>
          {count != null && (
            <span style={{ fontFamily: HT.mono, fontSize: 12, fontWeight: 700, color: HT.dim, padding: '1px 7px', borderRadius: 999, background: HT.s2 }}>{count}</span>
          )}
          {needsYou && <Chip color={a.color} bg={a.soft} icon="bell" style={{ marginLeft: 'auto' }}>needs you</Chip>}
        </div>
        <div style={{ fontSize: 14.5, fontWeight: 600, color: HT.text, marginTop: 5 }}>{headline}</div>
        <div style={{ fontSize: 11.5, color: HT.muted, marginTop: 2 }}>{sub}</div>
        {transit != null && transit > 0 && nextName && (
          <div style={{ fontSize: 10.5, color: HT.muted, marginTop: 8, fontStyle: 'italic' }}>↓ {transit} moving to {nextName}</div>
        )}
        {cta && (
          <div style={{ marginTop: 11 }}>
            <Btn kind={ctaColor === HT.success ? 'success' : 'soft'} size="sm" iconR="arrowR">{cta}</Btn>
          </div>
        )}
      </div>
    </div>
  );
}

function ScreenB_Spine() {
  return (
    <Screen scroll tabBar={<TabBar active="stream" variant="b" />}>
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', paddingTop: 8, paddingBottom: 8 }}>
        <div>
          <div style={{ fontSize: 26, fontWeight: 700, letterSpacing: '-0.03em', color: HT.text }}>Pipeline</div>
          <div style={{ fontSize: 12.5, color: HT.muted, marginTop: 2, display: 'flex', alignItems: 'center', gap: 6 }}>
            <Dot color={HT.success} size={7} pulse /> Live · all 4 agents running
          </div>
        </div>
        <UserAvatar size={32} />
      </div>

      {/* hero stat */}
      <Card style={{ padding: '14px 16px', marginBottom: 20, display: 'flex', alignItems: 'center', gap: 14 }}>
        <div style={{ fontFamily: HT.mono, fontSize: 36, fontWeight: 800, color: HT.success, lineHeight: 1 }}>3</div>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 14, fontWeight: 700, color: HT.text }}>roles waiting on you</div>
          <div style={{ fontSize: 11.5, color: HT.muted, marginTop: 1 }}>everything else is moving on its own</div>
        </div>
        <Icon name="chevronR" size={18} color={HT.muted} />
      </Card>

      {/* the spine */}
      <div style={{ paddingLeft: 2 }}>
        <Station agent="scout" headline="75 roles found overnight" sub="6 boards scanned · 3h ago" count="75"
          transit={12} nextColor={AGENTS.scorer.color} nextName="Scorer" first />
        <Station agent="scorer" headline="12 cleared your match bar" sub="ranked on skills, experience, rate, location" count="12"
          transit={3} nextColor={AGENTS.tailor.color} nextName="Tailor" />
        <Station agent="tailor" headline="3 CVs + cover letters drafted" sub="ATS scored 88–92% · ready for your call" count="3"
          needsYou cta="Review & approve" ctaColor={HT.success} transit={1} nextColor={AGENTS.coach.color} nextName="Coach" />
        <Station agent="coach" headline="1 interview prep is ready" sub="Hays · Tuesday 9am · 12 questions" count="1"
          needsYou cta="Open prep" transit={0} nextColor={HT.muted} />

        {/* finish node */}
        <div style={{ display: 'flex', gap: 14 }}>
          <div style={{ width: 46, flexShrink: 0, display: 'flex', justifyContent: 'center' }}>
            <div style={{ width: 46, height: 46, borderRadius: 999, display: 'flex', alignItems: 'center', justifyContent: 'center', background: HT.s2, border: `2px dashed ${HT.borderStrong}` }}>
              <Icon name="target" size={20} color={HT.muted} />
            </div>
          </div>
          <div style={{ flex: 1, paddingTop: 4 }}>
            <div style={{ fontSize: 13.5, fontWeight: 700, color: HT.muted }}>Offer</div>
            <div style={{ fontSize: 13, color: HT.dim, marginTop: 4 }}>The finish line — 2 applications already in flight.</div>
          </div>
        </div>
        <div style={{ height: 10 }} />
      </div>
    </Screen>
  );
}

// ── B2 · Agent feed ───────────────────────────────────────────────────────────
function FeedMsg({ agent, time, children, attach }) {
  const a = AGENTS[agent];
  return (
    <div style={{ display: 'flex', gap: 11, marginBottom: 16 }}>
      <AgentBadge agent={agent} size={34} />
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginBottom: 6 }}>
          <span style={{ fontSize: 13, fontWeight: 700, color: a.color }}>{a.name}</span>
          <span style={{ fontSize: 10.5, color: HT.muted }}>{time}</span>
        </div>
        <div style={{ background: HT.surface, border: `1px solid ${HT.border}`, borderRadius: 14, borderTopLeftRadius: 4, padding: 13 }}>
          <p style={{ margin: 0, fontSize: 13.5, lineHeight: 1.55, color: HT.dim }}>{children}</p>
          {attach}
        </div>
      </div>
    </div>
  );
}

function ScreenB_Feed() {
  return (
    <div style={{ position: 'absolute', inset: 0, background: HT.bg, color: HT.text, fontFamily: HT.font, display: 'flex', flexDirection: 'column' }}>
      <div style={{ height: 56, flexShrink: 0 }} />
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '8px 18px 14px' }}>
        <div>
          <div style={{ fontSize: 26, fontWeight: 700, letterSpacing: '-0.03em', color: HT.text }}>Briefing</div>
          <div style={{ fontSize: 12.5, color: HT.muted, marginTop: 2 }}>Your agents, reporting in</div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: -6 }}>
          {PIPE.map((k, i) => (
            <span key={k} style={{ marginLeft: i ? -8 : 0, borderRadius: 8, border: `2px solid ${HT.bg}` }}>
              <AgentBadge agent={k} size={26} />
            </span>
          ))}
        </div>
      </div>

      <div style={{ flex: 1, overflow: 'auto', padding: '4px 18px 0' }}>
        <div style={{ textAlign: 'center', fontSize: 10.5, color: HT.muted, margin: '2px 0 16px', fontWeight: 600, letterSpacing: '0.04em' }}>TODAY</div>

        <FeedMsg agent="scout" time="6:02am" attach={
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 10 }}>
            {['Reed', 'CWJobs', 'ContractorUK', '+3 boards'].map((s) => (
              <Chip key={s} color={HT.dim} bg={HT.s2}>{s}</Chip>
            ))}
          </div>
        }>
          Good morning. I scanned 6 job boards overnight and found <strong style={{ color: HT.text }}>75 new roles</strong> in your patch.
        </FeedMsg>

        <FeedMsg agent="scorer" time="6:18am" attach={
          <div style={{ display: 'flex', alignItems: 'center', gap: 9, marginTop: 10, padding: '8px 10px', borderRadius: 9, background: HT.s2 }}>
            <ScorePill score={1.0} />
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 12.5, fontWeight: 600, color: HT.text }}>Solutions Architect</div>
              <div style={{ fontSize: 10.5, color: HT.muted }}>Hays · your top match</div>
            </div>
          </div>
        }>
          Ranked all 75. <strong style={{ color: HT.text }}>3 cleared your 75% bar</strong> — the strongest is a 100% match.
        </FeedMsg>

        <FeedMsg agent="tailor" time="7:05am" attach={
          <div style={{ marginTop: 11 }}>
            <Btn kind="success" size="sm" full iconR="arrowR">Review &amp; approve 3</Btn>
          </div>
        }>
          I drafted a tailored CV + cover letter for all 3. ATS scores landed at <strong style={{ color: HT.text }}>88–92%</strong>. They just need your sign-off.
        </FeedMsg>

        <FeedMsg agent="coach" time="9:40am" attach={
          <div style={{ display: 'flex', gap: 8, marginTop: 11 }}>
            <Chip color={HT.warning} bg={HT.warningSoft} icon="calendar">Tue 9:00am</Chip>
            <Btn kind="soft" size="sm" iconR="arrowR" style={{ marginLeft: 'auto' }}>Open prep</Btn>
          </div>
        }>
          Heads up — your <strong style={{ color: HT.text }}>Hays interview is in 3 days</strong>. I've prepped 12 likely questions with STAR answers from your story bank.
        </FeedMsg>
        <div style={{ height: 8 }} />
      </div>

      {/* composer */}
      <div style={{ flexShrink: 0, padding: '10px 18px 12px', borderTop: `1px solid ${HT.border}`, background: HT.bgEl }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '9px 12px 9px 14px', borderRadius: 999, background: HT.surface, border: `1px solid ${HT.border}` }}>
          <Icon name="message" size={16} color={HT.muted} />
          <span style={{ flex: 1, fontSize: 13, color: HT.muted }}>Ask your agents to do something…</span>
          <div style={{ width: 30, height: 30, borderRadius: 999, background: HT.accent, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <Icon name="send" size={15} color="#fff" />
          </div>
        </div>
      </div>
      <div style={{ height: 30, flexShrink: 0 }} />
    </div>
  );
}

// ── B3 · Swipe to approve ─────────────────────────────────────────────────────
function ScreenB_Swipe() {
  return (
    <div style={{ position: 'absolute', inset: 0, background: HT.bg, color: HT.text, fontFamily: HT.font, display: 'flex', flexDirection: 'column' }}>
      <div style={{ height: 56, flexShrink: 0 }} />
      {/* header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '6px 18px 8px' }}>
        <div style={{ width: 34, height: 34, borderRadius: 10, display: 'flex', alignItems: 'center', justifyContent: 'center', background: HT.surface, border: `1px solid ${HT.border}` }}>
          <Icon name="x" size={16} color={HT.dim} />
        </div>
        <div style={{ textAlign: 'center' }}>
          <div style={{ fontSize: 14, fontWeight: 700, color: HT.text }}>Approve applications</div>
          <div style={{ fontSize: 11, color: HT.muted }}>swipe right to send · left to skip</div>
        </div>
        <AgentBadge agent="tailor" size={34} />
      </div>

      {/* progress */}
      <div style={{ display: 'flex', gap: 5, padding: '6px 18px 14px' }}>
        {[1, 0, 0].map((on, i) => (
          <div key={i} style={{ flex: 1, height: 4, borderRadius: 999, background: on ? HT.success : HT.s2 }} />
        ))}
      </div>

      {/* card stack */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', justifyContent: 'center', padding: '0 22px', minHeight: 0 }}>
       <div style={{ position: 'relative' }}>
        {/* back cards peeking below */}
        <div style={{ position: 'absolute', left: 24, right: 24, bottom: -22, height: 60, borderRadius: 20, background: HT.surface, border: `1px solid ${HT.border}`, opacity: 0.35, zIndex: 0 }} />
        <div style={{ position: 'absolute', left: 14, right: 14, bottom: -11, height: 60, borderRadius: 20, background: HT.surface, border: `1px solid ${HT.border}`, opacity: 0.6, zIndex: 0 }} />

        {/* swipe hint tags */}
        <div style={{ position: 'absolute', top: '44%', left: -14, zIndex: 2, transform: 'rotate(-8deg)', display: 'flex', alignItems: 'center', gap: 5, padding: '5px 9px', borderRadius: 8, background: HT.dangerSoft, color: HT.danger, fontSize: 11, fontWeight: 700, border: `1px solid ${HT.danger}` }}>
          <Icon name="x" size={12} color={HT.danger} /> Skip
        </div>
        <div style={{ position: 'absolute', top: '44%', right: -14, zIndex: 2, transform: 'rotate(8deg)', display: 'flex', alignItems: 'center', gap: 5, padding: '5px 9px', borderRadius: 8, background: HT.successSoft, color: HT.success, fontSize: 11, fontWeight: 700, border: `1px solid ${HT.success}` }}>
          Send <Icon name="check" size={12} color={HT.success} />
        </div>

        {/* front card */}
        <div style={{ position: 'relative', zIndex: 1, background: HT.surface, border: `1px solid ${HT.borderStrong}`, borderRadius: 20, padding: 18, boxShadow: '0 16px 40px rgba(0,0,0,0.35)' }}>
          <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 10 }}>
            <div style={{ minWidth: 0 }}>
              <div style={{ fontSize: 18, fontWeight: 700, color: HT.text, letterSpacing: '-0.02em' }}>Solutions Architect</div>
              <div style={{ fontSize: 12, color: HT.muted, marginTop: 3 }}>Hays · London · £600–675/day</div>
            </div>
            <ScorePill score={1.0} size="lg" />
          </div>

          <div style={{ display: 'flex', gap: 7, marginTop: 13 }}>
            <Chip color={HT.success} bg={HT.successSoft} icon="checkCircle">CV tailored</Chip>
            <Chip color={HT.success} bg={HT.successSoft} icon="checkCircle">Cover letter</Chip>
            <Chip color={HT.dim} bg={HT.s2}>ATS 92%</Chip>
          </div>

          {/* faux doc */}
          <div style={{ background: '#f7f7f4', borderRadius: 12, padding: 16, marginTop: 14, display: 'flex', flexDirection: 'column', gap: 8 }}>
            <div style={{ height: 8, width: '44%', borderRadius: 3, background: '#2a2a30' }} />
            <div style={{ height: 5, width: '60%', borderRadius: 3, background: '#bcbcc4' }} />
            <div style={{ height: 1, background: '#e2e2dc', margin: '2px 0' }} />
            {['90%', '74%', '84%', '58%'].map((w, i) => <div key={i} style={{ height: 4.5, width: w, borderRadius: 3, background: '#d2d2cb' }} />)}
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 14, fontSize: 11.5, color: HT.muted }}>
            <Icon name="user" size={13} color={HT.muted} />
            Why you: 8 of 10 must-have skills matched
          </div>
        </div>
       </div>
      </div>

      {/* action buttons */}
      <div style={{ flexShrink: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 22, padding: '14px 0 16px' }}>
        <div style={{ width: 56, height: 56, borderRadius: 999, display: 'flex', alignItems: 'center', justifyContent: 'center', background: HT.surface, border: `1.5px solid ${HT.border}` }}>
          <Icon name="x" size={24} color={HT.danger} />
        </div>
        <div style={{ width: 46, height: 46, borderRadius: 999, display: 'flex', alignItems: 'center', justifyContent: 'center', background: HT.surface, border: `1.5px solid ${HT.border}` }}>
          <Icon name="fileText" size={18} color={HT.dim} />
        </div>
        <div style={{ width: 64, height: 64, borderRadius: 999, display: 'flex', alignItems: 'center', justifyContent: 'center', background: HT.success, boxShadow: `0 8px 24px ${HT.successSoft}` }}>
          <Icon name="send" size={26} color="#06231a" />
        </div>
      </div>
      <div style={{ height: 30, flexShrink: 0 }} />
    </div>
  );
}

Object.assign(window, { ScreenB_Spine, ScreenB_Feed, ScreenB_Swipe });

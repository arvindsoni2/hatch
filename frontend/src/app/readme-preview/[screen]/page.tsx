import { notFound } from "next/navigation";
import { TodayScreen } from "@/components/hatch/screens/TodayScreen";
import { StreamScreen } from "@/components/hatch/screens/StreamScreen";
import { TrackerScreen } from "@/components/hatch/screens/TrackerScreen";
import { PrepScreen } from "@/components/hatch/screens/PrepScreen";
import {
  demoApplications,
  demoCvHighlights,
  demoFunnel,
  demoJobs,
  demoPrepSessions,
  demoProfileName,
  demoWatchedJobs,
} from "@/demo/readmeDemoData";

const SCREENS = new Set([
  "onboarding",
  "today-ready",
  "pipeline",
  "applications",
  "cv-studio",
  "interview-prep",
]);

function PreviewFrame({ screen, children }: { screen: string; children: React.ReactNode }) {
  return (
    <div data-testid={`readme-preview-${screen}`} style={{ minHeight: "calc(100vh - 48px)" }}>
      {children}
    </div>
  );
}

function OnboardingPreview() {
  return (
    <section className="mx-auto grid max-w-5xl gap-8 py-10 lg:grid-cols-[0.95fr_1.05fr]">
      <div>
        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--accent)]">Profile setup</p>
        <h1 className="mt-3 text-3xl font-semibold text-[var(--text)]">Tell Hatch where to focus.</h1>
        <p className="mt-3 max-w-xl text-sm leading-6 text-[var(--text-muted)]">
          The first-run flow captures the market, role titles, compensation, eligibility, CV evidence, and AI preference before any agent work starts.
        </p>
      </div>
      <div className="rounded-[var(--radius-card)] border border-[var(--border)] bg-[var(--surface)] p-5 shadow-[var(--shadow-lg)]">
        <div className="mb-5 flex items-center justify-between">
          <span className="text-sm font-semibold text-[var(--text)]">Your market</span>
          <span className="font-mono text-xs text-[var(--text-muted)]">02 / 06</span>
        </div>
        <label className="block text-sm font-semibold text-[var(--text)]" htmlFor="demo-market">Job market</label>
        <select id="demo-market" className="mt-2 w-full rounded-[var(--radius-control)] border border-[var(--border)] bg-[var(--surface-2)] px-3 py-3 text-sm text-[var(--text)]" defaultValue="uk">
          <option value="uk">United Kingdom</option>
        </select>
        <label className="mt-5 block text-sm font-semibold text-[var(--text)]" htmlFor="demo-roles">Target job titles</label>
        <div id="demo-roles" className="mt-2 flex flex-wrap gap-2 rounded-[var(--radius-control)] border border-[var(--border)] bg-[var(--surface-2)] p-3">
          {["Delivery Lead", "Programme Manager", "Transformation Lead"].map((role) => (
            <span key={role} className="rounded-full bg-[var(--accent-soft)] px-3 py-1.5 text-xs font-semibold text-[var(--accent)]">{role}</span>
          ))}
        </div>
        <div className="mt-5 grid gap-3 sm:grid-cols-3">
          {["Contract", "Permanent", "Either"].map((type) => (
            <button key={type} className="rounded-[var(--radius-control)] border border-[var(--border)] bg-[var(--surface-2)] px-3 py-3 text-sm font-semibold text-[var(--text)]">
              {type}
            </button>
          ))}
        </div>
      </div>
    </section>
  );
}

function CvStudioPreview() {
  return (
    <section className="grid gap-5 py-4 lg:grid-cols-[0.9fr_1.1fr]">
      <div className="rounded-[var(--radius-card)] border border-[var(--border)] bg-[var(--surface)] p-5">
        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--accent)]">CV Studio</p>
        <h1 className="mt-3 text-2xl font-semibold text-[var(--text)]">Evidence-led tailoring</h1>
        <p className="mt-3 text-sm leading-6 text-[var(--text-muted)]">
          Hatch compares the job description with confirmed CV evidence before drafting a reviewable CV and cover letter.
        </p>
        <div className="mt-5 rounded-[var(--radius-control)] bg-[var(--surface-2)] p-4">
          <div className="text-sm font-semibold text-[var(--text)]">{demoCvHighlights.role}</div>
          <div className="mt-1 text-sm text-[var(--text-muted)]">{demoCvHighlights.company}</div>
        </div>
      </div>
      <div className="rounded-[var(--radius-card)] border border-[var(--border)] bg-[var(--surface)] p-5">
        <h2 className="text-base font-semibold text-[var(--text)]">Tailoring review</h2>
        <div className="mt-4 grid gap-4 md:grid-cols-2">
          <div>
            <h3 className="text-sm font-semibold text-[var(--success)]">Matched evidence</h3>
            <ul className="mt-3 space-y-2 text-sm text-[var(--text-muted)]">
              {demoCvHighlights.matchedEvidence.map((item) => <li key={item}>{item}</li>)}
            </ul>
          </div>
          <div>
            <h3 className="text-sm font-semibold text-[var(--warning)]">Unsupported requirements</h3>
            <ul className="mt-3 space-y-2 text-sm text-[var(--text-muted)]">
              {demoCvHighlights.unsupportedRequirements.map((item) => <li key={item}>{item}</li>)}
            </ul>
          </div>
        </div>
        <div className="mt-5 rounded-[var(--radius-control)] border border-[var(--border)] bg-[var(--surface-2)] p-4">
          <div className="text-sm font-semibold text-[var(--text)]">Quality gate</div>
          <p className="mt-1 text-sm text-[var(--text-muted)]">Checks readability, core sections, keyword coverage, and unsupported claims before review.</p>
        </div>
      </div>
    </section>
  );
}

export default async function ReadmePreviewPage({ params }: { params: Promise<{ screen: string }> }) {
  const { screen } = await params;
  if (!SCREENS.has(screen)) notFound();

  if (screen === "onboarding") {
    return <PreviewFrame screen={screen}><OnboardingPreview /></PreviewFrame>;
  }
  if (screen === "today-ready") {
    return (
      <PreviewFrame screen={screen}>
        <TodayScreen jobs={demoJobs} watchedCompanyJobs={demoWatchedJobs} funnel={demoFunnel} profileName={demoProfileName} followUpCount={2} />
      </PreviewFrame>
    );
  }
  if (screen === "pipeline") {
    return <PreviewFrame screen={screen}><StreamScreen jobs={demoJobs} /></PreviewFrame>;
  }
  if (screen === "applications") {
    return <PreviewFrame screen={screen}><TrackerScreen applications={demoApplications} /></PreviewFrame>;
  }
  if (screen === "cv-studio") {
    return <PreviewFrame screen={screen}><CvStudioPreview /></PreviewFrame>;
  }
  if (screen === "interview-prep") {
    return <PreviewFrame screen={screen}><PrepScreen sessions={demoPrepSessions} openSessionId="demo-prep-1" /></PreviewFrame>;
  }
  notFound();
}

import type { HatchJob } from "@/components/hatch/screens/TodayScreen";
import type { ApplicationListItem } from "@/lib/api";
import type { PrepSession } from "@/components/hatch/screens/PrepScreen";

export const demoProfileName = "Mira Patel";

export const demoFunnel = {
  scout: 42,
  scorer: 18,
  tailor: 6,
  coach: 3,
};

export const demoJobs: HatchJob[] = [
  {
    id: "demo-ready-1",
    jobPostingId: "posting-demo-ready-1",
    title: "Platform Delivery Lead",
    company: "Northstar Systems",
    loc: "London, hybrid",
    rate: "GBP 650-760/day",
    score: 0.92,
    state: "ready",
    dims: { Skills: 0.94, Experience: 0.91, Rate: 0.88, Location: 0.95 },
  },
  {
    id: "demo-ready-2",
    jobPostingId: "posting-demo-ready-2",
    title: "Agile Programme Manager",
    company: "HarbourGrid",
    loc: "Manchester, remote",
    rate: "GBP 95k-110k",
    score: 0.87,
    state: "ready",
    dims: { Skills: 0.89, Experience: 0.9, Rate: 0.82, Location: 0.86 },
  },
  {
    id: "demo-tailoring-1",
    title: "Transformation Partner",
    company: "Cedar Loop",
    loc: "Birmingham",
    rate: "GBP 700/day",
    score: 0.81,
    state: "tailoring",
  },
  {
    id: "demo-apply-1",
    title: "Senior Delivery Consultant",
    company: "Blueforge Health",
    loc: "Leeds, hybrid",
    rate: "GBP 88k",
    score: 0.84,
    ats: 78,
    state: "ready_to_apply",
  },
  {
    id: "demo-parked-1",
    title: "Service Improvement Lead",
    company: "Riverbank Digital",
    loc: "Remote",
    rate: "GBP 580/day",
    score: 0.69,
    state: "parked",
  },
];

export const demoWatchedJobs: HatchJob[] = [
  {
    id: "demo-watch-1",
    title: "Portfolio Delivery Lead",
    company: "AtlasWorks",
    loc: "London",
    rate: "GBP 720/day",
    score: 0.79,
    state: "ready",
    source: "watched_company",
  },
];

function app(
  id: string,
  status: ApplicationListItem["status"],
  title: string,
  company: string,
  location: string,
  score: number,
  ats?: number,
): ApplicationListItem {
  return {
    id,
    job_id: `job-${id}`,
    status,
    priority: "normal",
    applied_date: status === "applied" ? "2026-07-08T12:00:00Z" : null,
    recruiter_name: null,
    agency_name: null,
    salary_offered: null,
    is_active: true,
    created_at: "2026-07-01T09:00:00Z",
    updated_at: "2026-07-10T09:00:00Z",
    job_title: title,
    job_company: company,
    job_location: location,
    job_rate_text: "Market aligned",
    job_rate_min: null,
    job_source: "demo",
    job_url: null,
    agent_score: score,
    latest_cv_ats_score: ats ?? null,
    agent_created: true,
    approval_status: "approved",
  };
}

export const demoApplications: ApplicationListItem[] = [
  app("demo-app-saved", "saved", "Operations Strategy Lead", "Pioneer Cloud", "London", 0.72),
  app("demo-app-discovered", "discovered", "Delivery Director", "Nexa Works", "Remote", 0.81),
  app("demo-app-preparing", "preparing", "AI Transformation Lead", "Orbit House", "Bristol", 0.9),
  app("demo-app-ready", "ready_to_apply", "Programme Lead", "Wayline Energy", "Manchester", 0.86, 82),
  app("demo-app-applied", "applied", "Senior Delivery Manager", "Caldera Labs", "Leeds", 0.83, 76),
  app("demo-app-interview", "interview", "Portfolio Coach", "Beacon Mutual", "London", 0.88, 84),
  app("demo-app-offered", "offered", "Head of Delivery", "Foundry Nine", "Edinburgh", 0.91, 89),
  app("demo-app-accepted", "accepted", "Transformation Lead", "North Pier", "London", 0.93, 91),
];

export const demoPrepSessions: PrepSession[] = [
  {
    id: "demo-prep-1",
    title: "Platform Delivery Lead",
    company: "Northstar Systems",
    status: "ready",
    when: "Tomorrow at 10:30",
    createdAt: "2026-07-09T12:00:00Z",
    companyResearch:
      "Northstar Systems is modernising delivery governance across infrastructure programmes. Emphasise stakeholder cadence, measurable delivery health, and pragmatic risk control.",
    questions: [
      {
        q: "Tell me about a programme where delivery risk was high and expectations were unclear.",
        cat: "Behavioural",
        star: "Frame the situation, the governance reset, the measurable leading indicators, and the outcome.",
      },
      {
        q: "How would you balance team autonomy with executive reporting requirements?",
        cat: "Leadership",
      },
      {
        q: "Which delivery metrics would you trust for a platform migration?",
        cat: "Technical",
      },
    ],
  },
  {
    id: "demo-prep-2",
    title: "Agile Programme Manager",
    company: "HarbourGrid",
    status: "ready",
    when: "Friday at 14:00",
    createdAt: "2026-07-08T11:00:00Z",
    questions: [],
  },
];

export const demoCvHighlights = {
  role: "Platform Delivery Lead",
  company: "Northstar Systems",
  matchedEvidence: [
    "Led multi-team platform migration with weekly executive risk reviews",
    "Reduced blocked delivery items by 34 percent over two quarters",
    "Built reusable governance templates for delivery leads",
  ],
  unsupportedRequirements: [
    "Direct Workday implementation ownership",
    "German language fluency",
  ],
};

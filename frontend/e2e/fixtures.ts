/**
 * Shared Playwright fixtures for Job Pilot v2 E2E tests.
 *
 * bypassOnboarding: mocks the profile status API so OnboardingGate does
 * not redirect pages to /onboarding during test runs with no seeded DB.
 *
 * Also mocks other polling endpoints so networkidle doesn't stall.
 */
import { test as base, expect, type Page } from "@playwright/test";

const profile = {
  candidate: {
    name: "Test User",
    title: "Delivery Lead",
    years_experience: 12,
    summary: "Builds reliable delivery systems.",
  },
  locale: "uk",
  search: {
    target_roles: ["Delivery Lead"],
    contract_type: "contract",
    locations: [{ city: "London", country: "GB", remote_preference: "hybrid" }],
  },
  job_boards: [{ name: "LinkedIn", scraper: "linkedin", enabled: true }],
  compensation: { min_rate: 650, max_rate: 800, currency: "GBP", rate_type: "daily" },
  skills: { primary: ["Delivery"], secondary: ["Stakeholder management"] },
  scoring: { shortlist_threshold: 0.75, weights: { skill_match: 0.35 } },
  perception: { face: { enabled: false } },
  llm: { provider: "llamacpp" },
};

const appLockStatus = {
  enabled: false,
  configured_source: "none",
  is_configured: false,
  is_unlocked: true,
  password_policy: {
    min_length: 12,
    max_length: 128,
    require_letter: true,
    require_number: true,
    reject_edge_whitespace: true,
  },
};

export async function bypassOnboarding(page: Page) {
  // App lock — tells AppLockGate to render protected routes in test runs
  await page.route("**/api/app-lock/status", (route) => {
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(appLockStatus),
    });
  });

  // Profile status — tells OnboardingGate not to redirect
  await page.route("**/api/v2/profile/status", (route) => {
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        onboarding_required: false,
        candidate_name: "Test User",
        has_resume: true,
        llm_provider: "openai",
        target_roles: ["Software Engineer"],
      }),
    });
  });

  // Agent performance table polls every 30s — mock so networkidle can settle
  await page.route("**/api/v1/agents/performance", (route) => {
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ agents: [] }),
    });
  });

  // Notifications polling
  await page.route("**/api/v2/notifications**", (route) => {
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([]),
    });
  });
}

export async function mockProtectedRouteApis(page: Page) {
  await bypassOnboarding(page);

  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    const method = route.request().method();

    const json = (body: unknown) => route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(body),
    });

    if (path === "/api/app-lock/status") return json(appLockStatus);
    if (path === "/api/v2/profile/status") {
      return json({
        onboarding_required: false,
        candidate_name: "Test User",
        has_resume: true,
        llm_provider: "llamacpp",
        target_roles: ["Delivery Lead"],
      });
    }
    if (path === "/api/v2/profile" && method === "GET") return json(profile);
    if (path === "/api/v2/profile/summary") {
      return json({
        identity: { name: "Test User", title: "Delivery Lead" },
        target_roles: ["Delivery Lead"],
        skills: ["Delivery"],
        unverified_skills: [],
        domains: ["Technology"],
        certifications: [],
        education: [],
        proof_points: [],
        master_cv: {
          status: "present",
          path: "master-cv.pdf",
          last_validated_at: null,
          last_updated_at: null,
        },
        warnings: [],
      });
    }
    if (path === "/api/jobs") {
      return json({ items: [], total: 0, skip: 0, limit: 50 });
    }
    if (path === "/api/jobs/stats") {
      return json({ total_jobs: 0, by_source: {}, by_ir35: {}, new_today: 0, new_this_week: 0 });
    }
    if (path === "/api/jobs/filter-counts") {
      return json({ sources: {}, ir35_status: {}, job_type: {}, total: 0 });
    }
    if (path === "/api/v2/scoring/insights") {
      return json({
        threshold: 0.75,
        total_scored: 0,
        shortlist_count: 0,
        average_score: null,
        recommendations: [],
      });
    }
    if (path === "/api/agents/approvals/pending") return json([]);
    if (path === "/api/agents/status") {
      return json({
        uptime_seconds: 3600,
        database: "connected",
        agents: [
          { agent_name: "scout", status: "idle", last_run_at: null },
          { agent_name: "scorer", status: "idle", last_run_at: null },
          { agent_name: "tailor", status: "idle", last_run_at: null },
          { agent_name: "coach", status: "idle", last_run_at: null },
        ],
      });
    }
    if (path === "/api/agents/dashboard/pipeline") {
      return json({ discovered: 0, scored: 0, shortlisted: 0, tailored: 0, approved: 0, coach_sessions: 0 });
    }
    if (path === "/api/events") return json({ items: [], total: 0 });
    if (path === "/api/events/activity") return json({ items: [] });
    if (path === "/api/events/costs") return json({ total_cost_usd: 0, by_agent: {}, total_calls: 0 });
    if (path === "/api/debug/llm-traces") return json([]);
    if (path === "/api/debug/runtime-status") {
      return json({
        checked_at: Date.now() / 1000,
        services: [
          { name: "backend", status: "online", detail: "Mocked", latency_ms: 1 },
          { name: "llm-primary", status: "online", detail: "Mocked", latency_ms: 1 },
          { name: "llm-triage", status: "online", detail: "Mocked", latency_ms: 1 },
        ],
      });
    }
    if (path === "/api/interviews/upcoming") return json([]);
    if (path === "/api/interviews/follow-ups/overdue") return json([]);
    if (path === "/api/coach/sessions") return json([]);
    if (path === "/api/coach/capabilities") {
      return json({ face_analysis: false, voice_mode: false, tts: false });
    }
    if (path === "/api/stories") return json({ items: [], total: 0, skip: 0, limit: 20 });
    if (path === "/api/tailor/templates") {
      return json({
        templates: [
          {
            id: "ats_classic",
            name: "ATS Classic",
            description: "Clean, parser-friendly layout.",
          },
        ],
        controls: {
          page_targets: ["one_page", "two_page", "auto"],
          densities: ["standard"],
          section_order_presets: ["standard"],
          accent_colors: ["navy"],
          font_families: ["aptos"],
        },
        default_template_id: "ats_classic",
        default_design_settings: {
          template_id: "ats_classic",
          page_target: "two_page",
          density: "standard",
          section_order_preset: "standard",
          accent_color: "navy",
          font_family: "aptos",
        },
      });
    }
    if (path === "/api/async-jobs") return json([]);
    if (path === "/api/resume/status") {
      return json({
        status: "present",
        path: "master-cv.pdf",
        last_validated_at: null,
        last_updated_at: null,
        warnings: [],
      });
    }
    if (path === "/api/setup/status") {
      return json({
        runtime: { ai_mode: "local", quality_mode: "local", provider: "llamacpp", warnings: [] },
        restart_required: false,
        next_command: "hatch apply-ai-config",
      });
    }
    if (path === "/api/setup/hardware") {
      return json({
        detected: true,
        snapshot: {
          platform: { os_family: "linux", arch: "x86_64" },
          memory: { total_gb: 32 },
          storage: { models_dir_free_gb: 100 },
        },
      });
    }
    if (path === "/api/setup/models/catalog") return json({ models: [] });
    if (path === "/api/setup/models/recommendations") {
      return json({ recommended: [], compatible: [], not_recommended: [] });
    }
    if (path === "/api/v2/locales") return json([]);
    if (path.startsWith("/api/v2/locales/")) return json([]);

    return json({});
  });
}

// Extended test with onboarding bypass and polling mocks applied automatically
export const test = base.extend<{ page: Page }>({
  page: async ({ page }, use) => {
    await bypassOnboarding(page);
    await use(page);
  },
});

export { expect };

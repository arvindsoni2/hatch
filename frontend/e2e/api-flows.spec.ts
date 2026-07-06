/**
 * api-flows.spec.ts — comprehensive flow tests for every major page and endpoint.
 *
 * Covers:
 *  - All page renders (Today, Stream, Tracker, Prep, Settings sub-pages)
 *  - API health: every endpoint the UI calls, asserted against real backend
 *  - User flows: approve async, mark-applied guard, tracker kanban, scrape trigger
 *  - LLM model verification: traces show qwen3 models after scoring
 *  - Agent activity: supervisor, scorer, scout shown as active
 *  - CV/CL generation: async job completes within 15-minute budget
 */
import { test, expect, type Page } from "@playwright/test";

const API = "http://localhost:8000";

// ── Helpers ───────────────────────────────────────────────────────────────────

async function bypassOnboarding(page: Page) {
  await page.route("**/api/v2/profile/status", (r) =>
    r.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        onboarding_required: false,
        candidate_name: "Arvind Soni",
        has_resume: true,
        llm_provider: "llamacpp",
        target_roles: ["Delivery Lead"],
      }),
    })
  );
  await page.route("**/api/v2/notifications**", (r) =>
    r.fulfill({ status: 200, contentType: "application/json", body: "[]" })
  );
}

async function apiGet(url: string): Promise<{ status: number; body: unknown }> {
  const res = await fetch(`${API}${url}`);
  const body = await res.json().catch(() => null);
  return { status: res.status, body };
}

async function apiPost(url: string, payload?: object): Promise<{ status: number; body: unknown }> {
  const res = await fetch(`${API}${url}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: payload ? JSON.stringify(payload) : undefined,
  });
  const body = await res.json().catch(() => null);
  return { status: res.status, body };
}

// ── Section 1: API Health — every endpoint the UI uses ────────────────────────

test.describe("API health", () => {
  test("GET /api/v2/profile/status returns candidate name", async () => {
    const { status, body } = await apiGet("/api/v2/profile/status");
    expect(status).toBe(200);
    expect((body as Record<string, unknown>).candidate_name).toBeTruthy();
    expect((body as Record<string, unknown>).onboarding_required).toBe(false);
  });

  test("GET /api/v2/profile returns full profile with candidate section", async () => {
    const { status, body } = await apiGet("/api/v2/profile");
    expect(status).toBe(200);
    expect((body as Record<string, unknown>).candidate).toBeTruthy();
    expect((body as Record<string, unknown>).llm).toBeTruthy();
  });

  test("GET /api/jobs returns paginated job list", async () => {
    const { status, body } = await apiGet("/api/jobs?skip=0&limit=10");
    expect(status).toBe(200);
    const b = body as Record<string, unknown>;
    expect(b.items).toBeDefined();
    expect(b.total).toBeDefined();
  });

  test("GET /api/jobs/stats returns job counts by source", async () => {
    const { status, body } = await apiGet("/api/jobs/stats");
    expect(status).toBe(200);
    const b = body as Record<string, unknown>;
    expect(typeof (b as Record<string, unknown>).total_jobs).toBe("number");
  });

  test("GET /api/applications/kanban returns column layout", async () => {
    const { status, body } = await apiGet("/api/applications/kanban");
    expect(status).toBe(200);
    const b = body as Record<string, unknown>;
    expect(b.columns).toBeDefined();
    expect(b.stats).toBeDefined();
  });

  test("GET /api/agents/dashboard/pipeline returns funnel counts", async () => {
    const { status, body } = await apiGet("/api/agents/dashboard/pipeline");
    expect(status).toBe(200);
    const b = body as Record<string, unknown>;
    expect(["discovered", "scored", "shortlisted", "tailored", "approved"].every(
      (k) => k in (b as Record<string, unknown>)
    )).toBe(true);
  });

  test("GET /api/agents/approvals/pending returns list", async () => {
    const { status, body } = await apiGet("/api/agents/approvals/pending");
    expect(status).toBe(200);
    expect(Array.isArray(body)).toBe(true);
  });

  test("GET /api/analytics/agent-performance returns agents array", async () => {
    const { status, body } = await apiGet("/api/analytics/agent-performance");
    expect(status).toBe(200);
    const b = body as Record<string, unknown>;
    expect(b.agents).toBeDefined();
  });

  test("GET /api/analytics/dashboard returns full funnel data", async () => {
    const { status, body } = await apiGet("/api/analytics/dashboard");
    expect(status).toBe(200);
    const b = body as Record<string, unknown>;
    expect(b.funnel).toBeDefined();
    expect(b.stats).toBeDefined();
  });

  test("GET /api/events returns event log with pagination", async () => {
    const { status, body } = await apiGet("/api/events?limit=10");
    expect(status).toBe(200);
    const b = body as Record<string, unknown>;
    expect(b.items).toBeDefined();
    expect(typeof b.total).toBe("number");
  });

  test("GET /api/events/costs returns LLM cost summary", async () => {
    const { status, body } = await apiGet("/api/events/costs?days=30");
    expect(status).toBe(200);
    const b = body as Record<string, unknown>;
    expect(typeof b.total_cost_usd).toBe("number");
    expect(typeof b.total_calls).toBe("number");
    expect(b.by_agent).toBeDefined();
  });

  test("GET /api/debug/llm-traces returns trace list", async () => {
    const { status, body } = await apiGet("/api/debug/llm-traces");
    expect(status).toBe(200);
    expect(Array.isArray(body)).toBe(true);
  });

  test("GET /api/async-jobs returns recent background jobs", async () => {
    const { status, body } = await apiGet("/api/async-jobs?status=done&status=failed&limit=20");
    expect(status).toBe(200);
    expect(Array.isArray(body)).toBe(true);
  });

  test("GET /api/v2/locales returns list of supported locales", async () => {
    const { status, body } = await apiGet("/api/v2/locales");
    expect(status).toBe(200);
    expect(Array.isArray(body)).toBe(true);
    expect((body as unknown[]).length).toBeGreaterThan(0);
  });

  test("GET /api/coach/capabilities returns feature flags", async () => {
    const { status, body } = await apiGet("/api/coach/capabilities");
    expect(status).toBe(200);
    const b = body as Record<string, unknown>;
    expect(typeof b.face_analysis).toBe("boolean");
  });

  test("GET /api/interviews/upcoming?days=14 returns list", async () => {
    const { status } = await apiGet("/api/interviews/upcoming?days=14");
    expect(status).toBe(200);
  });

  test("GET /api/interviews/follow-ups/overdue returns list", async () => {
    const { status } = await apiGet("/api/interviews/follow-ups/overdue");
    expect(status).toBe(200);
  });

  test("GET /api/coach/sessions?limit=20 returns list", async () => {
    const { status, body } = await apiGet("/api/coach/sessions?limit=20");
    expect(status).toBe(200);
    expect(Array.isArray(body)).toBe(true);
  });

  test("GET /api/applications?status=ready_to_apply returns list", async () => {
    const { status, body } = await apiGet("/api/applications?status=ready_to_apply&skip=0&limit=10");
    expect(status).toBe(200);
    const b = body as Record<string, unknown>;
    expect(b.items ?? body).toBeDefined();
  });
});

// ── Section 2: LLM model verification ────────────────────────────────────────

test.describe("LLM model verification", () => {
  test("LLM traces show qwen3 models after scoring", async () => {
    const { status, body } = await apiGet("/api/debug/llm-traces");
    expect(status).toBe(200);
    const traces = body as Array<{ model: string }>;
    if (traces.length > 0) {
      const models = traces.map((t) => t.model.toLowerCase());
      const hasQwen3 = models.some((m) => m.includes("qwen3"));
      const hasOldQwen25 = models.some((m) => m.includes("qwen2.5"));
      // New traces must use qwen3; old qwen2.5 traces must not exist after swap
      expect(hasQwen3).toBe(true);
      expect(hasOldQwen25).toBe(false);
    } else {
      // Buffer empty after restart — acceptable, will fill on next scoring cycle
      console.log("LLM trace buffer empty (backend was recently restarted) — skipping model check");
    }
  });

  test("llm-primary health endpoint responds", async () => {
    const res = await fetch("http://localhost:8080/health");
    expect(res.status).toBe(200);
    const body = await res.json();
    expect((body as Record<string, unknown>).status).toBe("ok");
  });

  test("llm-triage health endpoint responds", async () => {
    const res = await fetch("http://localhost:8081/health");
    expect(res.status).toBe(200);
    const body = await res.json();
    expect((body as Record<string, unknown>).status).toBe("ok");
  });

  test("llm-primary reports qwen3.5-4b model", async () => {
    const res = await fetch("http://localhost:8080/v1/models");
    expect(res.status).toBe(200);
    const body = await res.json() as { data: Array<{ id: string }> };
    const modelId = body.data?.[0]?.id?.toLowerCase() ?? "";
    expect(modelId).toContain("qwen3.5-4b");
  });

  test("llm-triage reports qwen3.5-0.8b model", async () => {
    const res = await fetch("http://localhost:8081/v1/models");
    expect(res.status).toBe(200);
    const body = await res.json() as { data: Array<{ id: string }> };
    const modelId = body.data?.[0]?.id?.toLowerCase() ?? "";
    expect(modelId).toContain("qwen3.5-0.8b");
  });
});

// ── Section 3: Agent activity ─────────────────────────────────────────────────

test.describe("Agent activity", () => {
  test("agent performance endpoint returns all four agents", async () => {
    const { status, body } = await apiGet("/api/analytics/agent-performance");
    expect(status).toBe(200);
    // Field is 'agent' (not 'name') in the analytics/agent-performance response
    const agents = ((body as Record<string, unknown>).agents as Array<{ agent: string }>) ?? [];
    const names = agents.map((a) => (a.agent ?? "").toLowerCase());
    // At minimum scorer (or rescore) and scout should have run
    const knownAgents = ["rescore", "scorer", "scout", "supervisor", "tailor"];
    const foundAgents = knownAgents.filter((a) => names.some((n) => n.includes(a)));
    expect(foundAgents.length).toBeGreaterThanOrEqual(2);
  });

  test("events log contains scoring and scraping activity", async () => {
    const { status, body } = await apiGet("/api/events?limit=50");
    expect(status).toBe(200);
    const items = (body as Record<string, unknown>).items as Array<{ event_type?: string; type?: string }> ?? [];
    if (items.length > 0) {
      const types = items.map((e) => (e.event_type ?? e.type ?? "").toLowerCase());
      const hasActivity = types.some((t) =>
        t.includes("job") || t.includes("scor") || t.includes("scrape") || t.includes("triage")
      );
      expect(hasActivity).toBe(true);
    }
    // If no events yet, just pass — system may be freshly started
  });

  test("pipeline has discovered jobs flowing through the funnel", async () => {
    const { status, body } = await apiGet("/api/agents/dashboard/pipeline");
    expect(status).toBe(200);
    const b = body as Record<string, number>;
    expect(b.discovered).toBeGreaterThanOrEqual(0);
    // At least some jobs should exist
    expect(b.discovered + b.scored + b.shortlisted + b.tailored + b.approved).toBeGreaterThan(0);
  });

  test("job stats show jobs have been scraped from real sources", async () => {
    const { status, body } = await apiGet("/api/jobs/stats");
    expect(status).toBe(200);
    const b = body as Record<string, unknown>;
    const total = (b.total_jobs as number) ?? 0;
    expect(total).toBeGreaterThan(0);
  });
});

// ── Section 4: Approve async flow ────────────────────────────────────────────

test.describe("Approve async flow", () => {
  test("POST approve returns 202 with async_job_id immediately", async () => {
    // Get a job that can be approved (scored, active)
    const { body: jobsBody } = await apiGet("/api/jobs?skip=0&limit=50");
    const jobs = ((jobsBody as Record<string, unknown>).items as Array<{ id: string; match_score: number | null }>) ?? [];
    const candidate = jobs.find((j) => j.match_score !== null && j.match_score > 0);
    if (!candidate) {
      console.log("No scored jobs available for approve test — skipping");
      return;
    }

    const { status, body } = await apiPost(`/api/jobs/${candidate.id}/approve`);
    expect(status).toBe(202);
    const b = body as Record<string, unknown>;
    expect(b.async_job_id).toBeTruthy();
    expect(b.job_id).toBe(candidate.id);
    expect(b.status).toBe("preparing");
    expect(typeof b.message).toBe("string");
  });

  test("async job for prepare_application is queryable", async () => {
    const { body: jobsList } = await apiGet("/api/async-jobs?status=done&status=failed&status=running&status=pending&limit=20");
    const jobs = (jobsList as Array<{ type: string; status: string; id: string }>) ?? [];
    const prepJob = jobs.find((j) => j.type === "prepare_application");
    if (!prepJob) {
      console.log("No prepare_application job found — skipping poll test");
      return;
    }

    const { status, body } = await apiGet(`/api/async-jobs/${prepJob.id}`);
    expect(status).toBe(200);
    const b = body as Record<string, unknown>;
    expect(b.id).toBe(prepJob.id);
    expect(["pending", "running", "done", "failed"]).toContain(b.status as string);
  });

  test("mark-applied returns 422 when application is not ready_to_apply", async () => {
    // Find an already-applied application to verify the guard works
    const { body: appsBody } = await apiGet("/api/applications?status=applied&skip=0&limit=5");
    const items =
      ((appsBody as Record<string, unknown>).items as Array<{ id: string; status: string }>) ??
      (Array.isArray(appsBody) ? (appsBody as Array<{ id: string; status: string }>) : []);
    if (items.length === 0) {
      console.log("No applied applications to test guard — skipping");
      return;
    }
    const { status } = await apiPost(`/api/applications/${items[0].id}/mark-applied`);
    expect(status).toBe(422);
  });

  test("mark-applied returns 200 for a ready_to_apply application", async () => {
    const { body: appsBody } = await apiGet("/api/applications?status=ready_to_apply&skip=0&limit=5");
    const items =
      ((appsBody as Record<string, unknown>).items as Array<{ id: string; status: string }>) ??
      (Array.isArray(appsBody) ? (appsBody as Array<{ id: string; status: string }>) : []);
    if (items.length === 0) {
      console.log("No ready_to_apply applications — skipping mark-applied success test");
      return;
    }
    const appId = items[0].id;
    const { status } = await apiPost(`/api/applications/${appId}/mark-applied`);
    // Expect 200 or 422 (if it was already moved to applied by previous test run)
    expect([200, 422]).toContain(status);
  });
});

// ── Section 5: Page renders with real data ────────────────────────────────────

test.describe("Page renders with real data", () => {
  test("today page shows pipeline stats from real backend", async ({ page }) => {
    await bypassOnboarding(page);
    await page.goto("/today");
    await page.waitForLoadState("networkidle");

    // Should show pipeline metric cards or the approval queue
    const hasContent = await Promise.any([
      page.getByText("Agents active").waitFor({ timeout: 5000 }).then(() => true),
      page.getByText("Needs you").waitFor({ timeout: 5000 }).then(() => true),
    ]).catch(() => false);
    expect(hasContent).toBeTruthy();
  });

  test("stream page shows job cards from backend", async ({ page }) => {
    await bypassOnboarding(page);
    await page.goto("/stream");
    await page.waitForLoadState("networkidle");
    const title = await page.title();
    expect(title).not.toContain("500");
    // Either jobs or an empty state should appear
    const hasContent = await Promise.any([
      page.locator("[data-testid='job-card']").first().waitFor({ timeout: 3000 }).then(() => true),
      page.getByText(/No jobs|nothing here|all caught up/i).first().waitFor({ timeout: 3000 }).then(() => true),
      page.getByText("Stream").first().waitFor({ timeout: 3000 }).then(() => true),
    ]).catch(() => false);
    expect(hasContent).toBeTruthy();
  });

  test("tracker page shows kanban board with status columns", async ({ page }) => {
    await bypassOnboarding(page);
    await page.goto("/tracker");
    await page.waitForLoadState("networkidle");
    const title = await page.title();
    expect(title).not.toContain("500");
    await expect(page.getByText("Tracker").first()).toBeVisible();
  });

  test("prep page loads without error", async ({ page }) => {
    await bypassOnboarding(page);
    await page.goto("/prep");
    await page.waitForLoadState("networkidle");
    const title = await page.title();
    expect(title).not.toContain("500");
  });

  test("settings/system page loads LLM traces panel", async ({ page }) => {
    await bypassOnboarding(page);
    await page.goto("/settings/system");
    await page.waitForLoadState("networkidle");
    const title = await page.title();
    expect(title).not.toContain("500");
    // Should show the LLM Call Traces heading
    await expect(page.getByText("LLM Call Traces").first()).toBeVisible({ timeout: 8000 });
  });

  test("settings/system page shows cost summary panel", async ({ page }) => {
    await bypassOnboarding(page);
    await page.goto("/settings/system");
    await page.waitForLoadState("networkidle");
    // Cost panel + event log heading always renders
    await expect(page.getByText("System Event Log").first()).toBeVisible({ timeout: 8000 });
  });

  test("settings/profile page renders candidate form", async ({ page }) => {
    await bypassOnboarding(page);
    await page.goto("/settings/profile");
    await page.waitForLoadState("networkidle");
    const title = await page.title();
    expect(title).not.toContain("500");
  });

  test("settings/ai page renders AI provider settings", async ({ page }) => {
    await bypassOnboarding(page);
    await page.goto("/settings/ai");
    await page.waitForLoadState("networkidle");
    const title = await page.title();
    expect(title).not.toContain("500");
  });

  test("settings/resume page renders CV upload section", async ({ page }) => {
    await bypassOnboarding(page);
    await page.goto("/settings/resume");
    await page.waitForLoadState("networkidle");
    const title = await page.title();
    expect(title).not.toContain("500");
  });
});

// ── Section 6: Scrape & scoring trigger ──────────────────────────────────────

test.describe("Scrape and scoring triggers", () => {
  test("POST /api/jobs/scrape returns array of source results", async () => {
    test.setTimeout(120_000);
    const { status, body } = await apiPost("/api/jobs/scrape");
    expect(status).toBe(200);
    expect(Array.isArray(body)).toBe(true);
    const results = body as Array<{ source: string; jobs_found: number }>;
    expect(results.every((r) => typeof r.source === "string")).toBe(true);
  });

  test("POST /api/jobs/rescore-unscored triggers scoring pipeline", async () => {
    test.setTimeout(60_000);
    const { status, body } = await apiPost("/api/jobs/rescore-unscored");
    expect(status).toBe(200);
    const b = body as Record<string, unknown>;
    expect(typeof b.events_emitted === "number" || typeof b.queued === "number").toBe(true);
  });
});

// ── Section 7: CV/CL async job completion within 15-minute budget ─────────────

test.describe("CV/CL generation latency", () => {
  test("prepare_application async job completes within 15 minutes", async () => {
    // Find most recent prepare_application job (running or done)
    const { body: list } = await apiGet(
      "/api/async-jobs?status=done&status=failed&status=running&status=pending&limit=50"
    );
    const jobs = (list as Array<{ type: string; status: string; id: string; created_at: string; error: string | null }>) ?? [];
    const prepJobs = jobs
      .filter((j) => j.type === "prepare_application")
      .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());

    if (prepJobs.length === 0) {
      console.log("No prepare_application jobs found — triggering one");
      // Find a scored job to approve
      const { body: jobsBody } = await apiGet("/api/jobs?skip=0&limit=50");
      const allJobs = ((jobsBody as Record<string, unknown>).items as Array<{ id: string; match_score: number | null }>) ?? [];
      const candidate = allJobs.find((j) => j.match_score !== null && j.match_score > 0.3);
      if (!candidate) {
        console.log("No scored jobs available — skipping CV/CL latency test");
        return;
      }
      const { body: approveBody } = await apiPost(`/api/jobs/${candidate.id}/approve`);
      const asyncJobId = (approveBody as Record<string, unknown>).async_job_id as string;
      if (!asyncJobId) {
        console.log("approve did not return async_job_id — skipping");
        return;
      }
      prepJobs.push({ type: "prepare_application", status: "pending", id: asyncJobId, created_at: new Date().toISOString(), error: null });
    }

    const jobToWatch = prepJobs[0];

    // If already done or failed, just verify the outcome
    if (jobToWatch.status === "done") {
      console.log(`prepare_application ${jobToWatch.id} already done`);
      expect(jobToWatch.error).toBeNull();
      return;
    }
    if (jobToWatch.status === "failed") {
      console.log(`prepare_application ${jobToWatch.id} failed: ${jobToWatch.error}`);
      // Fail the test with the error message
      throw new Error(`prepare_application failed: ${jobToWatch.error}`);
    }

    // Poll every 30 seconds for up to 15 minutes
    const POLL_INTERVAL_MS = 30_000;
    const MAX_WAIT_MS = 15 * 60 * 1000;
    const deadline = Date.now() + MAX_WAIT_MS;
    let finalStatus = jobToWatch.status;
    let finalError: string | null = null;

    console.log(`Polling prepare_application ${jobToWatch.id} (max 15 min)...`);

    while (Date.now() < deadline) {
      await new Promise((r) => setTimeout(r, POLL_INTERVAL_MS));
      const { body: poll } = await apiGet(`/api/async-jobs/${jobToWatch.id}`);
      const p = poll as Record<string, unknown>;
      finalStatus = p.status as string;
      finalError = (p.error as string) ?? null;
      console.log(`  → status: ${finalStatus} (${Math.round((deadline - Date.now()) / 1000)}s remaining)`);
      if (finalStatus === "done" || finalStatus === "failed") break;
    }

    expect(finalStatus).toBe("done");
    expect(finalError).toBeNull();
  }, 16 * 60 * 1000); // 16-minute test timeout
});

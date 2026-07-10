import { LEGACY_ROUTE_REDIRECTS, PRODUCT_ROUTES } from "./product-routes";

export type RouteCategory =
  | "primary"
  | "advanced"
  | "contextual"
  | "developer"
  | "setup"
  | "legacy_redirect";

export interface ProductRouteTaxonomyEntry {
  path: string;
  label: string;
  category: RouteCategory;
  purpose: string;
  redirectTo?: string;
}

const primaryRoutes: ProductRouteTaxonomyEntry[] = Object.values(PRODUCT_ROUTES).map((route) => ({
  path: route.href,
  label: route.label,
  category: "primary",
  purpose: route.purpose,
}));

export const PRODUCT_ROUTE_TAXONOMY: ProductRouteTaxonomyEntry[] = [
  ...primaryRoutes,
  {
    path: "/today",
    label: "Today",
    category: "primary",
    purpose: "Show the user's highest-priority work for the current job search day.",
  },
  {
    path: "/tailor",
    label: "CV Studio",
    category: "primary",
    purpose: "Review, tailor, and manage generated CV documents.",
  },
  {
    path: "/tracker/watched-companies",
    label: "Watched companies",
    category: "contextual",
    purpose: "Monitor target employers from the Applications workflow.",
  },
  {
    path: "/prep/question-bank",
    label: "Question Bank",
    category: "contextual",
    purpose: "Save, tag, and reuse interview questions and answers from Interview Prep.",
  },
  {
    path: "/jobs/[id]",
    label: "Job detail",
    category: "contextual",
    purpose: "Inspect a discovered role before saving or preparing it.",
  },
  {
    path: "/applications/[id]",
    label: "Application detail",
    category: "contextual",
    purpose: "Review an individual application record.",
  },
  {
    path: "/approvals",
    label: "Approvals",
    category: "contextual",
    purpose: "Review pending generated documents and approval work.",
  },
  {
    path: "/approvals/[id]",
    label: "Approval detail",
    category: "contextual",
    purpose: "Review one pending approval item.",
  },
  {
    path: "/calendar",
    label: "Calendar",
    category: "contextual",
    purpose: "Open interview and follow-up calendar context.",
  },
  {
    path: "/coach/session/[id]",
    label: "Coach session",
    category: "contextual",
    purpose: "Run an interview coaching session.",
  },
  {
    path: "/coach/report/[id]",
    label: "Coach report",
    category: "contextual",
    purpose: "Review feedback from a completed coaching session.",
  },
  {
    path: "/coach/stories",
    label: "Story bank",
    category: "contextual",
    purpose: "Manage reusable interview stories.",
  },
  {
    path: "/coach/stories/[id]",
    label: "Story detail",
    category: "contextual",
    purpose: "Edit a reusable interview story.",
  },
  {
    path: "/coach/stories/new",
    label: "New story",
    category: "contextual",
    purpose: "Create a reusable interview story.",
  },
  {
    path: "/settings",
    label: "Settings",
    category: "advanced",
    purpose: "Manage Hatch workspace preferences and system configuration.",
  },
  {
    path: "/settings/ai",
    label: "AI settings",
    category: "advanced",
    purpose: "Configure local or cloud AI capabilities.",
  },
  {
    path: "/settings/preferences",
    label: "Preferences",
    category: "advanced",
    purpose: "Tune job-search preferences.",
  },
  {
    path: "/settings/profile",
    label: "Profile settings",
    category: "advanced",
    purpose: "Edit the job-search profile used by Hatch.",
  },
  {
    path: "/settings/resume",
    label: "Resume settings",
    category: "advanced",
    purpose: "Manage resume source material.",
  },
  {
    path: "/settings/security",
    label: "Security settings",
    category: "advanced",
    purpose: "Manage local app-lock settings.",
  },
  {
    path: "/settings/system",
    label: "System settings",
    category: "advanced",
    purpose: "Review local system status and diagnostics.",
  },
  {
    path: "/agents",
    label: "Agents",
    category: "developer",
    purpose: "Inspect agent runtime behavior.",
  },
  {
    path: "/analytics",
    label: "Analytics",
    category: "developer",
    purpose: "Inspect job-search analytics and diagnostics.",
  },
  {
    path: "/readme-preview/[screen]",
    label: "README screenshot preview",
    category: "developer",
    purpose: "Render deterministic product screenshots for release docs.",
  },
  {
    path: "/onboarding",
    label: "Onboarding",
    category: "setup",
    purpose: "Set up the local Hatch workspace.",
  },
  {
    path: "/unlock",
    label: "Unlock",
    category: "setup",
    purpose: "Unlock the local Hatch workspace.",
  },
  ...Object.entries(LEGACY_ROUTE_REDIRECTS).map(([path, redirectTo]) => ({
    path,
    label: "Legacy application tracker",
    category: "legacy_redirect" as const,
    purpose: "Redirect older application tracker links to the current Applications board.",
    redirectTo,
  })),
];

export function routeTaxonomyByPath(): Map<string, ProductRouteTaxonomyEntry> {
  return new Map(PRODUCT_ROUTE_TAXONOMY.map((route) => [route.path, route]));
}

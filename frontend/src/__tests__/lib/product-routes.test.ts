import { describe, expect, it } from "vitest";
import {
  LEGACY_ROUTE_REDIRECTS,
  PRODUCT_ROUTES,
} from "@/lib/product-routes";
import {
  PRODUCT_ROUTE_TAXONOMY,
  routeTaxonomyByPath,
} from "@/lib/route-taxonomy";
import { metadata as jobsMetadata } from "@/app/jobs/layout";
import { metadata as pipelineMetadata } from "@/app/stream/layout";
import { metadata as applicationsMetadata } from "@/app/tracker/layout";
import { metadata as interviewPrepMetadata } from "@/app/prep/layout";
import { metadata as interviewCoachMetadata } from "@/app/coach/layout";

describe("product route contract", () => {
  it("assigns a unique path and label to each retained capability", () => {
    const routes = Object.values(PRODUCT_ROUTES);

    expect(new Set(routes.map((route) => route.href)).size).toBe(routes.length);
    expect(new Set(routes.map((route) => route.label)).size).toBe(routes.length);
    expect(routes.every((route) => route.purpose.length > 0)).toBe(true);
  });

  it("retains distinct preparation and live coaching destinations", () => {
    expect(PRODUCT_ROUTES.interviewPrep).toMatchObject({
      href: "/prep",
      label: "Interview Prep",
    });
    expect(PRODUCT_ROUTES.interviewCoach).toMatchObject({
      href: "/coach",
      label: "Interview Coach",
    });
  });

  it("retires the duplicate applications route in favour of the tracker", () => {
    expect(LEGACY_ROUTE_REDIRECTS["/applications"]).toBe(
      PRODUCT_ROUTES.applications.href,
    );
  });

  it("classifies every primary product route in the route taxonomy", () => {
    const taxonomy = routeTaxonomyByPath();

    for (const route of Object.values(PRODUCT_ROUTES)) {
      expect(taxonomy.get(route.href)).toMatchObject({
        category: "primary",
        label: route.label,
      });
    }
  });

  it("keeps advanced, contextual, and developer routes reachable without promoting them to primary navigation", () => {
    const taxonomy = routeTaxonomyByPath();

    expect(taxonomy.get("/tracker/watched-companies")?.category).toBe("contextual");
    expect(taxonomy.get("/prep/question-bank")?.category).toBe("contextual");
    expect(taxonomy.get("/settings/ai")?.category).toBe("advanced");
    expect(taxonomy.get("/agents")?.category).toBe("developer");
    expect(taxonomy.get("/analytics")?.category).toBe("developer");
  });

  it("documents legacy redirects in the same taxonomy as live routes", () => {
    const legacyApplications = PRODUCT_ROUTE_TAXONOMY.find(
      (route) => route.path === "/applications",
    );

    expect(legacyApplications).toMatchObject({
      category: "legacy_redirect",
      redirectTo: PRODUCT_ROUTES.applications.href,
    });
  });

  it.each([
    [jobsMetadata, PRODUCT_ROUTES.jobs],
    [pipelineMetadata, PRODUCT_ROUTES.pipeline],
    [applicationsMetadata, PRODUCT_ROUTES.applications],
    [interviewPrepMetadata, PRODUCT_ROUTES.interviewPrep],
    [interviewCoachMetadata, PRODUCT_ROUTES.interviewCoach],
  ])("uses the route contract for page metadata", (metadata, route) => {
    expect(metadata.title).toBe(`${route.label} | Hatch`);
    expect(metadata.description).toBe(route.purpose);
  });
});

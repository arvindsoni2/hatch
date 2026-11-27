import { NextRequest } from "next/server";
import { afterEach, describe, expect, it, vi } from "vitest";

const DEFAULT_HOSTS = "localhost,127.0.0.1,[::1],backend,frontend";

async function loadMiddleware(
  hosts = DEFAULT_HOSTS,
  token = "boundary-token",
) {
  vi.resetModules();
  vi.stubEnv("HATCH_TRUSTED_HOSTS", hosts);
  vi.stubEnv("HATCH_AUTH_TOKEN", token);
  return await import("@/middleware");
}

function request(url: string, host?: string) {
  return new NextRequest(url, host ? { headers: { host } } : undefined);
}

afterEach(() => {
  vi.unstubAllEnvs();
  vi.resetModules();
});

describe("frontend local boundary middleware", () => {
  it("rejects an untrusted host before adding the bearer token", async () => {
    const { middleware } = await loadMiddleware();

    const response = middleware(
      request("http://evil.example:3000/api/jobs", "evil.example:3000"),
    );

    expect(response.status).toBe(400);
    await expect(response.json()).resolves.toEqual({
      error: { code: "untrusted_host" },
    });
    expect(response.headers.get("x-middleware-request-authorization")).toBeNull();
  });

  it.each([
    "http://localhost:3000/api/jobs",
    "http://127.0.0.1:3000/api/jobs",
    "http://[::1]:3000/api/jobs",
    "http://backend:3000/api/jobs",
    "http://frontend:3000/api/jobs",
  ])("accepts the default trusted host %s", async (url) => {
    const { middleware } = await loadMiddleware();

    const response = middleware(request(url));

    expect(response.status).toBe(200);
    expect(response.headers.get("x-middleware-request-authorization")).toBe(
      "Bearer boundary-token",
    );
  });

  it("rejects an untrusted host on a page request", async () => {
    const { middleware } = await loadMiddleware();

    const response = middleware(request("http://evil.example:3000/"));

    expect(response.status).toBe(400);
  });

  it("rejects a host header containing multiple values", async () => {
    const { middleware } = await loadMiddleware();

    const response = middleware(
      request("http://localhost:3000/api/jobs", "localhost,evil.example"),
    );

    expect(response.status).toBe(400);
  });

  it("accepts a configured extra host", async () => {
    const { middleware } = await loadMiddleware(
      "localhost,127.0.0.1,[::1],backend,frontend,proxy.example",
    );

    const response = middleware(
      request("http://proxy.example:8443/api/jobs", "proxy.example:8443"),
    );

    expect(response.status).toBe(200);
  });

  it("does not inject the bearer token into non-API pages", async () => {
    const { middleware } = await loadMiddleware();

    const response = middleware(request("http://localhost:3000/today"));

    expect(response.status).toBe(200);
    expect(response.headers.get("x-middleware-request-authorization")).toBeNull();
  });

  it("does not inject the bearer token into health checks", async () => {
    const { middleware } = await loadMiddleware();

    const response = middleware(request("http://localhost:3000/api/health"));

    expect(response.status).toBe(200);
    expect(response.headers.get("x-middleware-request-authorization")).toBeNull();
  });
});

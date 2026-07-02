import { beforeEach, describe, expect, it, vi } from "vitest";

const redirectMock = vi.fn();
const cookiesMock = vi.fn();

vi.mock("next/headers", () => ({ cookies: cookiesMock }));
vi.mock("next/navigation", () => ({ redirect: redirectMock }));

describe("serverApiFetch", () => {
  beforeEach(() => {
    vi.resetModules();
    vi.clearAllMocks();
    cookiesMock.mockResolvedValue({
      toString: () => "hatch_app_session=browser-session",
    });
  });

  it("forwards the app-lock cookie to the backend", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ total: 19 }), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const { serverApiFetch } = await import("@/lib/server-api");
    await expect(serverApiFetch<{ total: number }>("/api/jobs")).resolves.toEqual({ total: 19 });

    const [, init] = fetchMock.mock.calls[0];
    expect(new Headers(init.headers).get("cookie")).toBe("hatch_app_session=browser-session");
  });

  it("redirects locked server renders instead of returning empty data", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: "Hatch is locked." }), { status: 423 }),
    ));
    redirectMock.mockImplementation(() => {
      throw new Error("NEXT_REDIRECT");
    });

    const { serverApiFetch } = await import("@/lib/server-api");
    await expect(serverApiFetch("/api/applications/kanban")).rejects.toThrow("NEXT_REDIRECT");
    expect(redirectMock).toHaveBeenCalledWith("/unlock");
  });
});

import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

const DEFAULT_TRUSTED_HOSTS = "localhost,127.0.0.1,[::1],backend,frontend";
const AUTH_TOKEN = process.env.HATCH_AUTH_TOKEN ?? "";

function normalizeHost(value: string): string {
  const host = value.trim().toLowerCase();
  if (!host || /[,\s]/.test(host)) return "";
  if (host.startsWith("[")) {
    const closing = host.indexOf("]");
    if (closing === -1) return "";
    const remainder = host.slice(closing + 1);
    if (remainder && !/^:\d+$/.test(remainder)) return "";
    return host.slice(1, closing);
  }
  if (host.split(":").length === 2) {
    const [name, port] = host.split(":");
    return /^\d+$/.test(port) ? name : "";
  }
  return host;
}

function trustedHosts(): Set<string> {
  return new Set(
    (process.env.HATCH_TRUSTED_HOSTS ?? DEFAULT_TRUSTED_HOSTS)
      .split(",")
      .map(normalizeHost)
      .filter(Boolean),
  );
}

export function middleware(request: NextRequest) {
  const host = request.headers.get("host") ?? request.nextUrl.host;
  if (!trustedHosts().has(normalizeHost(host))) {
    return NextResponse.json(
      { error: { code: "untrusted_host" } },
      { status: 400 },
    );
  }

  if (!AUTH_TOKEN) return NextResponse.next();

  // Only inject on API proxy paths; skip OPTIONS (CORS preflight) and health.
  const { pathname } = request.nextUrl;
  if (
    request.method === "OPTIONS" ||
    pathname === "/api/health" ||
    !pathname.startsWith("/api/")
  ) {
    return NextResponse.next();
  }

  const headers = new Headers(request.headers);
  headers.set("Authorization", `Bearer ${AUTH_TOKEN}`);
  return NextResponse.next({ request: { headers } });
}

export const config = {
  matcher: "/:path*",
};

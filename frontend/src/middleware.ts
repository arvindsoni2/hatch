import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

const AUTH_TOKEN = process.env.HATCH_AUTH_TOKEN ?? "";

export function middleware(request: NextRequest) {
  if (!AUTH_TOKEN) return NextResponse.next();

  // Only inject on API proxy paths; skip OPTIONS (CORS preflight) and health
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
  matcher: "/api/:path*",
};

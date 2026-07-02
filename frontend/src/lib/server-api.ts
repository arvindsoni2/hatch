import { cookies } from "next/headers";
import { redirect } from "next/navigation";

const BACKEND_URL = process.env.API_URL ?? "http://127.0.0.1:8000";
const AUTH_TOKEN = process.env.HATCH_AUTH_TOKEN ?? "";

export async function serverApiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const cookieHeader = (await cookies()).toString();
  const headers = new Headers(init?.headers);
  if (cookieHeader) headers.set("cookie", cookieHeader);
  if (AUTH_TOKEN) headers.set("authorization", `Bearer ${AUTH_TOKEN}`);
  if (init?.body && !(init.body instanceof FormData) && !headers.has("content-type")) {
    headers.set("content-type", "application/json");
  }

  const response = await fetch(`${BACKEND_URL}${path}`, {
    ...init,
    headers,
    cache: init?.cache ?? "no-store",
  });

  if (response.status === 423) {
    redirect("/unlock");
  }
  if (!response.ok) {
    const detail = await response.text().catch(() => response.statusText);
    throw new Error(`API error ${response.status}: ${detail}`);
  }
  return response.json() as Promise<T>;
}

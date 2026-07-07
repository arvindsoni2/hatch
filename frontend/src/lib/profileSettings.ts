import { API_BASE } from "@/lib/api";

export type ProfileSettingsData = Record<string, unknown>;

export async function fetchProfileSettings(): Promise<ProfileSettingsData> {
  const response = await fetch(`${API_BASE}/api/v2/profile`);
  if (!response.ok) throw new Error("Failed to load profile.");
  return response.json() as Promise<ProfileSettingsData>;
}

export async function saveProfileSettings(data: ProfileSettingsData): Promise<void> {
  const response = await fetch(`${API_BASE}/api/v2/profile`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error((body as { detail?: string }).detail || "Save failed.");
  }
}

export function getPathValue<T>(
  source: ProfileSettingsData,
  path: string[],
  fallback: T,
): T {
  let current: unknown = source;
  for (const key of path) {
    if (current == null || typeof current !== "object") return fallback;
    current = (current as Record<string, unknown>)[key];
  }
  return (current ?? fallback) as T;
}

export function updatePathValue(
  source: ProfileSettingsData,
  path: string[],
  value: unknown,
): ProfileSettingsData {
  const next = structuredClone(source);
  let current = next;
  for (let index = 0; index < path.length - 1; index += 1) {
    const key = path[index];
    if (!current[key] || typeof current[key] !== "object") current[key] = {};
    current = current[key] as Record<string, unknown>;
  }
  current[path[path.length - 1]] = value;
  return next;
}

export function firstLocation(profile: ProfileSettingsData): Record<string, unknown> {
  return getPathValue<Array<Record<string, unknown>>>(
    profile,
    ["search", "locations"],
    [{ city: "", country: "", remote_preference: "any" }],
  )[0] ?? { city: "", country: "", remote_preference: "any" };
}

export function updateFirstLocation(
  profile: ProfileSettingsData,
  patch: Record<string, unknown>,
): ProfileSettingsData {
  const locations = structuredClone(getPathValue<Array<Record<string, unknown>>>(
    profile,
    ["search", "locations"],
    [{ city: "", country: "", remote_preference: "any" }],
  ));
  locations[0] = { ...(locations[0] ?? {}), ...patch };
  return updatePathValue(profile, ["search", "locations"], locations);
}

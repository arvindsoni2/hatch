import { redirect } from "next/navigation";
import type { AppLockStatus } from "@/lib/api";
import { serverApiFetch } from "@/lib/server-api";

export default async function RootPage() {
  let status: AppLockStatus | null = null;
  try {
    status = await serverApiFetch<AppLockStatus>("/api/app-lock/status");
  } catch {
    // Preserve the established product entry point when the backend is unavailable.
  }

  if (
    status?.enabled
    && status.configured_source === "none"
    && status.onboarding.status !== "complete"
  ) {
    redirect("/onboarding");
  }
  redirect("/today");
}

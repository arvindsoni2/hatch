import type { KanbanResponse } from "@/lib/api";
import { serverApiFetch } from "@/lib/server-api";
import { TrackerScreen } from "@/components/hatch/screens/TrackerScreen";

export const revalidate = 30;

export default async function TrackerPage() {
  const kanban = await serverApiFetch<KanbanResponse>("/api/applications/kanban");

  return (
    <TrackerScreen
      applications={Object.values(kanban.columns).flat()}
    />
  );
}

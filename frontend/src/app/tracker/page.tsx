import { fetchKanban, type ApplicationListItem } from "@/lib/api";
import { TrackerScreen } from "@/components/hatch/screens/TrackerScreen";

export const revalidate = 30;

export default async function TrackerPage() {
  const kanban = await fetchKanban().catch(() => ({ columns: {} as Record<string, ApplicationListItem[]>, stats: { active_count: 0, applied_count: 0, response_rate: 0, overdue_count: 0 } }));

  return (
    <TrackerScreen
      applications={Object.values(kanban.columns).flat()}
    />
  );
}

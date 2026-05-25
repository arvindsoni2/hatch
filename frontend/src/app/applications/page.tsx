"use client";

import { useState, useEffect, useCallback } from "react";
import { Loader2, Plus } from "lucide-react";
import { KanbanBoard } from "@/components/KanbanBoard";
import { ApplicationDetail } from "@/components/ApplicationDetail";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  fetchKanban,
  fetchFollowUpReminders,
  updateApplicationStatus,
  createApplication,
  type ApplicationListItem,
  type ApplicationStatus,
  type KanbanStats,
} from "@/lib/api";

export default function ApplicationsPage() {
  const [kanbanData, setKanbanData] = useState<Record<string, ApplicationListItem[]>>({});
  const [stats, setStats] = useState<KanbanStats>({
    active_count: 0,
    applied_count: 0,
    response_rate: 0,
    overdue_count: 0,
  });
  const [overdueIds, setOverdueIds] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedAppId, setSelectedAppId] = useState<string | null>(null);
  const [search, setSearch] = useState("");

  const loadKanban = useCallback(async () => {
    try {
      const [response, reminders] = await Promise.all([
        fetchKanban(),
        fetchFollowUpReminders().catch(() => []),
      ]);
      setKanbanData(response.columns);
      setStats(response.stats);
      setOverdueIds(new Set(reminders.filter((r) => r.overdue).map((r) => r.application_id)));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load applications");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadKanban();
  }, [loadKanban]);

  const handleStatusChange = async (id: string, newStatus: ApplicationStatus) => {
    await updateApplicationStatus(id, newStatus);
    await loadKanban();
  };

  const handleNewApplication = async () => {
    const app = await createApplication({ status: "discovered" });
    await loadKanban();
    setSelectedAppId(app.id);
  };

  return (
    <main className="min-h-screen bg-slate-50">
      <div className="max-w-[1400px] mx-auto px-6 py-8">
        {/* Page header */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl font-bold text-slate-900">Applications</h1>
            <p className="text-sm text-slate-500 mt-1">
              Track and manage your contract applications
            </p>
          </div>
          <div className="flex gap-3 items-center">
            <Input
              placeholder="Search..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-48"
            />
            <Button onClick={() => void handleNewApplication()} size="sm">
              <Plus className="h-4 w-4 mr-1" />
              New Application
            </Button>
          </div>
        </div>

        {loading ? (
          <div className="flex items-center justify-center py-24">
            <Loader2 className="h-8 w-8 animate-spin text-indigo-400" />
          </div>
        ) : error ? (
          <div className="text-center py-24">
            <p className="text-red-500 mb-4">{error}</p>
            <Button variant="outline" onClick={() => void loadKanban()}>
              Retry
            </Button>
          </div>
        ) : (
          <KanbanBoard
            initialData={kanbanData}
            stats={stats}
            overdueIds={overdueIds}
            onStatusChange={handleStatusChange}
            onCardClick={(id) => setSelectedAppId(id)}
          />
        )}
      </div>

      {/* Application detail slide-over */}
      {selectedAppId && (
        <ApplicationDetail
          applicationId={selectedAppId}
          onClose={() => setSelectedAppId(null)}
          onStatusChange={loadKanban}
        />
      )}
    </main>
  );
}

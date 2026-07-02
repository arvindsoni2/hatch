import type { SessionFeedbackReport } from "@/lib/api";
import { serverApiFetch } from "@/lib/server-api";
import { FeedbackReport } from "@/components/coach/FeedbackReport";
import { Brain, ArrowLeft } from "lucide-react";
import Link from "next/link";

interface ReportPageProps {
  params: Promise<{ id: string }>;
}

export default async function ReportPage({ params }: ReportPageProps) {
  const { id } = await params;

  const report = await serverApiFetch<SessionFeedbackReport>(`/api/coach/sessions/${id}/report`);

  return (
    <main className="mx-auto max-w-3xl px-4 py-8">
      <div className="mb-6 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Brain className="h-6 w-6 text-indigo-400" />
          <div>
            <h1 className="text-xl font-bold text-slate-100">Session Feedback Report</h1>
            <p className="text-xs text-slate-500">Session ID: {id}</p>
          </div>
        </div>
        <Link
          href="/coach"
          className="flex items-center gap-1.5 text-sm text-slate-400 hover:text-slate-200"
        >
          <ArrowLeft className="h-4 w-4" />
          All Sessions
        </Link>
      </div>

      <FeedbackReport report={report} />
    </main>
  );
}

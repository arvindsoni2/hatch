"use client";

import { useState } from "react";
import { createSession, CreateSessionRequest, type SessionResponse } from "@/lib/api";
import { useAsyncJob } from "@/hooks/useAsyncJob";
import { Button } from "@/components/ui/button";

interface SessionLauncherProps {
  onSessionCreated: (session: SessionResponse) => void;
}

const CATEGORIES = ["Technical", "Behavioural", "Situational", "Domain", "Culture", "Commercial"];

export function SessionLauncher({ onSessionCreated }: SessionLauncherProps) {
  const [step, setStep] = useState<1 | 2 | 3>(1);
  const [companyName, setCompanyName] = useState("");
  const [roleTitle, setRoleTitle] = useState("");
  const [jdText, setJdText] = useState("");
  const [questionCount, setQuestionCount] = useState(10);
  const [difficulty, setDifficulty] = useState<"easy" | "medium" | "hard">("medium");
  const [selectedCategories, setSelectedCategories] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);

  const { state: sessionState, submit: submitSession } = useAsyncJob<SessionResponse>({
    onComplete: (session) => {
      onSessionCreated(session);
    },
    onError: (err) => {
      setError(err);
    },
  });

  const loading = sessionState.status === "pending" || sessionState.status === "running";

  const toggleCategory = (cat: string) => {
    setSelectedCategories((prev) =>
      prev.includes(cat) ? prev.filter((c) => c !== cat) : [...prev, cat]
    );
  };

  const handleStart = async () => {
    if (!companyName.trim() || !roleTitle.trim()) return;
    setError(null);
    const request: CreateSessionRequest = {
      company_name: companyName,
      role_title: roleTitle,
      jd_text: jdText || null,
      config: {
        question_count: questionCount,
        categories: selectedCategories,
        difficulty,
        recording_mode: "text",
      },
    };
    await submitSession(() => createSession(request));
  };

  const inputCls = "w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-800 placeholder:text-slate-400 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500";

  return (
    <div className="mx-auto max-w-lg rounded-xl border border-slate-200 bg-white p-6 shadow-lg">
      <div className="mb-6 flex items-center gap-2">
        {([1, 2, 3] as const).map((s) => (
          <div
            key={s}
            className={`h-2 flex-1 rounded-full transition-colors ${
              s <= step ? "bg-indigo-500" : "bg-slate-200"
            }`}
          />
        ))}
      </div>

      {step === 1 && (
        <div className="space-y-4">
          <h2 className="text-lg font-semibold text-slate-900">Company &amp; Role</h2>
          <div>
            <label className="mb-1 block text-sm font-medium text-slate-600">Company Name</label>
            <input
              type="text"
              value={companyName}
              onChange={(e) => setCompanyName(e.target.value)}
              placeholder="e.g. Accenture"
              className={inputCls}
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-slate-600">Role Title</label>
            <input
              type="text"
              value={roleTitle}
              onChange={(e) => setRoleTitle(e.target.value)}
              placeholder="e.g. Solutions Architect"
              className={inputCls}
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-slate-600">Job Description <span className="font-normal text-slate-400">(optional)</span></label>
            <textarea
              value={jdText}
              onChange={(e) => setJdText(e.target.value)}
              rows={4}
              placeholder="Paste the JD here for tailored questions..."
              className={inputCls + " resize-none"}
            />
          </div>
          <Button
            onClick={() => setStep(2)}
            disabled={!companyName.trim() || !roleTitle.trim()}
            className="w-full bg-indigo-600 hover:bg-indigo-700"
          >
            Next →
          </Button>
        </div>
      )}

      {step === 2 && (
        <div className="space-y-4">
          <h2 className="text-lg font-semibold text-slate-900">Session Configuration</h2>
          <div>
            <label className="mb-2 block text-sm font-medium text-slate-600">
              Questions: <span className="font-semibold text-indigo-600">{questionCount}</span>
            </label>
            <input
              type="range"
              min={3}
              max={20}
              value={questionCount}
              onChange={(e) => setQuestionCount(Number(e.target.value))}
              className="w-full accent-indigo-600"
            />
          </div>
          <div>
            <label className="mb-2 block text-sm font-medium text-slate-600">Difficulty</label>
            <div className="flex gap-2">
              {(["easy", "medium", "hard"] as const).map((d) => (
                <button
                  key={d}
                  onClick={() => setDifficulty(d)}
                  className={`flex-1 rounded-md px-3 py-1.5 text-sm capitalize transition-colors ${
                    difficulty === d
                      ? "bg-indigo-600 text-white"
                      : "bg-slate-100 text-slate-600 hover:bg-slate-200"
                  }`}
                >
                  {d}
                </button>
              ))}
            </div>
          </div>
          <div>
            <label className="mb-2 block text-sm font-medium text-slate-600">Categories <span className="font-normal text-slate-400">(leave blank for all)</span></label>
            <div className="flex flex-wrap gap-2">
              {CATEGORIES.map((cat) => (
                <button
                  key={cat}
                  onClick={() => toggleCategory(cat)}
                  className={`rounded-full px-3 py-1 text-xs transition-colors ${
                    selectedCategories.includes(cat)
                      ? "bg-indigo-600 text-white"
                      : "bg-slate-100 text-slate-600 hover:bg-slate-200"
                  }`}
                >
                  {cat}
                </button>
              ))}
            </div>
          </div>
          <div className="flex gap-2">
            <Button variant="outline" onClick={() => setStep(1)} className="flex-1 text-slate-600">
              ← Back
            </Button>
            <Button onClick={() => setStep(3)} className="flex-1 bg-indigo-600 hover:bg-indigo-700">
              Next →
            </Button>
          </div>
        </div>
      )}

      {step === 3 && (
        <div className="space-y-4">
          <h2 className="text-lg font-semibold text-slate-900">Ready to Start?</h2>
          <div className="rounded-lg bg-slate-50 border border-slate-200 p-4 text-sm text-slate-700 space-y-1">
            <p><span className="font-medium text-slate-500">Company:</span> {companyName}</p>
            <p><span className="font-medium text-slate-500">Role:</span> {roleTitle}</p>
            <p><span className="font-medium text-slate-500">Questions:</span> {questionCount}</p>
            <p><span className="font-medium text-slate-500">Difficulty:</span> {difficulty}</p>
            {selectedCategories.length > 0 && (
              <p><span className="font-medium text-slate-500">Categories:</span> {selectedCategories.join(", ")}</p>
            )}
          </div>
          {error && (
            <p className="rounded-md bg-red-50 border border-red-200 px-3 py-2 text-sm text-red-700">{error}</p>
          )}
          <div className="flex gap-2">
            <Button variant="outline" onClick={() => setStep(2)} className="flex-1 text-slate-600">
              ← Back
            </Button>
            <Button
              onClick={handleStart}
              disabled={loading}
              className="flex-1 bg-indigo-600 hover:bg-indigo-700"
            >
              {loading ? "Generating questions…" : "Start Session"}
            </Button>
          </div>
          {(sessionState.status === "pending" || sessionState.status === "running") && (
            <div className="mt-2 rounded-lg border border-slate-100 bg-slate-50 p-3 text-center">
              <p className="text-xs text-slate-600">
                {sessionState.status === "pending" ? "Queuing your session…" : "Generating your questions — this can take a few minutes."}
              </p>
              <p className="mt-1 text-xs text-slate-400">
                You can navigate away and check the <span className="font-medium text-slate-500">notification bell</span> when your session is ready.
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

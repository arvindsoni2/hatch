"use client";

import { useState } from "react";
import { createSession, CreateSessionRequest, SessionResponse } from "@/lib/api";
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
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const toggleCategory = (cat: string) => {
    setSelectedCategories((prev) =>
      prev.includes(cat) ? prev.filter((c) => c !== cat) : [...prev, cat]
    );
  };

  const handleStart = async () => {
    if (!companyName.trim() || !roleTitle.trim()) return;
    setLoading(true);
    setError(null);
    try {
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
      const session = await createSession(request);
      onSessionCreated(session);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create session");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="mx-auto max-w-lg rounded-xl border border-slate-700 bg-slate-800 p-6">
      <div className="mb-6 flex items-center gap-2">
        {([1, 2, 3] as const).map((s) => (
          <div
            key={s}
            className={`h-2 flex-1 rounded-full transition-colors ${
              s <= step ? "bg-indigo-500" : "bg-slate-600"
            }`}
          />
        ))}
      </div>

      {step === 1 && (
        <div className="space-y-4">
          <h2 className="text-lg font-semibold text-slate-100">Company &amp; Role</h2>
          <div>
            <label className="mb-1 block text-sm text-slate-400">Company Name</label>
            <input
              type="text"
              value={companyName}
              onChange={(e) => setCompanyName(e.target.value)}
              placeholder="e.g. Accenture"
              className="w-full rounded-lg border border-slate-600 bg-slate-700 px-3 py-2 text-sm text-slate-100 placeholder:text-slate-500 focus:border-indigo-500 focus:outline-none"
            />
          </div>
          <div>
            <label className="mb-1 block text-sm text-slate-400">Role Title</label>
            <input
              type="text"
              value={roleTitle}
              onChange={(e) => setRoleTitle(e.target.value)}
              placeholder="e.g. Solutions Architect"
              className="w-full rounded-lg border border-slate-600 bg-slate-700 px-3 py-2 text-sm text-slate-100 placeholder:text-slate-500 focus:border-indigo-500 focus:outline-none"
            />
          </div>
          <div>
            <label className="mb-1 block text-sm text-slate-400">Job Description (optional)</label>
            <textarea
              value={jdText}
              onChange={(e) => setJdText(e.target.value)}
              rows={4}
              placeholder="Paste the JD here for tailored questions..."
              className="w-full rounded-lg border border-slate-600 bg-slate-700 px-3 py-2 text-sm text-slate-100 placeholder:text-slate-500 focus:border-indigo-500 focus:outline-none"
            />
          </div>
          <Button
            onClick={() => setStep(2)}
            disabled={!companyName.trim() || !roleTitle.trim()}
            className="w-full bg-indigo-600 hover:bg-indigo-500"
          >
            Next →
          </Button>
        </div>
      )}

      {step === 2 && (
        <div className="space-y-4">
          <h2 className="text-lg font-semibold text-slate-100">Session Configuration</h2>
          <div>
            <label className="mb-2 block text-sm text-slate-400">
              Questions: <span className="font-semibold text-slate-100">{questionCount}</span>
            </label>
            <input
              type="range"
              min={3}
              max={20}
              value={questionCount}
              onChange={(e) => setQuestionCount(Number(e.target.value))}
              className="w-full accent-indigo-500"
            />
          </div>
          <div>
            <label className="mb-2 block text-sm text-slate-400">Difficulty</label>
            <div className="flex gap-2">
              {(["easy", "medium", "hard"] as const).map((d) => (
                <button
                  key={d}
                  onClick={() => setDifficulty(d)}
                  className={`flex-1 rounded-lg px-3 py-1.5 text-sm capitalize transition-colors ${
                    difficulty === d
                      ? "bg-indigo-600 text-white"
                      : "bg-slate-700 text-slate-400 hover:bg-slate-600"
                  }`}
                >
                  {d}
                </button>
              ))}
            </div>
          </div>
          <div>
            <label className="mb-2 block text-sm text-slate-400">Categories (leave blank for all)</label>
            <div className="flex flex-wrap gap-2">
              {CATEGORIES.map((cat) => (
                <button
                  key={cat}
                  onClick={() => toggleCategory(cat)}
                  className={`rounded-full px-3 py-1 text-xs transition-colors ${
                    selectedCategories.includes(cat)
                      ? "bg-indigo-600 text-white"
                      : "bg-slate-700 text-slate-400 hover:bg-slate-600"
                  }`}
                >
                  {cat}
                </button>
              ))}
            </div>
          </div>
          <div className="flex gap-2">
            <Button
              variant="outline"
              onClick={() => setStep(1)}
              className="flex-1 border-slate-600 text-slate-400"
            >
              ← Back
            </Button>
            <Button onClick={() => setStep(3)} className="flex-1 bg-indigo-600 hover:bg-indigo-500">
              Next →
            </Button>
          </div>
        </div>
      )}

      {step === 3 && (
        <div className="space-y-4">
          <h2 className="text-lg font-semibold text-slate-100">Ready to Start?</h2>
          <div className="rounded-lg bg-slate-700/50 p-4 text-sm text-slate-300 space-y-1">
            <p><span className="text-slate-500">Company:</span> {companyName}</p>
            <p><span className="text-slate-500">Role:</span> {roleTitle}</p>
            <p><span className="text-slate-500">Questions:</span> {questionCount}</p>
            <p><span className="text-slate-500">Difficulty:</span> {difficulty}</p>
            {selectedCategories.length > 0 && (
              <p><span className="text-slate-500">Categories:</span> {selectedCategories.join(", ")}</p>
            )}
          </div>
          {error && (
            <p className="rounded-lg bg-red-900/30 px-3 py-2 text-sm text-red-400">{error}</p>
          )}
          <div className="flex gap-2">
            <Button
              variant="outline"
              onClick={() => setStep(2)}
              className="flex-1 border-slate-600 text-slate-400"
            >
              ← Back
            </Button>
            <Button
              onClick={handleStart}
              disabled={loading}
              className="flex-1 bg-indigo-600 hover:bg-indigo-500"
            >
              {loading ? "Generating questions…" : "Start Session"}
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

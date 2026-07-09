"use client";

import { useState, useTransition } from "react";
import Link from "next/link";
import { ArrowLeft, CopyPlus, Pencil, Plus, Search, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  createQuestionBankItem,
  deleteQuestionBankItem,
  listQuestionBank,
  updateQuestionBankItem,
  type QuestionBankItem,
  type QuestionBankItemType,
  type QuestionBankConfidence,
} from "@/lib/api";

export type { QuestionBankItem } from "@/lib/api";

interface QuestionBankClientProps {
  initialItems: QuestionBankItem[];
  initialTotal: number;
}

interface FormState {
  id?: string;
  type: QuestionBankItemType;
  title: string;
  question: string;
  answerDraft: string;
  situation: string;
  task: string;
  action: string;
  result: string;
  skills: string;
  tags: string;
  seniority: string;
  roleFamily: string;
  confidence: QuestionBankConfidence;
}

const emptyForm: FormState = {
  type: "interview_question",
  title: "",
  question: "",
  answerDraft: "",
  situation: "",
  task: "",
  action: "",
  result: "",
  skills: "",
  tags: "",
  seniority: "",
  roleFamily: "",
  confidence: "draft",
};

function splitCsv(value: string): string[] {
  return value.split(",").map((item) => item.trim()).filter(Boolean);
}

function joinCsv(value: string[] | null | undefined): string {
  return (value ?? []).join(", ");
}

function formFromItem(item: QuestionBankItem): FormState {
  return {
    id: item.id,
    type: item.type as QuestionBankItemType,
    title: item.title,
    question: item.question ?? "",
    answerDraft: item.answer_draft,
    situation: item.situation ?? "",
    task: item.task ?? "",
    action: item.action ?? "",
    result: item.result ?? "",
    skills: joinCsv(item.skills),
    tags: joinCsv(item.tags),
    seniority: item.seniority ?? "",
    roleFamily: item.role_family ?? "",
    confidence: item.confidence as QuestionBankConfidence,
  };
}

function payloadFromForm(form: FormState) {
  return {
    type: form.type,
    title: form.title.trim(),
    question: form.question.trim() || null,
    answer_draft: form.answerDraft.trim(),
    situation: form.situation.trim() || null,
    task: form.task.trim() || null,
    action: form.action.trim() || null,
    result: form.result.trim() || null,
    skills: splitCsv(form.skills),
    tags: splitCsv(form.tags),
    seniority: form.seniority.trim() || null,
    role_family: form.roleFamily.trim() || null,
    source: "manual" as const,
    confidence: form.confidence,
  };
}

export function QuestionBankClient({ initialItems, initialTotal }: QuestionBankClientProps) {
  const [items, setItems] = useState(initialItems);
  const [total, setTotal] = useState(initialTotal);
  const [form, setForm] = useState<FormState>(emptyForm);
  const [showForm, setShowForm] = useState(initialItems.length === 0);
  const [search, setSearch] = useState("");
  const [typeFilter, setTypeFilter] = useState("");
  const [confidenceFilter, setConfidenceFilter] = useState("");
  const [tagFilter, setTagFilter] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  const refresh = async () => {
    const data = await listQuestionBank({
      search: search || undefined,
      type: typeFilter || undefined,
      confidence: confidenceFilter || undefined,
      tag: tagFilter || undefined,
    });
    setItems(data.items);
    setTotal(data.total);
  };

  const applyFilters = () => {
    startTransition(async () => {
      await refresh();
    });
  };

  const save = () => {
    startTransition(async () => {
      setMessage(null);
      try {
        const payload = payloadFromForm(form);
        if (form.id) {
          await updateQuestionBankItem(form.id, payload);
        } else {
          await createQuestionBankItem(payload);
        }
        setForm(emptyForm);
        setShowForm(false);
        await refresh();
        setMessage("Question Bank entry saved.");
      } catch (error) {
        setMessage(error instanceof Error ? error.message : "Could not save Question Bank entry.");
      }
    });
  };

  const edit = (item: QuestionBankItem) => {
    setForm(formFromItem(item));
    setShowForm(true);
  };

  const duplicate = (item: QuestionBankItem) => {
    setForm({ ...formFromItem(item), id: undefined, title: `${item.title} adaptation` });
    setShowForm(true);
  };

  const remove = (item: QuestionBankItem) => {
    startTransition(async () => {
      await deleteQuestionBankItem(item.id);
      await refresh();
      setMessage("Question Bank entry deleted.");
    });
  };

  return (
    <div className="mx-auto max-w-6xl space-y-5">
      <header className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <Link className="mb-3 inline-flex items-center gap-2 text-sm font-semibold text-[var(--accent)]" href="/prep">
            <ArrowLeft className="h-4 w-4" aria-hidden="true" />
            Interview Prep
          </Link>
          <h1 className="text-[28px] font-semibold text-[var(--text)]">Question Bank</h1>
          <p className="mt-1 max-w-2xl text-sm leading-relaxed text-[var(--text-muted)]">
            Reusable answers, STAR stories, proof points, and role notes for interview preparation.
          </p>
        </div>
        <Button disabled={isPending} onClick={() => { setForm(emptyForm); setShowForm(true); }} type="button">
          <Plus className="h-4 w-4" aria-hidden="true" />
          Add entry
        </Button>
      </header>

      <section className="rounded-[var(--radius-card)] border border-[var(--border)] bg-[var(--surface)] p-4">
        <p className="text-sm text-[var(--text-muted)]">Question Bank works in Basic mode without AI.</p>
      </section>

      <section className="grid gap-3 rounded-[var(--radius-card)] border border-[var(--border)] bg-[var(--surface)] p-4 md:grid-cols-5">
        <label className="grid gap-1.5 text-sm font-medium text-[var(--text-muted)] md:col-span-2">
          Search
          <input className="min-h-11 rounded-[var(--radius-control)] border border-[var(--border)] bg-[var(--surface-2)] px-3 text-[var(--text)]" value={search} onChange={(event) => setSearch(event.target.value)} />
        </label>
        <label className="grid gap-1.5 text-sm font-medium text-[var(--text-muted)]">
          Type
          <select className="min-h-11 rounded-[var(--radius-control)] border border-[var(--border)] bg-[var(--surface-2)] px-3 text-[var(--text)]" value={typeFilter} onChange={(event) => setTypeFilter(event.target.value)}>
            <option value="">All</option>
            <option value="interview_question">Question</option>
            <option value="star_story">STAR story</option>
            <option value="proof_point">Proof point</option>
            <option value="company_research_note">Research note</option>
            <option value="role_specific_answer">Role answer</option>
          </select>
        </label>
        <label className="grid gap-1.5 text-sm font-medium text-[var(--text-muted)]">
          Filter confidence
          <select className="min-h-11 rounded-[var(--radius-control)] border border-[var(--border)] bg-[var(--surface-2)] px-3 text-[var(--text)]" value={confidenceFilter} onChange={(event) => setConfidenceFilter(event.target.value)}>
            <option value="">All</option>
            <option value="draft">Draft</option>
            <option value="reviewed">Reviewed</option>
            <option value="final">Final</option>
          </select>
        </label>
        <label className="grid gap-1.5 text-sm font-medium text-[var(--text-muted)]">
          Tag
          <input className="min-h-11 rounded-[var(--radius-control)] border border-[var(--border)] bg-[var(--surface-2)] px-3 text-[var(--text)]" value={tagFilter} onChange={(event) => setTagFilter(event.target.value)} />
        </label>
        <Button className="md:col-start-5" disabled={isPending} onClick={applyFilters} type="button" variant="outline">
          <Search className="h-4 w-4" aria-hidden="true" />
          Apply filters
        </Button>
      </section>

      {message ? <p className="rounded-[var(--radius-control)] bg-[var(--surface-2)] p-3 text-sm text-[var(--text)]" role="status">{message}</p> : null}

      {showForm ? (
        <section className="rounded-[var(--radius-card)] border border-[var(--border)] bg-[var(--surface)] p-5">
          <div className="grid gap-3 md:grid-cols-2">
            <label className="grid gap-1.5 text-sm font-medium text-[var(--text-muted)]">
              Type
              <select className="min-h-11 rounded-[var(--radius-control)] border border-[var(--border)] bg-[var(--surface-2)] px-3 text-[var(--text)]" value={form.type} onChange={(event) => setForm((current) => ({ ...current, type: event.target.value as QuestionBankItemType }))}>
                <option value="interview_question">Interview question</option>
                <option value="star_story">STAR story</option>
                <option value="proof_point">Proof point</option>
                <option value="company_research_note">Company research note</option>
                <option value="role_specific_answer">Role-specific answer</option>
              </select>
            </label>
            <label className="grid gap-1.5 text-sm font-medium text-[var(--text-muted)]">
              Confidence
              <select className="min-h-11 rounded-[var(--radius-control)] border border-[var(--border)] bg-[var(--surface-2)] px-3 text-[var(--text)]" value={form.confidence} onChange={(event) => setForm((current) => ({ ...current, confidence: event.target.value as QuestionBankConfidence }))}>
                <option value="draft">Draft</option>
                <option value="reviewed">Reviewed</option>
                <option value="final">Final</option>
              </select>
            </label>
            <label className="grid gap-1.5 text-sm font-medium text-[var(--text-muted)] md:col-span-2">
              Title
              <input className="min-h-11 rounded-[var(--radius-control)] border border-[var(--border)] bg-[var(--surface-2)] px-3 text-[var(--text)]" value={form.title} onChange={(event) => setForm((current) => ({ ...current, title: event.target.value }))} />
            </label>
            <label className="grid gap-1.5 text-sm font-medium text-[var(--text-muted)] md:col-span-2">
              Question
              <input className="min-h-11 rounded-[var(--radius-control)] border border-[var(--border)] bg-[var(--surface-2)] px-3 text-[var(--text)]" value={form.question} onChange={(event) => setForm((current) => ({ ...current, question: event.target.value }))} />
            </label>
            <label className="grid gap-1.5 text-sm font-medium text-[var(--text-muted)] md:col-span-2">
              Answer draft
              <textarea className="min-h-32 rounded-[var(--radius-control)] border border-[var(--border)] bg-[var(--surface-2)] px-3 py-2 text-[var(--text)]" value={form.answerDraft} onChange={(event) => setForm((current) => ({ ...current, answerDraft: event.target.value }))} />
            </label>
            {(["situation", "task", "action", "result"] as const).map((key) => (
              <label className="grid gap-1.5 text-sm font-medium text-[var(--text-muted)]" key={key}>
                {key[0].toUpperCase() + key.slice(1)}
                <textarea className="min-h-24 rounded-[var(--radius-control)] border border-[var(--border)] bg-[var(--surface-2)] px-3 py-2 text-[var(--text)]" value={form[key]} onChange={(event) => setForm((current) => ({ ...current, [key]: event.target.value }))} />
              </label>
            ))}
            <label className="grid gap-1.5 text-sm font-medium text-[var(--text-muted)]">
              Skills
              <input className="min-h-11 rounded-[var(--radius-control)] border border-[var(--border)] bg-[var(--surface-2)] px-3 text-[var(--text)]" value={form.skills} onChange={(event) => setForm((current) => ({ ...current, skills: event.target.value }))} />
            </label>
            <label className="grid gap-1.5 text-sm font-medium text-[var(--text-muted)]">
              Tags
              <input className="min-h-11 rounded-[var(--radius-control)] border border-[var(--border)] bg-[var(--surface-2)] px-3 text-[var(--text)]" value={form.tags} onChange={(event) => setForm((current) => ({ ...current, tags: event.target.value }))} />
            </label>
            <label className="grid gap-1.5 text-sm font-medium text-[var(--text-muted)]">
              Seniority
              <input className="min-h-11 rounded-[var(--radius-control)] border border-[var(--border)] bg-[var(--surface-2)] px-3 text-[var(--text)]" value={form.seniority} onChange={(event) => setForm((current) => ({ ...current, seniority: event.target.value }))} />
            </label>
            <label className="grid gap-1.5 text-sm font-medium text-[var(--text-muted)]">
              Role family
              <input className="min-h-11 rounded-[var(--radius-control)] border border-[var(--border)] bg-[var(--surface-2)] px-3 text-[var(--text)]" value={form.roleFamily} onChange={(event) => setForm((current) => ({ ...current, roleFamily: event.target.value }))} />
            </label>
          </div>
          <div className="mt-4 flex justify-end gap-2">
            <Button disabled={isPending} onClick={() => { setShowForm(false); setForm(emptyForm); }} type="button" variant="ghost">Cancel</Button>
            <Button disabled={isPending || !form.title.trim() || !form.answerDraft.trim()} onClick={save} type="button">Save entry</Button>
          </div>
        </section>
      ) : null}

      {total === 0 ? (
        <section className="rounded-[var(--radius-card)] border border-[var(--border)] bg-[var(--surface)] p-8 text-center">
          <h2 className="text-lg font-semibold text-[var(--text)]">No Question Bank entries yet</h2>
          <p className="mx-auto mt-2 max-w-md text-sm text-[var(--text-muted)]">Save answers, STAR stories, and proof points you can reuse in future interview prep.</p>
        </section>
      ) : (
        <section className="grid gap-3">
          {items.map((entry) => (
            <article className="rounded-[var(--radius-card)] border border-[var(--border)] bg-[var(--surface)] p-5" key={entry.id}>
              <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <h2 className="text-lg font-semibold text-[var(--text)]">{entry.title}</h2>
                    <span className="rounded-full bg-[var(--surface-2)] px-2 py-1 text-xs font-medium text-[var(--text-muted)]">{entry.type.replace(/_/g, " ")}</span>
                    <span className="rounded-full bg-[var(--accent-soft)] px-2 py-1 text-xs font-medium text-[var(--accent)]">{entry.confidence}</span>
                  </div>
                  {entry.question ? <p className="mt-2 text-sm font-medium text-[var(--text)]">{entry.question}</p> : null}
                  <p className="mt-2 line-clamp-3 text-sm leading-relaxed text-[var(--text-muted)]">{entry.answer_draft}</p>
                  <div className="mt-3 flex flex-wrap gap-2">
                    {[...entry.tags, ...entry.skills].slice(0, 8).map((label) => (
                      <span className="rounded-full bg-[var(--surface-2)] px-2 py-1 text-xs text-[var(--text-muted)]" key={label}>{label}</span>
                    ))}
                  </div>
                </div>
                <div className="grid gap-2 sm:grid-cols-3 lg:min-w-[330px]">
                  <Button aria-label={`Edit ${entry.title}`} disabled={isPending} onClick={() => edit(entry)} type="button" variant="outline">
                    <Pencil className="h-4 w-4" aria-hidden="true" />
                    Edit
                  </Button>
                  <Button aria-label={`Duplicate ${entry.title}`} disabled={isPending} onClick={() => duplicate(entry)} type="button" variant="secondary">
                    <CopyPlus className="h-4 w-4" aria-hidden="true" />
                    Adapt
                  </Button>
                  <Button aria-label={`Delete ${entry.title}`} disabled={isPending} onClick={() => remove(entry)} type="button" variant="ghost">
                    <Trash2 className="h-4 w-4" aria-hidden="true" />
                    Delete
                  </Button>
                </div>
              </div>
            </article>
          ))}
        </section>
      )}
    </div>
  );
}

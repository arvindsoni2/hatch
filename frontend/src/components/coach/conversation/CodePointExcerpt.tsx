import type { ConversationTranscriptEvidenceSpan } from "@/lib/api";

export function sliceCodePoints(value: string, start: number, end: number): string {
  const normalized = value.normalize("NFC").replace(/\r\n?/g, "\n");
  return Array.from(normalized).slice(start, end).join("");
}

interface CodePointExcerptProps {
  transcript: string;
  span: ConversationTranscriptEvidenceSpan;
}

export function CodePointExcerpt({ transcript, span }: CodePointExcerptProps) {
  const excerpt = sliceCodePoints(transcript, span.transcript_start, span.transcript_end);

  return (
    <q className="block border-l-2 border-[var(--accent)] pl-3 text-sm text-[var(--text-muted)]">
      {excerpt}
    </q>
  );
}

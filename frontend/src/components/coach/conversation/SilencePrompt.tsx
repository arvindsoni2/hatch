import { Button } from "@/components/ui/button";

interface SilencePromptProps {
  pending: boolean;
  onFinish: () => void;
  onKeepSpeaking: () => void;
}

export function SilencePrompt({ pending, onFinish, onKeepSpeaking }: SilencePromptProps) {
  return (
    <section
      aria-label="Silence check"
      className="rounded-lg border border-[var(--border)] bg-[var(--surface-2)] p-3"
    >
      <p className="font-semibold text-[var(--text)]">Are you finished?</p>
      <div className="mt-3 flex flex-wrap gap-2">
        <Button type="button" onClick={onFinish} disabled={pending}>
          Finish answer after silence
        </Button>
        <Button type="button" variant="outline" onClick={onKeepSpeaking} disabled={pending}>
          Keep speaking and continue recording
        </Button>
      </div>
    </section>
  );
}

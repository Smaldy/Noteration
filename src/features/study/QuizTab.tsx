import { Check, Sparkles, X } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api";
import { cn } from "@/lib/utils";
import { useStudyStore } from "@/stores/study";
import type { MCQ } from "@/types/study";

interface QuizTabProps {
  topicId: number;
  mcqs: MCQ[];
}

export function QuizTab({ topicId, mcqs }: QuizTabProps) {
  const [index, setIndex] = useState(0);
  const [selected, setSelected] = useState<number | null>(null);
  const [revealed, setRevealed] = useState(false);
  const [correct, setCorrect] = useState(0);
  const [finished, setFinished] = useState(false);

  if (mcqs.length === 0) {
    return (
      <div className="py-12 text-center">
        <p className="text-sm text-muted-foreground">
          No quiz questions yet for this topic.
        </p>
        <div className="mt-4 flex justify-center">
          <GenerateMoreQuestions topicId={topicId} />
        </div>
      </div>
    );
  }

  function restart() {
    setIndex(0);
    setSelected(null);
    setRevealed(false);
    setCorrect(0);
    setFinished(false);
  }

  if (finished) {
    return (
      <div className="py-12 text-center">
        <p className="text-2xl font-semibold">
          {correct} / {mcqs.length}
        </p>
        <p className="mt-1 text-sm text-muted-foreground">
          {correct === mcqs.length ? "Perfect!" : "Review the ones you missed."}
        </p>
        <div className="mt-6 flex items-center justify-center gap-2">
          <Button variant="outline" onClick={restart}>
            Try again
          </Button>
          <GenerateMoreQuestions topicId={topicId} />
        </div>
      </div>
    );
  }

  const mcq = mcqs[index];

  function choose(i: number) {
    if (revealed) return;
    setSelected(i);
    setRevealed(true);
    if (i === mcq.correct_index) setCorrect((c) => c + 1);
  }

  function next() {
    if (index === mcqs.length - 1) {
      setFinished(true);
      return;
    }
    setIndex((i) => i + 1);
    setSelected(null);
    setRevealed(false);
  }

  return (
    <div>
      <div className="mb-4 h-1.5 w-full overflow-hidden rounded-full bg-muted">
        <div
          className="h-full bg-primary transition-all"
          style={{ width: `${(index / mcqs.length) * 100}%` }}
        />
      </div>
      <p className="mb-1 text-xs text-muted-foreground">
        Question {index + 1} of {mcqs.length}
      </p>
      <h3 className="text-lg font-medium">{mcq.question}</h3>

      <div className="mt-4 space-y-2">
        {mcq.options.map((option, i) => {
          const isCorrect = i === mcq.correct_index;
          const isChosen = i === selected;
          return (
            <button
              key={i}
              type="button"
              onClick={() => choose(i)}
              disabled={revealed}
              className={cn(
                "flex w-full items-center justify-between rounded-md border px-3 py-2 text-left text-sm transition-colors",
                !revealed && "hover:bg-accent/50",
                revealed && isCorrect && "border-emerald-500/60 bg-emerald-500/10",
                revealed &&
                  isChosen &&
                  !isCorrect &&
                  "border-destructive/60 bg-destructive/10",
              )}
            >
              <span>{option}</span>
              {revealed && isCorrect && (
                <Check className="size-4 text-emerald-600" />
              )}
              {revealed && isChosen && !isCorrect && (
                <X className="size-4 text-destructive" />
              )}
            </button>
          );
        })}
      </div>

      {revealed && (
        <div className="mt-4 rounded-md bg-muted/50 p-3 text-sm">
          {mcq.explanation ? (
            <p>{mcq.explanation}</p>
          ) : (
            <p className="text-muted-foreground">No explanation provided.</p>
          )}
        </div>
      )}

      <div className="mt-6 flex items-center justify-between gap-2">
        <GenerateMoreQuestions topicId={topicId} />
        <Button onClick={next} disabled={!revealed}>
          {index === mcqs.length - 1 ? "Finish" : "Next"}
        </Button>
      </div>
    </div>
  );
}

function GenerateMoreQuestions({ topicId }: { topicId: number }) {
  const generateMore = useStudyStore((s) => s.generateMore);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run() {
    setBusy(true);
    setError(null);
    try {
      await generateMore(topicId, "mcqs");
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Couldn't generate more questions.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col items-start gap-1">
      <Button variant="ghost" size="sm" onClick={() => void run()} disabled={busy}>
        <Sparkles />
        {busy ? "Generating…" : "Generate more questions"}
      </Button>
      {error && <p className="text-xs text-destructive">{error}</p>}
    </div>
  );
}

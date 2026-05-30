import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { ApiError, api } from "@/lib/api";
import type { FlashcardContent } from "@/types/study";

type Grade = "correct" | "incorrect" | "skip";

interface FlashcardsTabProps {
  flashcards: FlashcardContent[];
}

export function FlashcardsTab({ flashcards }: FlashcardsTabProps) {
  const [index, setIndex] = useState(0);
  const [flipped, setFlipped] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Reset when the deck changes (e.g. switching topics).
  useEffect(() => {
    setIndex(0);
    setFlipped(false);
    setError(null);
  }, [flashcards]);

  if (flashcards.length === 0) {
    return (
      <p className="py-12 text-center text-sm text-muted-foreground">
        No flashcards yet for this topic.
      </p>
    );
  }

  if (index >= flashcards.length) {
    return (
      <div className="py-12 text-center">
        <p className="text-lg font-medium">Deck complete</p>
        <Button
          className="mt-6"
          variant="outline"
          onClick={() => {
            setIndex(0);
            setFlipped(false);
          }}
        >
          Review again
        </Button>
      </div>
    );
  }

  const card = flashcards[index];

  async function grade(g: Grade) {
    setBusy(true);
    setError(null);
    try {
      await api.post(`/study/flashcards/${card.id}/review`, { grade: g });
      setIndex((i) => i + 1);
      setFlipped(false);
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Could not save your grade.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col items-center">
      <p className="mb-3 text-xs text-muted-foreground">
        Card {index + 1} of {flashcards.length}
      </p>

      <button
        type="button"
        onClick={() => setFlipped((f) => !f)}
        className={cn(
          "flex min-h-44 w-full max-w-xl items-center justify-center rounded-xl border p-8 text-center text-lg shadow-sm transition-colors",
          flipped ? "bg-muted/40" : "bg-card",
        )}
      >
        <div>
          <p className="mb-1 text-xs uppercase tracking-wide text-muted-foreground">
            {flipped ? "Back" : "Front"}
          </p>
          <p>{flipped ? card.back : card.front}</p>
        </div>
      </button>

      {!flipped ? (
        <p className="mt-4 text-sm text-muted-foreground">
          Click the card to reveal the answer.
        </p>
      ) : (
        <div className="mt-5 flex gap-2">
          <Button
            variant="outline"
            onClick={() => void grade("incorrect")}
            disabled={busy}
          >
            Incorrect
          </Button>
          <Button
            variant="ghost"
            onClick={() => void grade("skip")}
            disabled={busy}
          >
            Skip
          </Button>
          <Button onClick={() => void grade("correct")} disabled={busy}>
            Correct
          </Button>
        </div>
      )}

      {error && <p className="mt-3 text-sm text-destructive">{error}</p>}
    </div>
  );
}

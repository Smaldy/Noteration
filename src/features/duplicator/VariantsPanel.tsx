import { Loader2 } from "lucide-react";

import type { ExtractedExercise } from "@/types/duplicator";

import { DuplicateResultCard } from "./DuplicateResultCard";

/**
 * Shows an exercise's variant results, with a per-exercise loading state while
 * its background search runs. Polling of the whole session is owned by the store
 * (it refreshes every 4s until every exercise reaches a terminal status).
 */
export function VariantsPanel({
  exercise,
  yearLevel,
}: {
  exercise: ExtractedExercise;
  yearLevel: number;
}) {
  const { status, results } = exercise;

  return (
    <div className="mt-4 border-t border-border pt-3">
      <div className="mb-2 flex items-center gap-2 text-xs font-medium text-muted-foreground">
        <span>Variant problems</span>
        {status === "searching" && <Loader2 className="h-3 w-3 animate-spin" />}
      </div>

      {status === "pending" && (
        <p className="text-xs text-muted-foreground">Queued for variant search…</p>
      )}
      {status === "searching" && results.length === 0 && (
        <p className="text-xs text-muted-foreground">
          Searching for university-level variants…
        </p>
      )}
      {status === "error" && (
        <p className="text-xs text-destructive">
          Variant search failed for this exercise.
        </p>
      )}
      {status === "done" && results.length === 0 && (
        <p className="text-xs text-muted-foreground">No variants found.</p>
      )}

      <div className="space-y-2">
        {results.map((result) => (
          <DuplicateResultCard
            key={result.id}
            result={result}
            topic={exercise.topic}
            subtopic={exercise.subtopic}
            yearLevel={yearLevel}
          />
        ))}
      </div>
    </div>
  );
}

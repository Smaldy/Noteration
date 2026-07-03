import { Loader2 } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import type { ExtractedExercise } from "@/types/duplicator";

import { DuplicateResultCard } from "./DuplicateResultCard";
import { VariantFocusDialog } from "./VariantFocusDialog";

/**
 * Shows an exercise's variant results, with a per-exercise loading state while
 * its background search runs. Polling of the whole session is owned by the store
 * (it refreshes every 4s until every exercise reaches a terminal status). Owns the
 * variant full-screen focus state so any variant can be opened large (with its
 * graph) and paged through.
 */
export function VariantsPanel({
  exercise,
  yearLevel,
}: {
  exercise: ExtractedExercise;
  yearLevel: number;
}) {
  const { t } = useTranslation();
  const { status, results } = exercise;
  const [focusIdx, setFocusIdx] = useState<number | null>(null);

  return (
    <div className="mt-4 border-t border-border pt-3">
      <div className="mb-2 flex items-center gap-2 text-xs font-medium text-muted-foreground">
        <span>{t("duplicator.variants.heading")}</span>
        {status === "searching" && <Loader2 className="h-3 w-3 animate-spin" />}
      </div>

      {status === "pending" && (
        <p className="text-xs text-muted-foreground">{t("duplicator.variants.queued")}</p>
      )}
      {status === "searching" && results.length === 0 && (
        <p className="text-xs text-muted-foreground">
          {t("duplicator.variants.searching")}
        </p>
      )}
      {status === "error" && (
        <p className="text-xs text-destructive">
          {t("duplicator.variants.failed")}
        </p>
      )}
      {status === "done" && results.length === 0 && (
        <p className="text-xs text-muted-foreground">{t("duplicator.variants.empty")}</p>
      )}

      <div className="grid gap-3 md:grid-cols-2">
        {results.map((result, i) => (
          <DuplicateResultCard
            key={result.id}
            result={result}
            topic={exercise.topic}
            subtopic={exercise.subtopic}
            yearLevel={yearLevel}
            onFocus={() => setFocusIdx(i)}
          />
        ))}
      </div>

      {focusIdx !== null && results[focusIdx] && (
        <VariantFocusDialog
          results={results}
          index={focusIdx}
          topic={exercise.topic}
          subtopic={exercise.subtopic}
          yearLevel={yearLevel}
          onNavigate={setFocusIdx}
          onClose={() => setFocusIdx(null)}
        />
      )}
    </div>
  );
}

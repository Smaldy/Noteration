import { ChevronRight, Loader2, Maximize2, Trash2 } from "lucide-react";

import { MarkdownView } from "@/components/MarkdownView";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import type { ExtractedExercise } from "@/types/duplicator";

import { normalizeLatex } from "./latex";
import { VizRouter } from "./renderers/VizRouter";

/** A short, glanceable summary of the variant-search state for the card footer. */
function variantSummary(exercise: ExtractedExercise) {
  const n = exercise.results.length;
  switch (exercise.status) {
    case "pending":
      return { label: "Queued for variants", tone: "muted", spinning: false };
    case "searching":
      return {
        label: n > 0 ? `${n} so far · searching` : "Searching variants",
        tone: "muted",
        spinning: true,
      };
    case "error":
      return { label: "Variant search failed", tone: "error", spinning: false };
    default:
      return n > 0
        ? { label: `${n} variant${n === 1 ? "" : "s"}`, tone: "accent", spinning: false }
        : { label: "No variants found", tone: "muted", spinning: false };
  }
}

/**
 * Compact, glanceable card for the results grid. Shows the exercise preview
 * (topic, problem, viz) and a single clear affordance — the footer / "Focus"
 * button — that opens the full-screen view of this one exercise and its
 * variants. The card body itself is not clickable (no fake-clickable surface);
 * only the labelled controls are.
 */
export function ExtractedExerciseCard({
  exercise,
  index,
  onFocus,
  onRemove,
}: {
  exercise: ExtractedExercise;
  index: number;
  onFocus: () => void;
  onRemove: () => void;
}) {
  const summary = variantSummary(exercise);

  return (
    <Card className="group flex flex-col overflow-hidden transition-shadow hover:shadow-md">
      <CardContent className="flex flex-1 flex-col gap-3 p-5">
        <div className="flex items-start justify-between gap-2">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="grid h-6 min-w-6 place-items-center rounded-md bg-primary/10 px-1.5 text-xs font-bold tabular-nums text-primary">
              {index + 1}
            </span>
            <Badge variant="secondary">{exercise.topic}</Badge>
            {exercise.subtopic && (
              <Badge variant="outline">{exercise.subtopic}</Badge>
            )}
          </div>
          <div className="flex shrink-0 items-center gap-0.5 opacity-0 transition-opacity focus-within:opacity-100 group-hover:opacity-100">
            <button
              type="button"
              onClick={onRemove}
              title="Remove exercise"
              aria-label="Remove exercise"
              className="grid h-7 w-7 place-items-center rounded-md text-muted-foreground transition-colors hover:bg-destructive/10 hover:text-destructive"
            >
              <Trash2 className="h-3.5 w-3.5" />
            </button>
            <button
              type="button"
              onClick={onFocus}
              title="Open full screen"
              aria-label="Open full screen"
              className="flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground"
            >
              <Maximize2 className="h-3.5 w-3.5" />
              Focus
            </button>
          </div>
        </div>

        {exercise.difficulty_signals.length > 0 && (
          <div className="flex flex-wrap gap-1">
            {exercise.difficulty_signals.map((signal) => (
              <span
                key={signal}
                className="rounded-full bg-muted px-2 py-0.5 text-[10px] text-muted-foreground"
              >
                {signal}
              </span>
            ))}
          </div>
        )}

        {/* Preview: clamp tall problems behind a fade so the grid stays even. */}
        <div className="relative max-h-44 overflow-hidden text-sm">
          <MarkdownView interactiveTasks>
            {normalizeLatex(exercise.raw_text)}
          </MarkdownView>
          <div className="pointer-events-none absolute inset-x-0 bottom-0 h-10 bg-gradient-to-t from-card to-transparent" />
        </div>

        <VizRouter viz={exercise.viz} />

        {/* Footer: the variant summary doubles as the secondary focus trigger. */}
        <button
          type="button"
          onClick={onFocus}
          className="mt-auto flex items-center justify-between gap-2 rounded-lg border border-border bg-background/60 px-3 py-2 text-left transition-colors hover:border-primary/40 hover:bg-accent/40"
        >
          <span
            className={cn(
              "flex items-center gap-1.5 text-xs font-medium",
              summary.tone === "accent" && "text-primary",
              summary.tone === "error" && "text-destructive",
              summary.tone === "muted" && "text-muted-foreground",
            )}
          >
            {summary.spinning ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <span
                className={cn(
                  "h-1.5 w-1.5 rounded-full",
                  summary.tone === "accent" && "bg-primary",
                  summary.tone === "error" && "bg-destructive",
                  summary.tone === "muted" && "bg-muted-foreground/50",
                )}
              />
            )}
            {summary.label}
          </span>
          <ChevronRight className="h-4 w-4 text-muted-foreground transition-transform group-hover:translate-x-0.5" />
        </button>
      </CardContent>
    </Card>
  );
}

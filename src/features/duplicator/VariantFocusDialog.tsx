import {
  BookmarkPlus,
  Check,
  ChevronLeft,
  ChevronRight,
  ExternalLink,
  X,
} from "lucide-react";
import { useEffect } from "react";

import { MarkdownView } from "@/components/MarkdownView";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { DuplicateResult } from "@/types/duplicator";

import { normalizeLatex } from "./latex";
import { useCalibrationSave } from "./useCalibrationSave";
import { VizRouter } from "./renderers/VizRouter";

interface Props {
  results: DuplicateResult[];
  index: number;
  topic: string;
  subtopic: string | null;
  yearLevel: number;
  onNavigate: (next: number) => void;
  onClose: () => void;
}

/** Difficulty meter, shared between the header and the body. */
function DifficultyBar({ score }: { score: number }) {
  return (
    <div className="flex items-center gap-2">
      <span className="text-xs text-muted-foreground">Difficulty</span>
      <div className="h-1.5 w-28 overflow-hidden rounded-full bg-muted">
        <div
          className="h-full rounded-full bg-primary"
          style={{ width: `${Math.round(Math.min(1, Math.max(0, score)) * 100)}%` }}
        />
      </div>
      <span className="w-8 text-right text-xs tabular-nums text-muted-foreground">
        {score.toFixed(2)}
      </span>
    </div>
  );
}

/** The per-variant body — keyed by result id so save-state resets on navigate. */
function VariantBody({
  result,
  topic,
  subtopic,
  yearLevel,
}: {
  result: DuplicateResult;
  topic: string;
  subtopic: string | null;
  yearLevel: number;
}) {
  const { saved, saving, save } = useCalibrationSave(
    result,
    topic,
    subtopic,
    yearLevel,
  );
  const hasViz = Boolean(result.viz?.type);

  return (
    <div className="mx-auto max-w-7xl space-y-6 px-4 py-6 sm:px-6">
      <div className={cn("grid gap-6", hasViz && "lg:grid-cols-2 lg:items-start")}>
        <section className="focus-card focus-float fullscreen-zoom rounded-2xl p-6 sm:p-8">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
              Variant problem
            </span>
            {result.difficulty_score !== null && (
              <DifficultyBar score={result.difficulty_score} />
            )}
          </div>
          <MarkdownView>{normalizeLatex(result.problem_text)}</MarkdownView>

          <div className="mt-6 flex items-center justify-between gap-2 border-t border-border/60 pt-4">
            {result.source_url ? (
              <a
                href={result.source_url}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground hover:underline"
              >
                <ExternalLink className="h-3.5 w-3.5" />
                View source
              </a>
            ) : (
              <span />
            )}
            <Button
              variant="outline"
              size="sm"
              onClick={save}
              disabled={saving || saved}
              className="gap-1.5"
            >
              {saved ? (
                <>
                  <Check className="h-3.5 w-3.5" /> Saved
                </>
              ) : (
                <>
                  <BookmarkPlus className="h-3.5 w-3.5" /> Save to calibration
                </>
              )}
            </Button>
          </div>
        </section>

        {hasViz && (
          <section className="focus-card focus-float rounded-2xl p-4 sm:p-5 lg:sticky lg:top-6">
            <div className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
              Visualization
            </div>
            <VizRouter viz={result.viz} height={440} />
          </section>
        )}
      </div>
    </div>
  );
}

/**
 * Full-screen focus mode for a single variant — same description | graph split as
 * the exercise focus, stacked above it (z-60). ←/→ page through the exercise's
 * variants, Esc closes.
 */
export function VariantFocusDialog({
  results,
  index,
  topic,
  subtopic,
  yearLevel,
  onNavigate,
  onClose,
}: Props) {
  const result = results[index];
  const total = results.length;

  useEffect(() => {
    // Capture phase + stopPropagation so keys handled here never reach the
    // exercise focus dialog stacked underneath (which has its own arrow/Esc nav).
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        onClose();
      } else if (e.key === "ArrowRight") {
        e.stopPropagation();
        if (index < total - 1) onNavigate(index + 1);
      } else if (e.key === "ArrowLeft") {
        e.stopPropagation();
        if (index > 0) onNavigate(index - 1);
      }
    };
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [index, total, onNavigate, onClose]);

  if (!result) return null;

  return (
    <div className="fullscreen-stage fixed inset-0 z-[60] flex flex-col" role="dialog" aria-modal="true">
      <header className="glass relative z-10 flex items-center justify-between gap-3 border-b border-border/60 px-4 py-2.5 sm:px-6">
        <span className="text-sm font-semibold tabular-nums">
          Variant {index + 1}
          <span className="text-muted-foreground"> / {total}</span>
        </span>
        <div className="flex shrink-0 items-center gap-1">
          <Button
            variant="ghost"
            size="icon"
            disabled={index === 0}
            onClick={() => onNavigate(index - 1)}
            aria-label="Previous variant"
          >
            <ChevronLeft className="h-5 w-5" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            disabled={index === total - 1}
            onClick={() => onNavigate(index + 1)}
            aria-label="Next variant"
          >
            <ChevronRight className="h-5 w-5" />
          </Button>
          <Button variant="ghost" size="icon" onClick={onClose} aria-label="Close variant focus">
            <X className="h-5 w-5" />
          </Button>
        </div>
      </header>

      <div className="relative z-10 flex-1 overflow-y-auto">
        <VariantBody
          key={result.id}
          result={result}
          topic={topic}
          subtopic={subtopic}
          yearLevel={yearLevel}
        />
      </div>
    </div>
  );
}

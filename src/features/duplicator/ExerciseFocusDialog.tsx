import {
  ChevronLeft,
  ChevronRight,
  RefreshCw,
  Trash2,
  X,
} from "lucide-react";
import { useEffect } from "react";

import { MarkdownView } from "@/components/MarkdownView";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { ExtractedExercise } from "@/types/duplicator";

import { normalizeLatex } from "./latex";
import { VariantsPanel } from "./VariantsPanel";
import { VizRouter } from "./renderers/VizRouter";

interface Props {
  exercises: ExtractedExercise[];
  index: number;
  yearLevel: number;
  onNavigate: (next: number) => void;
  onClose: () => void;
  onRemove: (exerciseId: number) => void;
  onFindMore: (exerciseId: number) => void;
}

/**
 * Full-screen focus mode for a single exercise. The viewport is split into a
 * description pane and a visualization pane (when the exercise has a graph), with
 * the full variant list below — so one problem gets the whole screen instead of a
 * cramped card. Arrow keys / header arrows page between exercises; Esc closes.
 * Body scroll is locked while open.
 */
export function ExerciseFocusDialog({
  exercises,
  index,
  yearLevel,
  onNavigate,
  onClose,
  onRemove,
  onFindMore,
}: Props) {
  const exercise = exercises[index];
  const total = exercises.length;

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      else if (e.key === "ArrowRight" && index < total - 1) onNavigate(index + 1);
      else if (e.key === "ArrowLeft" && index > 0) onNavigate(index - 1);
    };
    window.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [index, total, onNavigate, onClose]);

  if (!exercise) return null;
  const hasViz = Boolean(exercise.viz?.type);
  const searching =
    exercise.status === "pending" || exercise.status === "searching";

  return (
    <div className="fullscreen-stage fixed inset-0 z-50 flex flex-col" role="dialog" aria-modal="true">
      {/* Sticky header — always reachable, never needs a scroll-up. */}
      <header className="glass relative z-10 flex items-center justify-between gap-3 border-b border-border/60 px-4 py-2.5 sm:px-6">
        <div className="flex min-w-0 items-center gap-2">
          <span className="shrink-0 text-sm font-semibold tabular-nums">
            Exercise {index + 1}
            <span className="text-muted-foreground"> / {total}</span>
          </span>
          <Badge variant="secondary" className="truncate">{exercise.topic}</Badge>
          {exercise.subtopic && (
            <Badge variant="outline" className="hidden truncate sm:inline-flex">
              {exercise.subtopic}
            </Badge>
          )}
        </div>

        <div className="flex shrink-0 items-center gap-1">
          <Button
            variant="outline"
            size="sm"
            className="gap-1.5"
            disabled={searching}
            onClick={() => onFindMore(exercise.id)}
          >
            <RefreshCw className={cn("h-3.5 w-3.5", searching && "animate-spin")} />
            <span className="hidden sm:inline">Find more</span>
          </Button>
          <Button
            variant="ghost"
            size="sm"
            className="gap-1.5 text-muted-foreground hover:text-destructive"
            onClick={() => onRemove(exercise.id)}
          >
            <Trash2 className="h-3.5 w-3.5" />
            <span className="hidden sm:inline">Remove</span>
          </Button>
          <div className="mx-1 h-5 w-px bg-border" />
          <Button
            variant="ghost"
            size="icon"
            disabled={index === 0}
            onClick={() => onNavigate(index - 1)}
            aria-label="Previous exercise"
          >
            <ChevronLeft className="h-5 w-5" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            disabled={index === total - 1}
            onClick={() => onNavigate(index + 1)}
            aria-label="Next exercise"
          >
            <ChevronRight className="h-5 w-5" />
          </Button>
          <Button variant="ghost" size="icon" onClick={onClose} aria-label="Close focus mode">
            <X className="h-5 w-5" />
          </Button>
        </div>
      </header>

      {/* Scrollable body */}
      <div className="relative z-10 flex-1 overflow-y-auto">
        <div className="mx-auto max-w-7xl space-y-6 px-4 py-6 sm:px-6">
          <div
            className={cn(
              "grid gap-6",
              hasViz && "lg:grid-cols-2 lg:items-start",
            )}
          >
            {/* Description pane */}
            <section className="focus-card focus-float fullscreen-zoom rounded-2xl p-6 sm:p-8">
              <div className="mb-3 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                Problem
              </div>
              {exercise.difficulty_signals.length > 0 && (
                <div className="mb-4 flex flex-wrap gap-1.5">
                  {exercise.difficulty_signals.map((signal) => (
                    <span
                      key={signal}
                      className="rounded-full bg-muted px-2.5 py-0.5 text-xs text-muted-foreground"
                    >
                      {signal}
                    </span>
                  ))}
                </div>
              )}
              <MarkdownView>{normalizeLatex(exercise.raw_text)}</MarkdownView>
            </section>

            {/* Visualization pane */}
            {hasViz && (
              <section className="focus-card focus-float rounded-2xl p-4 sm:p-5 lg:sticky lg:top-6">
                <div className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                  Visualization
                </div>
                <VizRouter viz={exercise.viz} height={440} />
              </section>
            )}
          </div>

          {/* Variants — full width below the split. */}
          <section className="focus-card focus-float rounded-2xl p-6 sm:p-8">
            <VariantsPanel exercise={exercise} yearLevel={yearLevel} />
          </section>
        </div>
      </div>
    </div>
  );
}

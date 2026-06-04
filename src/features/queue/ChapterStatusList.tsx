import { motion } from "framer-motion";
import { BookOpen, Moon, Pause, Play } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type {
  ChapterQueueState,
  ChapterStatus,
  DocumentChapters,
} from "@/types/chapter";

const STATE_STYLE: Record<
  ChapterQueueState,
  { label: string; accent: string; pill: string }
> = {
  running: {
    label: "Processing",
    accent: "bg-primary",
    pill: "bg-primary-soft text-primary-soft-foreground",
  },
  overnight: {
    label: "Overnight",
    accent: "bg-indigo-500",
    pill: "bg-indigo-500/12 text-indigo-700 dark:text-indigo-300",
  },
  paused: {
    label: "Paused",
    accent: "bg-muted-foreground/40",
    pill: "bg-muted text-muted-foreground",
  },
};

interface ChapterStatusListProps {
  /** Chapter lanes grouped by their book (document). */
  groups: DocumentChapters[];
  busy: number | null;
  onSetState: (chapterId: number, state: ChapterQueueState) => void;
}

export function ChapterStatusList({
  groups,
  busy,
  onSetState,
}: ChapterStatusListProps) {
  if (groups.length === 0) return null;
  return (
    <section className="space-y-5">
      <div>
        <h2 className="text-sm font-semibold tracking-tight">Chapters</h2>
        <p className="mt-0.5 text-xs text-muted-foreground">
          Resume a paused chapter to start generating its topics; pause one to stop.
        </p>
      </div>
      {groups.map((group) => (
        <div key={group.document_id}>
          {/* Books are scoped per document so the user always knows which one. */}
          <h3 className="flex items-center gap-1.5 px-0.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            <BookOpen className="size-3.5 shrink-0" />
            <span className="truncate">{group.subject_name}</span>
            <span className="truncate font-normal normal-case text-muted-foreground/70">
              · {group.filename}
            </span>
          </h3>
          <ul className="mt-2 space-y-2">
            {group.chapters.map((chapter) => (
              <ChapterRow
                key={chapter.id}
                chapter={chapter}
                busy={busy === chapter.id}
                onSetState={onSetState}
              />
            ))}
          </ul>
        </div>
      ))}
    </section>
  );
}

function ChapterRow({
  chapter,
  busy,
  onSetState,
}: {
  chapter: ChapterStatus;
  busy: boolean;
  onSetState: (chapterId: number, state: ChapterQueueState) => void;
}) {
  const style = STATE_STYLE[chapter.queue_state];
  const paused = chapter.queue_state === "paused";
  const total = chapter.topics_total;
  const pct = total > 0 ? Math.round((chapter.topics_ready / total) * 100) : 0;
  const range =
    chapter.page_start != null && chapter.page_end != null
      ? `pp. ${chapter.page_start}–${chapter.page_end}`
      : null;

  return (
    <motion.li
      layout
      className="relative overflow-hidden rounded-xl border bg-card p-4 pl-5 shadow-sm"
    >
      <span className={cn("absolute inset-y-0 left-0 w-1", style.accent)} />

      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="truncate text-sm font-semibold tracking-tight">
              {chapter.title}
            </h3>
            {range && (
              <span className="shrink-0 rounded-md bg-muted px-1.5 py-0.5 text-[11px] tabular-nums text-muted-foreground">
                {range}
              </span>
            )}
            <span
              className={cn(
                "shrink-0 rounded-full px-2 py-0.5 text-[11px] font-medium",
                style.pill,
              )}
            >
              {style.label}
            </span>
          </div>
          <p className="mt-1 text-xs text-muted-foreground tabular-nums">
            {chapter.topics_ready}/{total} ready
            {chapter.topics_processing > 0 && ` · ${chapter.topics_processing} processing`}
            {chapter.topics_error > 0 && (
              <span className="text-destructive"> · {chapter.topics_error} errored</span>
            )}
          </p>
        </div>

        <div className="shrink-0">
          {chapter.queue_state === "overnight" ? (
            <span className="inline-flex items-center gap-1.5 text-xs text-indigo-700 dark:text-indigo-300">
              <Moon className="size-3.5" />
              Overnight
            </span>
          ) : (
            <Button
              variant={paused ? "default" : "outline"}
              size="sm"
              disabled={busy}
              onClick={() => onSetState(chapter.id, paused ? "running" : "paused")}
            >
              {paused ? <Play className="size-4" /> : <Pause className="size-4" />}
              {paused ? "Resume chapter" : "Pause"}
            </Button>
          )}
        </div>
      </div>

      {/* Progress bar (ready / total). */}
      <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-muted">
        <motion.div
          className="h-full rounded-full bg-primary"
          initial={false}
          animate={{ width: `${pct}%` }}
          transition={{ duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
        />
      </div>
    </motion.li>
  );
}

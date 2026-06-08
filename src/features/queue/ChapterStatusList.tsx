import { motion, type Variants } from "framer-motion";
import { BookOpen, Moon, Pause, Play } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type {
  ChapterQueueState,
  ChapterStatus,
  DocumentChapters,
} from "@/types/chapter";

// Visual style per chapter state; the label is resolved via i18n at render.
const STATE_STYLE: Record<ChapterQueueState, { accent: string; pill: string }> = {
  running: {
    accent: "bg-primary",
    pill: "bg-primary-soft text-primary-soft-foreground",
  },
  overnight: {
    accent: "bg-indigo-500",
    pill: "bg-indigo-500/12 text-indigo-700 dark:text-indigo-300",
  },
  paused: {
    accent: "bg-muted-foreground/40",
    pill: "bg-muted text-muted-foreground",
  },
};

/** A chapter is "done" when every topic is ready and nothing is pending/erroring —
 *  the only chapters the user can clear from the queue (with the dust animation).
 *  A chapter with no generatable topics (0/0) counts as done: there's nothing left
 *  to do. Mirrors the backend's "finished" rule in ``get_book_chapter_groups``. */
export function isChapterComplete(ch: ChapterStatus): boolean {
  return (
    ch.topics_ready >= ch.topics_total &&
    ch.topics_processing === 0 &&
    ch.topics_queued === 0 &&
    ch.topics_error === 0
  );
}

// --- dust disintegration ----------------------------------------------------
// A cleared chapter scatters into ~16 emerald motes that drift up and fade while
// the card blurs out, then the row is committed to the dismissed set and unmounts
// (already invisible, so the removal is seamless). Offsets are deterministic per
// chapter id so the scatter is stable across re-renders mid-animation.
const DUST_COUNT = 16;

function hash01(seed: number): number {
  const x = Math.sin(seed * 12.9898) * 43758.5453;
  return x - Math.floor(x);
}

interface Mote {
  left: string;
  top: string;
  dx: number;
  dy: number;
  size: number;
  delay: number;
}

function motes(chapterId: number): Mote[] {
  return Array.from({ length: DUST_COUNT }, (_, i) => {
    const a = hash01(chapterId * 31 + i * 7);
    const b = hash01(chapterId * 17 + i * 13 + 1);
    const c = hash01(chapterId * 53 + i * 3 + 2);
    return {
      left: `${Math.round(a * 100)}%`,
      top: `${Math.round(b * 100)}%`,
      dx: (a - 0.5) * 70, // spread outward
      dy: -24 - c * 72, // drift upward like rising dust
      size: 2 + Math.round(c * 3),
      delay: a * 0.12,
    };
  });
}

const ROW_VARIANTS: Variants = {
  show: { opacity: 1, scale: 1, filter: "blur(0px)" },
  dust: {
    opacity: 0,
    scale: 0.94,
    filter: "blur(6px)",
    transition: { duration: 0.66, ease: [0.4, 0, 0.2, 1] },
  },
};

const MOTE_VARIANTS: Variants = {
  show: { opacity: 0, x: 0, y: 0, scale: 1 },
  dust: (m: Mote) => ({
    opacity: [0, 1, 0],
    x: m.dx,
    y: m.dy,
    scale: [1, 0.2],
    transition: { duration: 0.6, ease: "easeOut", times: [0, 0.3, 1], delay: m.delay },
  }),
};

interface ChapterGroupsProps {
  /** One subject's documents (already filtered to that subject's lane). */
  groups: DocumentChapters[];
  busy: number | null;
  /** Chapter ids currently playing the dust-clear animation. */
  dissolving: number[];
  onSetState: (chapterId: number, state: ChapterQueueState) => void;
  onDissolved: (chapterId: number) => void;
}

/** The chapter lanes for one subject, grouped by document, shown nested inside the
 *  subject lane card when it's expanded. Each chapter has a pause/resume control. */
export function ChapterGroups({
  groups,
  busy,
  dissolving,
  onSetState,
  onDissolved,
}: ChapterGroupsProps) {
  if (groups.length === 0) return null;
  return (
    <div className="space-y-4">
      {groups.map((group) => (
        <div key={group.document_id}>
          {/* Scoped per document so the user always knows which file. */}
          <h4 className="flex items-center gap-1.5 px-0.5 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
            <BookOpen className="size-3.5 shrink-0" />
            <span className="truncate">{group.filename}</span>
          </h4>
          <ul className="mt-2 space-y-2">
            {group.chapters.map((chapter) => (
              <ChapterRow
                key={chapter.id}
                chapter={chapter}
                busy={busy === chapter.id}
                dissolving={dissolving.includes(chapter.id)}
                onSetState={onSetState}
                onDissolved={onDissolved}
              />
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}

export function ChapterRow({
  chapter,
  busy,
  dissolving,
  onSetState,
  onDissolved,
}: {
  chapter: ChapterStatus;
  busy: boolean;
  dissolving: boolean;
  onSetState: (chapterId: number, state: ChapterQueueState) => void;
  onDissolved: (chapterId: number) => void;
}) {
  const { t } = useTranslation();
  const style = STATE_STYLE[chapter.queue_state];
  const paused = chapter.queue_state === "paused";
  const total = chapter.topics_total;
  const pct = total > 0 ? Math.round((chapter.topics_ready / total) * 100) : 0;
  const range =
    chapter.page_start != null && chapter.page_end != null
      ? t("queue.chapters.pages", {
          start: chapter.page_start,
          end: chapter.page_end,
        })
      : null;

  return (
    <motion.li
      layout
      variants={ROW_VARIANTS}
      initial={false}
      animate={dissolving ? "dust" : "show"}
      onAnimationComplete={(def) => {
        if (def === "dust") onDissolved(chapter.id);
      }}
      className="relative overflow-hidden rounded-xl border bg-card p-4 pl-5 shadow-sm"
    >
      <span className={cn("absolute inset-y-0 left-0 w-1", style.accent)} />

      {/* Dust motes — invisible until this row dissolves, then they scatter. */}
      <div className="pointer-events-none absolute inset-0 z-10" aria-hidden>
        {motes(chapter.id).map((m, i) => (
          <motion.span
            key={i}
            custom={m}
            variants={MOTE_VARIANTS}
            className="absolute rounded-full bg-emerald-400/80 shadow-[0_0_6px_rgba(52,211,153,0.6)]"
            style={{ left: m.left, top: m.top, width: m.size, height: m.size }}
          />
        ))}
      </div>

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
              {t(`queue.chapters.states.${chapter.queue_state}`)}
            </span>
          </div>
          <p className="mt-1 text-xs text-muted-foreground tabular-nums">
            {t("queue.chapters.ready", { ready: chapter.topics_ready, total })}
            {chapter.topics_processing > 0 &&
              ` · ${t("queue.chapters.processing", { count: chapter.topics_processing })}`}
            {chapter.topics_error > 0 && (
              <span className="text-destructive">
                {" · "}
                {t("queue.chapters.errored", { count: chapter.topics_error })}
              </span>
            )}
          </p>
        </div>

        <div className="shrink-0">
          {chapter.queue_state === "overnight" ? (
            <span className="inline-flex items-center gap-1.5 text-xs text-indigo-700 dark:text-indigo-300">
              <Moon className="size-3.5" />
              {t("queue.chapters.overnight")}
            </span>
          ) : (
            <Button
              variant={paused ? "default" : "outline"}
              size="sm"
              disabled={busy}
              onClick={() => onSetState(chapter.id, paused ? "running" : "paused")}
            >
              {paused ? <Play className="size-4" /> : <Pause className="size-4" />}
              {paused ? t("queue.chapters.resumeChapter") : t("queue.chapters.pause")}
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

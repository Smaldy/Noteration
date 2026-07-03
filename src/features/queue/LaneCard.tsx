import { AnimatePresence, motion } from "framer-motion";
import { ChevronDown, Clock, Moon, Pause, Play, Sparkles } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { cn } from "@/lib/utils";
import { providerInfo } from "@/lib/providers";
import type { ChapterQueueState, DocumentChapters } from "@/types/chapter";
import type { LaneState, LaneStatus } from "@/types/lanes";
import { ChapterGroups, isChapterComplete } from "./ChapterStatusList";

// Visual style per lane state, all from semantic tokens: running carries the
// accent, overnight the quiet info blue, waiting the warning amber.
const STATE_STYLE: Record<LaneState, { accent: string; pill: string }> = {
  running: {
    accent: "bg-primary",
    pill: "bg-primary-soft text-primary-soft-foreground",
  },
  overnight: {
    accent: "bg-info",
    pill: "bg-info/12 text-info",
  },
  waiting: {
    accent: "bg-warning",
    pill: "bg-warning/12 text-warning",
  },
  paused: {
    accent: "bg-muted-foreground/50",
    pill: "bg-muted text-muted-foreground",
  },
};

interface LaneCardProps {
  lane: LaneStatus;
  busy: boolean;
  /** This subject's documents + chapters, shown nested when the card is expanded. */
  chapterGroups: DocumentChapters[];
  chapterBusy: number | null;
  onSetChapterState: (chapterId: number, state: ChapterQueueState) => void;
  /** Hide completed chapters from the queue (called once each one's dust settles). */
  onDismissChapters: (chapterIds: number[]) => void;
  onPauseToggle: () => void;
  onOvernightToggle: (enabled: boolean) => void;
}

export function LaneCard({
  lane,
  busy,
  chapterGroups,
  chapterBusy,
  onSetChapterState,
  onDismissChapters,
  onPauseToggle,
  onOvernightToggle,
}: LaneCardProps) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(false);
  // Chapters mid dust-clear: they keep rendering (animating) until their motes
  // settle, then `onDissolved` commits them to the dismissed set and they unmount.
  const [dissolving, setDissolving] = useState<number[]>([]);
  const style = STATE_STYLE[lane.state];
  const paused = lane.queue_state === "paused";
  const provider = providerInfo(lane.active_provider);
  const chapterCount = chapterGroups.reduce((n, g) => n + g.chapters.length, 0);
  const canExpand = chapterCount > 0;
  const completedIds = chapterGroups
    .flatMap((g) => g.chapters)
    .filter((c) => isChapterComplete(c) && !dissolving.includes(c.id))
    .map((c) => c.id);

  const clearCompleted = () => setDissolving((prev) => [...prev, ...completedIds]);
  const handleDissolved = (chapterId: number) => {
    setDissolving((prev) => prev.filter((id) => id !== chapterId));
    onDismissChapters([chapterId]);
  };

  return (
    <motion.li
      layout
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25, ease: [0.22, 1, 0.36, 1] }}
      className="relative overflow-hidden rounded-2xl border bg-card shadow-sm"
    >
      {/* State-tinted spine. */}
      <span className={cn("absolute inset-y-0 left-0 w-1", style.accent)} />

      <div className="flex flex-wrap items-start justify-between gap-3 p-4 pl-5">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <h3 className="truncate text-base font-semibold tracking-tight">
              {lane.subject_name}
            </h3>
            <span className={cn("rounded-full px-2 py-0.5 text-[11px] font-medium", style.pill)}>
              {t(`queue.lane.states.${lane.state}`)}
            </span>
          </div>

          {/* Live provider / contention line. */}
          <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
            {lane.active_provider && lane.state !== "waiting" ? (
              <span className="inline-flex items-center gap-1.5">
                <span className={cn("size-2 rounded-full", provider.dot)} />
                <span className={provider.text}>{provider.label}</span>
              </span>
            ) : lane.state === "waiting" && lane.waiting_for ? (
              <span className="inline-flex items-center gap-1.5 text-warning">
                <Clock className="size-3.5" />
                {t("queue.lane.waitingFor", {
                  provider: providerInfo(lane.waiting_for).label,
                })}
              </span>
            ) : null}
            {lane.resume_at && <ResumeCountdown iso={lane.resume_at} />}
          </div>
        </div>

        <div className="flex shrink-0 items-center gap-3">
          <label className="flex cursor-pointer items-center gap-1.5 text-xs text-muted-foreground">
            <Moon className="size-3.5" />
            <span className="hidden sm:inline">{t("queue.lane.overnight")}</span>
            <Switch
              checked={lane.queue_state === "overnight"}
              disabled={busy || paused}
              onCheckedChange={(v) => onOvernightToggle(v)}
            />
          </label>
          <Button
            variant={paused ? "default" : "outline"}
            size="sm"
            disabled={busy}
            onClick={onPauseToggle}
          >
            {paused ? <Play className="size-4" /> : <Pause className="size-4" />}
            {paused ? t("queue.lane.resume") : t("queue.lane.pause")}
          </Button>
        </div>
      </div>

      {/* Counts. */}
      <div className="grid grid-cols-4 divide-x border-t text-center">
        <Count label={t("queue.lane.counts.ready")} value={lane.ready} tone="text-success" />
        <Count label={t("queue.lane.counts.processing")} value={lane.processing} tone="text-info" />
        <Count label={t("queue.lane.counts.queued")} value={lane.queued} tone="text-muted-foreground" />
        <Count label={t("queue.lane.counts.errored")} value={lane.error} tone="text-destructive" />
      </div>

      {/* Expand to reveal this subject's chapters with per-chapter pause/resume. */}
      {canExpand && (
        <>
          <button
            type="button"
            onClick={() => setExpanded((v) => !v)}
            aria-expanded={expanded}
            className="flex w-full items-center justify-center gap-1.5 border-t py-2 text-xs font-medium text-muted-foreground transition-colors hover:bg-muted/40 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring"
          >
            <ChevronDown
              className={cn("size-4 transition-transform", expanded && "rotate-180")}
            />
            {t("queue.chapters.title")}
            <span className="tabular-nums text-muted-foreground/70">({chapterCount})</span>
          </button>
          <AnimatePresence initial={false}>
            {expanded && (
              <motion.div
                key="chapters"
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: "auto", opacity: 1 }}
                exit={{ height: 0, opacity: 0 }}
                transition={{ duration: 0.2, ease: [0.22, 1, 0.36, 1] }}
                className="overflow-hidden border-t bg-muted/20"
              >
                <div className="space-y-3 p-4">
                  {completedIds.length > 0 && (
                    <div className="flex justify-end">
                      <button
                        type="button"
                        onClick={clearCompleted}
                        className="inline-flex items-center gap-1.5 rounded-full border border-success/30 bg-success/10 px-3 py-1 text-xs font-medium text-success transition-colors hover:bg-success/15 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                      >
                        <Sparkles className="size-3.5" />
                        {t("queue.chapters.clearCompleted")}
                        <span className="tabular-nums opacity-70">
                          ({completedIds.length})
                        </span>
                      </button>
                    </div>
                  )}
                  <ChapterGroups
                    groups={chapterGroups}
                    busy={chapterBusy}
                    dissolving={dissolving}
                    onSetState={onSetChapterState}
                    onDissolved={handleDissolved}
                  />
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </>
      )}
    </motion.li>
  );
}

function Count({ label, value, tone }: { label: string; value: number; tone: string }) {
  return (
    <div className="px-2 py-2.5">
      <p className={cn("text-lg font-semibold tabular-nums", value > 0 ? tone : "text-muted-foreground/50")}>
        {value}
      </p>
      <p className="text-[10px] uppercase tracking-wide text-muted-foreground">{label}</p>
    </div>
  );
}

function ResumeCountdown({ iso }: { iso: string }) {
  const { t } = useTranslation();
  const when = new Date(iso);
  const minutes = Math.max(0, Math.round((when.getTime() - Date.now()) / 60000));
  const time = when.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
  return (
    <span className="inline-flex items-center gap-1.5">
      <Clock className="size-3.5" />
      {minutes <= 0
        ? t("queue.lane.resumeShort", { time })
        : t("queue.lane.resumeShortMin", { time, minutes })}
    </span>
  );
}

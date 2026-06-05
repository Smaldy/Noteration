import { motion } from "framer-motion";
import { Clock, Moon, Pause, Play } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { cn } from "@/lib/utils";
import { providerInfo } from "@/lib/providers";
import type { LaneState, LaneStatus } from "@/types/lanes";

// Visual style per lane state; the label is resolved via i18n at render.
const STATE_STYLE: Record<LaneState, { accent: string; pill: string }> = {
  running: {
    accent: "bg-primary",
    pill: "bg-primary-soft text-primary-soft-foreground",
  },
  overnight: {
    accent: "bg-indigo-500",
    pill: "bg-indigo-500/12 text-indigo-700 dark:text-indigo-300",
  },
  waiting: {
    accent: "bg-amber-500",
    pill: "bg-amber-500/12 text-amber-700 dark:text-amber-300",
  },
  paused: {
    accent: "bg-muted-foreground/50",
    pill: "bg-muted text-muted-foreground",
  },
};

interface LaneCardProps {
  lane: LaneStatus;
  busy: boolean;
  onPauseToggle: () => void;
  onOvernightToggle: (enabled: boolean) => void;
}

export function LaneCard({ lane, busy, onPauseToggle, onOvernightToggle }: LaneCardProps) {
  const { t } = useTranslation();
  const style = STATE_STYLE[lane.state];
  const paused = lane.queue_state === "paused";
  const provider = providerInfo(lane.active_provider);

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
              <span className="inline-flex items-center gap-1.5 text-amber-700 dark:text-amber-300">
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
        <Count label={t("queue.lane.counts.ready")} value={lane.ready} tone="text-emerald-600" />
        <Count label={t("queue.lane.counts.processing")} value={lane.processing} tone="text-sky-600" />
        <Count label={t("queue.lane.counts.queued")} value={lane.queued} tone="text-muted-foreground" />
        <Count label={t("queue.lane.counts.errored")} value={lane.error} tone="text-destructive" />
      </div>
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

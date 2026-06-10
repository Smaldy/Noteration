import type { TFunction } from "i18next";
import { AlertCircle, ArrowLeft, Clock, RotateCw } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { cn } from "@/lib/utils";
import { useChaptersStore } from "@/stores/chapters";
import { useLanesStore } from "@/stores/lanes";
import { useQueueStore } from "@/stores/queue";
import { ClearHistoryMenu } from "./ClearHistoryMenu";
import { HistoryView } from "./HistoryView";
import { LaneCard } from "./LaneCard";
import { ProviderStrip } from "./ProviderStrip";

const POLL_MS = 5000;

export function QueuePage() {
  const navigate = useNavigate();
  const { t } = useTranslation();
  const [tab, setTab] = useState("lanes");

  const { status, error, retrying, fetchStatus, retryTopic } = useQueueStore();
  const lanes = useLanesStore((s) => s.status);
  const history = useLanesStore((s) => s.history);
  const busy = useLanesStore((s) => s.busy);
  const fetchLanes = useLanesStore((s) => s.fetchLanes);
  const fetchHistory = useLanesStore((s) => s.fetchHistory);
  const pauseLane = useLanesStore((s) => s.pauseLane);
  const resumeLane = useLanesStore((s) => s.resumeLane);
  const setOvernight = useLanesStore((s) => s.setOvernight);

  const chapterGroups = useChaptersStore((s) => s.groups);
  const chapterBusy = useChaptersStore((s) => s.busy);
  const dismissedChapters = useChaptersStore((s) => s.dismissed);
  const fetchChapters = useChaptersStore((s) => s.fetchGroups);
  const setChapterState = useChaptersStore((s) => s.setQueueState);
  const dismissChapters = useChaptersStore((s) => s.dismiss);

  // Hide chapters the user has cleared from the queue, then drop any now-empty
  // document group. (Dissolving-but-not-yet-committed chapters stay — they're
  // mid dust animation and dismissed only once it finishes.)
  const visibleGroups = chapterGroups
    .map((g) => ({
      ...g,
      chapters: g.chapters.filter((c) => !dismissedChapters.includes(c.id)),
    }))
    .filter((g) => g.chapters.length > 0);

  useEffect(() => {
    // Skip polling while the tab is hidden (no one's looking), and only fetch the
    // history feed when its tab is open — the lanes view never reads it.
    const tick = () => {
      if (document.hidden) return;
      void fetchStatus();
      void fetchLanes();
      void fetchChapters();
      if (tab === "history") void fetchHistory();
    };
    tick();
    const timer = setInterval(tick, POLL_MS);
    const onVisible = () => {
      if (!document.hidden) tick();
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      clearInterval(timer);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [tab, fetchStatus, fetchLanes, fetchHistory, fetchChapters]);

  const totalReady = status?.ready ?? 0;
  const totalQueued = status?.queued ?? 0;

  return (
    <div className="mx-auto max-w-3xl px-6 py-10">
      <button
        type="button"
        data-arcade-sector="library"
        onClick={() => navigate("/")}
        className="mb-4 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="size-4" />
        {t("common.library")}
      </button>

      <h1 className="text-3xl font-bold tracking-tight">{t("queue.title")}</h1>
      <p className="mt-1 text-sm text-muted-foreground">{t("queue.subtitle")}</p>

      <Tabs value={tab} onValueChange={setTab} className="mt-6">
        <TabsList>
          <TabsTrigger value="lanes">{t("queue.tabs.lanes")}</TabsTrigger>
          <TabsTrigger value="history">{t("queue.tabs.history")}</TabsTrigger>
        </TabsList>

        <TabsContent value="lanes" className="mt-5 space-y-5">
          {lanes && lanes.providers.length > 0 && (
            <ProviderStrip providers={lanes.providers} active={lanes.active_provider} />
          )}

          {/* Global never-zero-result summary. */}
          <p className="text-sm text-muted-foreground">
            <span className="font-medium text-emerald-600">
              {t("queue.ready", { count: totalReady })}
            </span>{" "}
            · {t("queue.queued", { count: totalQueued })}
            {status?.resume_at && ` · ${resumeSummary(status.resume_at, t)}`}
          </p>

          {status?.resume_at && (
            <Banner tone="amber" icon={<Clock className="mt-0.5 size-4 shrink-0 text-amber-600" />}>
              <p>{formatResume(status.resume_at, t)}</p>
              {status.paused_reason && (
                <p className="mt-1 line-clamp-3 text-xs text-muted-foreground">
                  {t("queue.providerSaid", { reason: status.paused_reason })}
                </p>
              )}
            </Banner>
          )}

          {status?.budget_paused && (
            <Banner tone="amber" icon={<AlertCircle className="mt-0.5 size-4 shrink-0 text-amber-600" />}>
              <p>
                {status.token_budget > 0
                  ? t("queue.budgetPausedWithTokens", {
                      spent: status.token_spent.toLocaleString(),
                      budget: status.token_budget.toLocaleString(),
                    })
                  : t("queue.budgetPaused")}
              </p>
              <p className="mt-1 text-xs text-muted-foreground">
                {t("queue.budgetRaise")}
              </p>
            </Banner>
          )}

          {lanes && lanes.lanes.length > 0 ? (
            <ul className="space-y-3">
              {lanes.lanes.map((lane) => (
                <LaneCard
                  key={lane.subject_id}
                  lane={lane}
                  busy={busy === lane.subject_id}
                  chapterGroups={visibleGroups.filter(
                    (g) => g.subject_id === lane.subject_id,
                  )}
                  chapterBusy={chapterBusy}
                  onSetChapterState={(chapterId, state) =>
                    void setChapterState(chapterId, state)
                  }
                  onDismissChapters={dismissChapters}
                  onPauseToggle={() =>
                    void (lane.queue_state === "paused"
                      ? resumeLane(lane.subject_id)
                      : pauseLane(lane.subject_id))
                  }
                  onOvernightToggle={(v) => void setOvernight(lane.subject_id, v)}
                />
              ))}
            </ul>
          ) : (
            <p className="text-sm text-muted-foreground">
              {error ?? t("queue.empty")}
            </p>
          )}

          {status && status.errors.length > 0 && (
            <section>
              <h2 className="flex items-center gap-2 text-sm font-semibold">
                <AlertCircle className="size-4 text-destructive" />
                {t("queue.needsAttention")}
              </h2>
              <ul className="mt-3 space-y-2">
                {status.errors.map((item) => (
                  <li
                    key={item.topic_id}
                    className="flex items-center justify-between gap-3 rounded-lg border border-destructive/30 bg-destructive/5 p-3"
                  >
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium">{item.title}</p>
                      {item.last_error && (
                        <p className="truncate text-xs text-muted-foreground">{item.last_error}</p>
                      )}
                    </div>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => void retryTopic(item.topic_id)}
                      disabled={retrying === item.topic_id}
                    >
                      <RotateCw className={cn(retrying === item.topic_id && "animate-spin")} />
                      {t("queue.retry")}
                    </Button>
                  </li>
                ))}
              </ul>
            </section>
          )}
        </TabsContent>

        <TabsContent value="history" className="mt-5">
          {history.length > 0 && (
            <div className="flex items-center justify-between gap-3 border-b border-border/60 pb-3">
              <p className="text-xs text-muted-foreground">
                {t("queue.events", { count: history.length })}
              </p>
              <ClearHistoryMenu />
            </div>
          )}
          <HistoryView events={history} />
        </TabsContent>
      </Tabs>
    </div>
  );
}

function Banner({
  tone,
  icon,
  children,
}: {
  tone: "amber";
  icon: ReactNode;
  children: ReactNode;
}) {
  return (
    <div
      className={cn(
        "flex items-start gap-2 rounded-lg border p-3 text-sm",
        tone === "amber" && "border-amber-500/30 bg-amber-500/5",
      )}
    >
      {icon}
      <div className="min-w-0">{children}</div>
    </div>
  );
}

function resumeSummary(iso: string, t: TFunction): string {
  const time = new Date(iso).toLocaleTimeString(undefined, {
    hour: "2-digit",
    minute: "2-digit",
  });
  return t("queue.resumeSummary", { time });
}

function formatResume(iso: string, t: TFunction): string {
  const when = new Date(iso);
  const minutes = Math.max(0, Math.round((when.getTime() - Date.now()) / 60000));
  const time = when.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
  if (minutes <= 0) return t("queue.resumeShortly", { time });
  return t("queue.resumeCooling", { time, minutes });
}

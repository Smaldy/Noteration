import { AlertCircle, ArrowLeft, Clock, RotateCw } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { cn } from "@/lib/utils";
import { useChaptersStore } from "@/stores/chapters";
import { useLanesStore } from "@/stores/lanes";
import { useQueueStore } from "@/stores/queue";
import { ChapterStatusList } from "./ChapterStatusList";
import { HistoryView } from "./HistoryView";
import { LaneCard } from "./LaneCard";
import { ProviderStrip } from "./ProviderStrip";

const POLL_MS = 5000;

export function QueuePage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [tab, setTab] = useState("lanes");
  const documentIdParam = searchParams.get("document_id");
  const documentId = documentIdParam ? Number(documentIdParam) : null;

  const { status, error, retrying, fetchStatus, retryTopic } = useQueueStore();
  const lanes = useLanesStore((s) => s.status);
  const history = useLanesStore((s) => s.history);
  const busy = useLanesStore((s) => s.busy);
  const fetchLanes = useLanesStore((s) => s.fetchLanes);
  const fetchHistory = useLanesStore((s) => s.fetchHistory);
  const pauseLane = useLanesStore((s) => s.pauseLane);
  const resumeLane = useLanesStore((s) => s.resumeLane);
  const setOvernight = useLanesStore((s) => s.setOvernight);

  const chapterStatuses = useChaptersStore((s) => s.statuses);
  const chapterBusy = useChaptersStore((s) => s.busy);
  const fetchChapters = useChaptersStore((s) => s.fetch);
  const setChapterState = useChaptersStore((s) => s.setQueueState);

  useEffect(() => {
    const tick = () => {
      void fetchStatus();
      void fetchLanes();
      void fetchHistory();
      if (documentId != null && Number.isFinite(documentId)) {
        void fetchChapters(documentId);
      }
    };
    tick();
    const timer = setInterval(tick, POLL_MS);
    return () => clearInterval(timer);
  }, [fetchStatus, fetchLanes, fetchHistory, fetchChapters, documentId]);

  const totalReady = status?.ready ?? 0;
  const totalQueued = status?.queued ?? 0;

  return (
    <div className="mx-auto max-w-3xl px-6 py-10">
      <button
        type="button"
        onClick={() => navigate("/")}
        className="mb-4 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="size-4" />
        Library
      </button>

      <h1 className="text-3xl font-bold tracking-tight">Processing queue</h1>
      <p className="mt-1 text-sm text-muted-foreground">
        Each subject runs its own lane — pause one to hand its model to another. Study
        what&apos;s ready now; the rest keeps going on free tiers.
      </p>

      <Tabs value={tab} onValueChange={setTab} className="mt-6">
        <TabsList>
          <TabsTrigger value="lanes">Lanes</TabsTrigger>
          <TabsTrigger value="history">History</TabsTrigger>
        </TabsList>

        <TabsContent value="lanes" className="mt-5 space-y-5">
          {lanes && lanes.providers.length > 0 && (
            <ProviderStrip providers={lanes.providers} active={lanes.active_provider} />
          )}

          {/* Global never-zero-result summary. */}
          <p className="text-sm text-muted-foreground">
            <span className="font-medium text-emerald-600">{totalReady} ready</span> ·{" "}
            {totalQueued} queued
            {status?.resume_at && ` · ${resumeSummary(status.resume_at)}`}
          </p>

          {status?.resume_at && (
            <Banner tone="amber" icon={<Clock className="mt-0.5 size-4 shrink-0 text-amber-600" />}>
              <p>{formatResume(status.resume_at)}</p>
              {status.paused_reason && (
                <p className="mt-1 line-clamp-3 text-xs text-muted-foreground">
                  Provider said: {status.paused_reason}
                </p>
              )}
            </Banner>
          )}

          {status?.budget_paused && (
            <Banner tone="amber" icon={<AlertCircle className="mt-0.5 size-4 shrink-0 text-amber-600" />}>
              <p>
                A document hit its token budget
                {status.token_budget > 0 &&
                  ` (~${status.token_spent.toLocaleString()} / ${status.token_budget.toLocaleString()} tokens)`}{" "}
                and is paused to protect your quota.
              </p>
              <p className="mt-1 text-xs text-muted-foreground">
                Raise the per-document token budget in Settings to continue.
              </p>
            </Banner>
          )}

          {documentId != null && (
            <ChapterStatusList
              statuses={chapterStatuses}
              busy={chapterBusy}
              onSetState={(chapterId, state) =>
                void setChapterState(chapterId, state)
              }
            />
          )}

          {lanes && lanes.lanes.length > 0 ? (
            <ul className="space-y-3">
              {lanes.lanes.map((lane) => (
                <LaneCard
                  key={lane.subject_id}
                  lane={lane}
                  busy={busy === lane.subject_id}
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
              {error ?? "Nothing in the queue yet. Upload a document to get started."}
            </p>
          )}

          {status && status.errors.length > 0 && (
            <section>
              <h2 className="flex items-center gap-2 text-sm font-semibold">
                <AlertCircle className="size-4 text-destructive" />
                Needs attention
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
                      Retry
                    </Button>
                  </li>
                ))}
              </ul>
            </section>
          )}
        </TabsContent>

        <TabsContent value="history" className="mt-5">
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

function resumeSummary(iso: string): string {
  const time = new Date(iso).toLocaleTimeString(undefined, {
    hour: "2-digit",
    minute: "2-digit",
  });
  return `resuming ~${time}`;
}

function formatResume(iso: string): string {
  const when = new Date(iso);
  const minutes = Math.max(0, Math.round((when.getTime() - Date.now()) / 60000));
  const time = when.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
  if (minutes <= 0) return `Resuming shortly (around ${time}).`;
  return `A provider quota is cooling — resuming around ${time} (~${minutes} min).`;
}

import { AlertCircle, ArrowLeft, Clock, RotateCw } from "lucide-react";
import { useEffect } from "react";
import { useNavigate } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { useQueueStore } from "@/stores/queue";

const POLL_MS = 5000;

export function QueuePage() {
  const navigate = useNavigate();
  const { status, loadState, error, retrying, fetchStatus, retryTopic } =
    useQueueStore();

  useEffect(() => {
    void fetchStatus();
    const timer = setInterval(() => void fetchStatus(), POLL_MS);
    return () => clearInterval(timer);
  }, [fetchStatus]);

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

      <h1 className="text-2xl font-semibold tracking-tight">Processing queue</h1>
      <p className="mt-1 text-sm text-muted-foreground">
        Topics generate in the background within free-tier budgets. Study what&apos;s
        ready now — the rest keeps going.
      </p>

      {loadState === "loading" && status === null && (
        <p className="mt-8 text-sm text-muted-foreground">Loading…</p>
      )}
      {loadState === "error" && status === null && (
        <p className="mt-8 text-sm text-destructive">{error}</p>
      )}

      {status && (
        <>
          <div className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
            <Stat label="Ready" value={status.ready} tone="ready" />
            <Stat label="Processing" value={status.processing} tone="processing" />
            <Stat label="Queued" value={status.queued} tone="queued" />
            <Stat label="Errored" value={status.error} tone="error" />
          </div>

          {status.resume_at && (
            <div className="mt-4 flex items-center gap-2 rounded-lg border bg-muted/40 p-3 text-sm">
              <Clock className="size-4 text-muted-foreground" />
              <span>{formatResume(status.resume_at)}</span>
            </div>
          )}

          {status.errors.length > 0 && (
            <section className="mt-8">
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
                        <p className="truncate text-xs text-muted-foreground">
                          {item.last_error}
                        </p>
                      )}
                    </div>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => void retryTopic(item.topic_id)}
                      disabled={retrying === item.topic_id}
                    >
                      <RotateCw
                        className={cn(retrying === item.topic_id && "animate-spin")}
                      />
                      Retry
                    </Button>
                  </li>
                ))}
              </ul>
            </section>
          )}

          {status.total === 0 && (
            <p className="mt-8 text-sm text-muted-foreground">
              Nothing in the queue yet. Upload a document to get started.
            </p>
          )}
        </>
      )}
    </div>
  );
}

const TONES: Record<string, string> = {
  ready: "text-emerald-600",
  processing: "text-sky-600",
  queued: "text-muted-foreground",
  error: "text-destructive",
};

function Stat({
  label,
  value,
  tone,
}: {
  label: string;
  value: number;
  tone: keyof typeof TONES;
}) {
  return (
    <div className="rounded-xl border p-4">
      <p className={cn("text-2xl font-semibold", TONES[tone])}>{value}</p>
      <p className="text-xs text-muted-foreground">{label}</p>
    </div>
  );
}

function formatResume(iso: string): string {
  const when = new Date(iso);
  const minutes = Math.max(0, Math.round((when.getTime() - Date.now()) / 60000));
  const time = when.toLocaleTimeString(undefined, {
    hour: "2-digit",
    minute: "2-digit",
  });
  if (minutes <= 0) return `Resuming shortly (around ${time}).`;
  return `A provider quota is cooling — resuming around ${time} (~${minutes} min).`;
}

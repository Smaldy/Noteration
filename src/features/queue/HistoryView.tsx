import { ArrowRight, Sparkles } from "lucide-react";

import { cn } from "@/lib/utils";
import { providerInfo } from "@/lib/providers";
import type { HistoryEvent } from "@/types/lanes";

/**
 * The cost-visibility / transparency surface that replaces notifications: a
 * chronological log of provider switches and per-topic generations (which topic,
 * which provider, how long it took).
 */
export function HistoryView({ events }: { events: HistoryEvent[] }) {
  if (events.length === 0) {
    return (
      <p className="mt-10 text-center text-sm text-muted-foreground">
        No generation history yet. As topics are generated, what produced them — and
        every provider switch — shows up here.
      </p>
    );
  }

  return (
    <ol className="mt-2 space-y-1">
      {events.map((event) => (
        <li key={event.id} className="flex gap-3">
          <Rail event={event} />
          <Row event={event} />
        </li>
      ))}
    </ol>
  );
}

function Rail({ event }: { event: HistoryEvent }) {
  const isSwitch = event.event_type === "provider_switch";
  const info = providerInfo(event.provider_to);
  return (
    <div className="flex w-4 flex-col items-center">
      <span className="mt-3.5 size-2 shrink-0 rounded-full ring-4 ring-card">
        <span className={cn("block size-2 rounded-full", isSwitch ? "bg-foreground/60" : info.dot)} />
      </span>
      <span className="w-px flex-1 bg-border" />
    </div>
  );
}

function Row({ event }: { event: HistoryEvent }) {
  const time = new Date(event.created_at).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });

  if (event.event_type === "provider_switch") {
    const from = providerInfo(event.provider_from);
    const to = providerInfo(event.provider_to);
    return (
      <div className="flex flex-1 flex-wrap items-center gap-x-2 gap-y-1 pb-4 text-sm">
        <span className="font-medium text-muted-foreground">Switched provider</span>
        <span className={cn("inline-flex items-center gap-1", from.text)}>
          <span className={cn("size-1.5 rounded-full", from.dot)} />
          {from.label}
        </span>
        <ArrowRight className="size-3.5 text-muted-foreground" />
        <span className={cn("inline-flex items-center gap-1 font-medium", to.text)}>
          <span className={cn("size-1.5 rounded-full", to.dot)} />
          {to.label}
        </span>
        <span className="ml-auto shrink-0 text-xs tabular-nums text-muted-foreground">{time}</span>
      </div>
    );
  }

  const provider = providerInfo(event.provider_to);
  return (
    <div className="flex flex-1 flex-wrap items-baseline gap-x-2 gap-y-1 pb-4 text-sm">
      <Sparkles className="size-3.5 shrink-0 translate-y-0.5 text-primary/70" />
      <span className="font-medium">{event.topic_title ?? "Topic generated"}</span>
      {event.subject_name && (
        <span className="text-xs text-muted-foreground">· {event.subject_name}</span>
      )}
      <span className={cn("inline-flex items-center gap-1 text-xs", provider.text)}>
        <span className={cn("size-1.5 rounded-full", provider.dot)} />
        {provider.label}
      </span>
      {event.detail && (
        <span className="text-xs tabular-nums text-muted-foreground">· {event.detail}</span>
      )}
      <span className="ml-auto shrink-0 text-xs tabular-nums text-muted-foreground">{time}</span>
    </div>
  );
}

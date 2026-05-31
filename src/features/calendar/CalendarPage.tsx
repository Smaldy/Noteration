import type {
  DatesSetArg,
  EventClickArg,
  EventDropArg,
  EventInput,
} from "@fullcalendar/core";
import daygridPlugin from "@fullcalendar/daygrid";
import interactionPlugin from "@fullcalendar/interaction";
import FullCalendar from "@fullcalendar/react";
import { ArrowLeft } from "lucide-react";
import { useMemo } from "react";
import { useNavigate } from "react-router-dom";

import { useCalendarStore } from "@/stores/calendar";
import type { CalendarEntry } from "@/types/calendar";

// Distinct colors: revision-buffer days stand out; otherwise by schedule source.
function colorFor(entry: CalendarEntry): string {
  if (entry.is_revision_buffer) return "#f59e0b"; // amber
  if (entry.source === "deadline") return "#f43f5e"; // rose
  if (entry.source === "manual") return "#8b5cf6"; // violet
  return "#6366f1"; // indigo (sm2)
}

export function CalendarPage() {
  const navigate = useNavigate();
  const { entries, error, fetchRange, reschedule } = useCalendarStore();

  const events = useMemo<EventInput[]>(
    () =>
      entries.map((entry) => ({
        id: String(entry.id),
        title: entry.is_revision_buffer
          ? `${entry.topic_title} (buffer)`
          : entry.topic_title,
        start: entry.date,
        allDay: true,
        backgroundColor: colorFor(entry),
        borderColor: colorFor(entry),
        extendedProps: {
          documentId: entry.document_id,
          topicId: entry.topic_id,
        },
      })),
    [entries],
  );

  function onDatesSet(arg: DatesSetArg) {
    void fetchRange(arg.startStr.slice(0, 10), arg.endStr.slice(0, 10));
  }

  function onEventClick(arg: EventClickArg) {
    const { documentId, topicId } = arg.event.extendedProps as {
      documentId: number;
      topicId: number;
    };
    navigate(`/documents/${documentId}/study/${topicId}`);
  }

  async function onEventDrop(arg: EventDropArg) {
    const date = arg.event.startStr.slice(0, 10);
    try {
      await reschedule(Number(arg.event.id), date);
    } catch {
      arg.revert(); // keep the UI consistent with the server
    }
  }

  return (
    <div className="mx-auto max-w-5xl animate-rise px-6 py-8">
      <button
        type="button"
        onClick={() => navigate("/")}
        className="mb-5 inline-flex items-center gap-1.5 text-sm font-medium text-muted-foreground transition-colors hover:text-foreground"
      >
        <ArrowLeft className="size-4" />
        Library
      </button>

      <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Calendar</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Scheduled reviews. Drag a session to reschedule, or click one to study it.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5">
          {LEGEND.map((l) => (
            <span key={l.label} className="inline-flex items-center gap-1.5 text-xs text-muted-foreground">
              <span className="size-2.5 rounded-full" style={{ backgroundColor: l.color }} />
              {l.label}
            </span>
          ))}
        </div>
      </div>

      {error && (
        <p className="mb-4 rounded-lg border border-destructive/40 bg-destructive/5 px-3 py-2 text-sm text-destructive">
          {error}
        </p>
      )}

      <div className="rounded-2xl border bg-card/70 p-4 shadow-sm sm:p-6">
        <FullCalendar
          plugins={[daygridPlugin, interactionPlugin]}
          initialView="dayGridMonth"
          height="auto"
          editable
          eventStartEditable
          eventDurationEditable={false}
          events={events}
          datesSet={onDatesSet}
          eventClick={onEventClick}
          eventDrop={onEventDrop}
          headerToolbar={{ left: "prev,next today", center: "title", right: "" }}
        />
      </div>
    </div>
  );
}

// Mirrors `colorFor` so the legend explains what each event color means.
const LEGEND: { label: string; color: string }[] = [
  { label: "Review (SM-2)", color: "#6366f1" },
  { label: "Manual", color: "#8b5cf6" },
  { label: "Deadline", color: "#f43f5e" },
  { label: "Revision buffer", color: "#f59e0b" },
];

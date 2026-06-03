import type {
  DatesSetArg,
  EventClickArg,
  EventContentArg,
  EventDropArg,
  EventInput,
} from "@fullcalendar/core";
import daygridPlugin from "@fullcalendar/daygrid";
import interactionPlugin from "@fullcalendar/interaction";
import listPlugin from "@fullcalendar/list";
import FullCalendar from "@fullcalendar/react";
import { ArrowLeft, CalendarDays } from "lucide-react";
import { useMemo } from "react";
import { useNavigate } from "react-router-dom";

import { useCalendarStore } from "@/stores/calendar";
import type { CalendarEntry } from "@/types/calendar";

// The schedule "kind" drives a semantic colour class (styled in index.css).
function classFor(entry: CalendarEntry): string {
  if (entry.is_revision_buffer) return "fc-ev-buffer";
  if (entry.source === "deadline") return "fc-ev-deadline";
  if (entry.source === "manual") return "fc-ev-manual";
  return "fc-ev-sm2";
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
        classNames: [classFor(entry)],
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
    <div className="mx-auto flex h-[100dvh] max-w-[1500px] animate-rise flex-col px-6 py-5">
      <button
        type="button"
        onClick={() => navigate("/")}
        className="mb-3 inline-flex w-fit items-center gap-1.5 text-sm font-medium text-muted-foreground transition-colors hover:text-foreground"
      >
        <ArrowLeft className="size-4" />
        Library
      </button>

      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <h1 className="flex items-center gap-2.5 text-2xl font-bold tracking-tight">
          <span className="grid size-9 place-items-center rounded-xl bg-primary-soft text-primary-soft-foreground">
            <CalendarDays className="size-5" />
          </span>
          Calendar
        </h1>
        <p className="text-sm text-muted-foreground">
          Drag a session to reschedule, or click one to study it.
        </p>
      </div>

      {error && (
        <p className="mb-3 rounded-lg border border-destructive/40 bg-destructive/5 px-3 py-2 text-sm text-destructive">
          {error}
        </p>
      )}

      {/* The card fills the remaining viewport height so the calendar uses the
          whole screen — tall month/week cells, a full-width agenda for Day. */}
      <div className="flex min-h-0 flex-1 flex-col rounded-2xl border bg-card/70 p-4 shadow-sm backdrop-blur-sm sm:p-5">
        <div className="min-h-0 flex-1">
          <FullCalendar
            plugins={[daygridPlugin, interactionPlugin, listPlugin]}
            initialView="dayGridMonth"
            height="100%"
            expandRows
            editable
            eventStartEditable
            eventDurationEditable={false}
            fixedWeekCount={false}
            views={{
              dayGridMonth: { dayMaxEvents: true, buttonText: "Month" },
              dayGridWeek: { dayMaxEvents: true, buttonText: "Week" },
              listDay: { buttonText: "Day" },
            }}
            events={events}
            eventContent={renderChip}
            datesSet={onDatesSet}
            eventClick={onEventClick}
            eventDrop={onEventDrop}
            noEventsText="No sessions scheduled for this day."
            headerToolbar={{
              left: "title",
              center: "dayGridMonth,dayGridWeek,listDay",
              right: "prev,next today",
            }}
            buttonText={{ today: "Today" }}
          />
        </div>

        <div className="mt-4 flex shrink-0 flex-wrap items-center gap-x-5 gap-y-2 border-t pt-3.5">
          {LEGEND.map((l) => (
            <span
              key={l.label}
              className="inline-flex items-center gap-2 text-xs font-medium text-muted-foreground"
            >
              <span
                className="size-2.5 rounded-full"
                style={{ backgroundColor: l.color }}
              />
              {l.label}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}

// In daygrid, a soft tinted chip with a leading dot; in the agenda list, just the
// title (the list row supplies its own coloured dot + layout).
function renderChip(arg: EventContentArg) {
  if (arg.view.type.startsWith("list")) {
    return <span className="cal-list-title">{arg.event.title}</span>;
  }
  return (
    <div className="cal-chip">
      <span className="cal-dot" />
      <span className="cal-chip-label">{arg.event.title}</span>
    </div>
  );
}

// Mirrors `classFor` / the CSS `--cal-*` tokens so the legend explains each colour.
const LEGEND: { label: string; color: string }[] = [
  { label: "Review (SM-2)", color: "var(--cal-sm2)" },
  { label: "Manual", color: "var(--cal-manual)" },
  { label: "Deadline", color: "var(--cal-deadline)" },
  { label: "Revision buffer", color: "var(--cal-buffer)" },
];

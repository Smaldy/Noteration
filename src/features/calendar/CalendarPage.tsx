import type {
  DateClickArg,
} from "@fullcalendar/interaction";
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
import { ArrowLeft, CalendarDays, Check, Plus, Sparkles, X } from "lucide-react";
import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { useCalendarStore } from "@/stores/calendar";
import type { CalendarEntry } from "@/types/calendar";

import { AddToCalendarDialog } from "./AddToCalendarDialog";
import { AiPlanDialog } from "./AiPlanDialog";
import { EditEventDialog } from "./EditEventDialog";

// The schedule "kind" drives a semantic colour class (styled in index.css).
function classFor(entry: CalendarEntry): string {
  if (entry.is_deadline) return "fc-ev-exam"; // bloody red — wins over everything
  if (entry.is_revision_buffer) return "fc-ev-buffer";
  if (entry.source === "deadline") return "fc-ev-deadline";
  if (entry.source === "ai") return "fc-ev-ai";
  if (entry.source === "manual") {
    return entry.kind === "custom" ? "fc-ev-custom" : "fc-ev-manual";
  }
  return "fc-ev-sm2";
}

export function CalendarPage() {
  const navigate = useNavigate();
  const { entries, error, fetchRange, reschedule, toggleCompleted, deleteEntry } =
    useCalendarStore();

  const [addOpen, setAddOpen] = useState(false);
  const [addDate, setAddDate] = useState<string | undefined>(undefined);
  const [planOpen, setPlanOpen] = useState(false);
  const [editEntry, setEditEntry] = useState<CalendarEntry | null>(null);

  const events = useMemo<EventInput[]>(
    () =>
      entries.map((entry) => ({
        id: String(entry.id),
        title: entry.title,
        start: entry.date,
        allDay: true,
        classNames: [classFor(entry), entry.completed && "fc-ev-done"].filter(
          Boolean,
        ) as string[],
        extendedProps: { entry },
      })),
    [entries],
  );

  function onDatesSet(arg: DatesSetArg) {
    void fetchRange(arg.startStr.slice(0, 10), arg.endStr.slice(0, 10));
  }

  function onDateClick(arg: DateClickArg) {
    setAddDate(arg.dateStr.slice(0, 10));
    setAddOpen(true);
  }

  function onEventClick(arg: EventClickArg) {
    const entry = arg.event.extendedProps.entry as CalendarEntry;
    // A topic session deep-links into the Study View; subject/custom events
    // open the editor (there's no single topic to open).
    if (entry.kind === "topic" && entry.document_id && entry.topic_id) {
      navigate(`/documents/${entry.document_id}/study/${entry.topic_id}`);
    } else {
      setEditEntry(entry);
    }
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
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            onClick={() => setPlanOpen(true)}
            title="Let AI plan a subject's study schedule"
          >
            <Sparkles className="size-4" />
            AI study plan
          </Button>
          <Button
            onClick={() => {
              setAddDate(undefined);
              setAddOpen(true);
            }}
          >
            <Plus className="size-4" />
            Add to calendar
          </Button>
        </div>
      </div>

      <p className="mb-3 text-sm text-muted-foreground">
        Click a day to add an event, drag a session to reschedule, or check one
        off when you've studied it. Click a topic to open it.
      </p>

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
            eventContent={(arg) => renderChip(arg, toggleCompleted, deleteEntry)}
            datesSet={onDatesSet}
            dateClick={onDateClick}
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

      <AddToCalendarDialog
        open={addOpen}
        onOpenChange={setAddOpen}
        presetDate={addDate}
      />
      <AiPlanDialog open={planOpen} onOpenChange={setPlanOpen} />
      <EditEventDialog entry={editEntry} onClose={() => setEditEntry(null)} />
    </div>
  );
}

// A "studied" checkbox (toggles completion; green when on time, amber when late)
// + the title + a hover delete. Deadlines have no checkbox (you don't "study" a
// deadline). In the agenda list the row supplies its own dot/layout.
function renderChip(
  arg: EventContentArg,
  toggle: (id: number, completed: boolean) => Promise<void>,
  remove: (id: number) => Promise<void>,
) {
  const entry = arg.event.extendedProps.entry as CalendarEntry;
  const list = arg.view.type.startsWith("list");

  const checkbox = entry.is_deadline ? null : (
    <button
      type="button"
      onClick={(e) => {
        e.stopPropagation();
        void toggle(entry.id, !entry.completed);
      }}
      title={entry.completed ? "Mark as not studied" : "Mark as studied"}
      aria-label={entry.completed ? "Mark as not studied" : "Mark as studied"}
      className={cn(
        "grid size-4 shrink-0 place-items-center rounded border transition-colors",
        entry.completed
          ? entry.on_time === false
            ? "border-amber-500 bg-amber-500 text-white"
            : "border-emerald-500 bg-emerald-500 text-white"
          : "border-current/40 hover:border-current",
      )}
    >
      {entry.completed && <Check className="size-3" strokeWidth={3} />}
    </button>
  );

  const remover = (
    <button
      type="button"
      onClick={(e) => {
        e.stopPropagation();
        if (
          window.confirm(`Remove "${entry.title}" from the calendar?`)
        ) {
          void remove(entry.id);
        }
      }}
      title="Remove from calendar"
      aria-label="Remove from calendar"
      className="grid size-4 shrink-0 place-items-center rounded opacity-0 transition-opacity hover:bg-black/10 group-hover/chip:opacity-70 hover:!opacity-100"
    >
      <X className="size-3" strokeWidth={2.5} />
    </button>
  );

  if (list) {
    return (
      <span className="group/chip flex items-center gap-2">
        {checkbox}
        <span
          className={cn(
            "cal-list-title flex-1",
            entry.completed && "line-through opacity-60",
          )}
        >
          {entry.title}
        </span>
        {remover}
      </span>
    );
  }
  return (
    <div className="cal-chip group/chip">
      {checkbox}
      <span
        className={cn(
          "cal-chip-label flex-1",
          entry.completed && "line-through opacity-60",
        )}
      >
        {entry.title}
      </span>
      {remover}
    </div>
  );
}

// Mirrors `classFor` / the CSS `--cal-*` tokens so the legend explains each colour.
const LEGEND: { label: string; color: string }[] = [
  { label: "Exam / deadline", color: "var(--cal-exam)" },
  { label: "Review (SM-2)", color: "var(--cal-sm2)" },
  { label: "AI plan", color: "var(--cal-ai)" },
  { label: "Topic / moved", color: "var(--cal-manual)" },
  { label: "Custom event", color: "var(--cal-custom)" },
  { label: "Revision buffer", color: "var(--cal-buffer)" },
];

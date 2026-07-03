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
import esLocale from "@fullcalendar/core/locales/es";
import itLocale from "@fullcalendar/core/locales/it";
import daygridPlugin from "@fullcalendar/daygrid";
import interactionPlugin from "@fullcalendar/interaction";
import listPlugin from "@fullcalendar/list";
import FullCalendar from "@fullcalendar/react";
import timeGridPlugin from "@fullcalendar/timegrid";
import { CalendarDays, Check, Plus, Sparkles, X } from "lucide-react";
import type { TFunction } from "i18next";
import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { BackLink } from "@/components/PageShell";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { useCalendarStore } from "@/stores/calendar";
import { useSettingsStore } from "@/stores/settings";
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

// Whether the Day button shows an hourly time-grid (`true`) or an agenda list
// (`false`). Persisted so the choice survives reloads; toggled by double-clicking
// the Day button.
const DAY_MODE_KEY = "noteration.calendarDayHourly";

function loadDayHourly(): boolean {
  try {
    return localStorage.getItem(DAY_MODE_KEY) === "1";
  } catch {
    return false;
  }
}

function pad2(n: number): string {
  return String(n).padStart(2, "0");
}

// Hoisted to module scope so the reference is stable across renders. Passing a
// fresh array inline made FullCalendar rebuild its DateEnv every render, which
// re-fired `datesSet` → fetchRange → setState → re-render → infinite loop.
const FC_LOCALES = [itLocale, esLocale];

export function CalendarPage() {
  const navigate = useNavigate();
  const { t, i18n } = useTranslation();
  const { entries, error, fetchRange, reschedule, toggleCompleted, deleteEntry } =
    useCalendarStore();
  const settings = useSettingsStore((s) => s.settings);
  const fetchSettings = useSettingsStore((s) => s.fetchSettings);

  const calendarRef = useRef<FullCalendar>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  const [addOpen, setAddOpen] = useState(false);
  const [addDate, setAddDate] = useState<string | undefined>(undefined);
  const [addTime, setAddTime] = useState<string | undefined>(undefined);
  const [planOpen, setPlanOpen] = useState(false);
  const [editEntry, setEditEntry] = useState<CalendarEntry | null>(null);
  const [dayHourly, setDayHourly] = useState(loadDayHourly);

  // Make sure the day-view config (range + slot gap) is available even if the
  // user deep-links straight to /calendar before the app-boot fetch lands.
  useEffect(() => {
    if (!settings) void fetchSettings();
  }, [settings, fetchSettings]);

  // The hourly window + slot gap, clamped to a sane, ordered range.
  const startHour = Math.min(23, Math.max(0, settings?.calendar_day_start_hour ?? 8));
  const endHour = Math.min(
    24,
    Math.max(startHour + 1, settings?.calendar_day_end_hour ?? 23),
  );
  const slotMinutes = settings?.calendar_slot_minutes ?? 60;

  const dayViewName = dayHourly ? "timeGridDay" : "listDay";

  const events = useMemo<EventInput[]>(
    () =>
      entries.map((entry) => {
        const timed = entry.start_time != null;
        return {
          id: String(entry.id),
          title: entry.title,
          // A timed entry carries a real start datetime so it lands on its hour
          // in the time-grid; an all-day entry stays date-only.
          start: timed ? `${entry.date}T${entry.start_time}:00` : entry.date,
          allDay: !timed,
          classNames: [classFor(entry), entry.completed && "fc-ev-done"].filter(
            Boolean,
          ) as string[],
          extendedProps: { entry },
        };
      }),
    [entries],
  );

  // Re-attach a dblclick handler to the Day toolbar button after every render
  // (its class flips between fc-listDay-button / fc-timeGridDay-button when the
  // mode changes, so the element is replaced). Double-click toggles hourly mode.
  useEffect(() => {
    const root = containerRef.current;
    if (!root) return;
    const btn = root.querySelector<HTMLButtonElement>(
      ".fc-listDay-button, .fc-timeGridDay-button",
    );
    if (!btn) return;
    const onDbl = (e: MouseEvent) => {
      e.preventDefault();
      toggleDayMode();
    };
    btn.addEventListener("dblclick", onDbl);
    return () => btn.removeEventListener("dblclick", onDbl);
    // The Day button element is replaced when its mode flips, so re-attach only
    // when `dayHourly` changes (not on every render).
  }, [dayHourly]);

  function toggleDayMode() {
    setDayHourly((hourly) => {
      const next = !hourly;
      try {
        localStorage.setItem(DAY_MODE_KEY, next ? "1" : "0");
      } catch {
        /* ignore storage failures */
      }
      // If a Day view is open, switch it live to the toggled variant.
      const api = calendarRef.current?.getApi();
      if (api && api.view.type.endsWith("Day") && !api.view.type.startsWith("dayGrid")) {
        api.changeView(next ? "timeGridDay" : "listDay");
      }
      return next;
    });
  }

  function onDatesSet(arg: DatesSetArg) {
    void fetchRange(arg.startStr.slice(0, 10), arg.endStr.slice(0, 10));
  }

  function onDateClick(arg: DateClickArg) {
    setAddDate(arg.dateStr.slice(0, 10));
    // In the hourly grid a slot click carries a time → prefill it.
    const timed = !arg.allDay && arg.date != null;
    setAddTime(
      timed ? `${pad2(arg.date.getHours())}:${pad2(arg.date.getMinutes())}` : undefined,
    );
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
    const start = arg.event.start;
    const date = arg.event.startStr.slice(0, 10);
    // Dropped onto an hour (time-grid, or a still-timed event moved across days)
    // → carry the new time; dropped into an all-day slot → clear it (null). A
    // plain all-day event stays all-day (null is a no-op for it).
    const time =
      !arg.event.allDay && start
        ? `${pad2(start.getHours())}:${pad2(start.getMinutes())}`
        : null;
    try {
      await reschedule(Number(arg.event.id), date, time);
    } catch {
      arg.revert(); // keep the UI consistent with the server
    }
  }

  return (
    <div className="mx-auto flex h-[100dvh] max-w-[1500px] animate-rise flex-col px-6 py-5">
      <BackLink className="mb-3 w-fit" />

      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <h1 className="flex items-center gap-2.5 text-3xl font-bold tracking-tight">
          <span className="grid size-10 place-items-center rounded-xl bg-primary-soft text-primary-soft-foreground">
            <CalendarDays className="size-5" />
          </span>
          {t("calendar.title")}
        </h1>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            onClick={() => setPlanOpen(true)}
            title={t("calendar.aiPlanTitle")}
          >
            <Sparkles className="size-4" />
            {t("calendar.aiPlan")}
          </Button>
          <Button
            onClick={() => {
              setAddDate(undefined);
              setAddTime(undefined);
              setAddOpen(true);
            }}
          >
            <Plus className="size-4" />
            {t("calendar.add")}
          </Button>
        </div>
      </div>

      <p className="mb-3 text-sm text-muted-foreground">
        {t("calendar.help")}{" "}
        <span className="text-muted-foreground/80">{t("calendar.helpDayToggle")}</span>
      </p>

      {error && (
        <p className="mb-3 rounded-lg border border-destructive/40 bg-destructive/5 px-3 py-2 text-sm text-destructive">
          {error}
        </p>
      )}

      {/* The card fills the remaining viewport height so the calendar uses the
          whole screen — tall month/week cells, a full-width agenda for Day. */}
      <div className="flex min-h-0 flex-1 flex-col rounded-2xl border bg-card/70 p-4 shadow-sm backdrop-blur-sm sm:p-5">
        <div ref={containerRef} className="min-h-0 flex-1">
          <FullCalendar
            ref={calendarRef}
            plugins={[
              daygridPlugin,
              timeGridPlugin,
              interactionPlugin,
              listPlugin,
            ]}
            initialView="dayGridMonth"
            locales={FC_LOCALES}
            locale={i18n.language}
            height="100%"
            expandRows
            editable
            eventStartEditable
            eventDurationEditable={false}
            fixedWeekCount={false}
            nowIndicator
            slotMinTime={`${pad2(startHour)}:00:00`}
            slotMaxTime={`${pad2(endHour)}:00:00`}
            slotDuration={`${pad2(Math.floor(slotMinutes / 60))}:${pad2(
              slotMinutes % 60,
            )}:00`}
            scrollTime={`${pad2(startHour)}:00:00`}
            views={{
              dayGridMonth: { dayMaxEvents: true, buttonText: t("calendar.buttons.month") },
              dayGridWeek: { dayMaxEvents: true, buttonText: t("calendar.buttons.week") },
              listDay: { buttonText: t("calendar.buttons.day") },
              timeGridDay: { buttonText: t("calendar.buttons.day"), allDaySlot: true },
            }}
            events={events}
            eventContent={(arg) => renderChip(arg, t, toggleCompleted, deleteEntry)}
            datesSet={onDatesSet}
            dateClick={onDateClick}
            eventClick={onEventClick}
            eventDrop={onEventDrop}
            noEventsText={t("calendar.noEvents")}
            headerToolbar={{
              left: "title",
              center: `dayGridMonth,dayGridWeek,${dayViewName}`,
              right: "prev,next today",
            }}
            buttonText={{ today: t("calendar.buttons.today") }}
          />
        </div>

        <div className="mt-4 flex shrink-0 flex-wrap items-center gap-x-5 gap-y-2 border-t pt-3.5">
          {LEGEND.map((l) => (
            <span
              key={l.key}
              className="inline-flex items-center gap-2 text-xs font-medium text-muted-foreground"
            >
              <span
                className="size-2.5 rounded-full"
                style={{ backgroundColor: l.color }}
              />
              {t(`calendar.legend.${l.key}`)}
            </span>
          ))}
        </div>
      </div>

      <AddToCalendarDialog
        open={addOpen}
        onOpenChange={setAddOpen}
        presetDate={addDate}
        presetTime={addTime}
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
  t: TFunction,
  toggle: (id: number, completed: boolean) => Promise<void>,
  remove: (id: number) => Promise<void>,
) {
  const entry = arg.event.extendedProps.entry as CalendarEntry;
  const list = arg.view.type.startsWith("list");
  const timed = arg.view.type.startsWith("timeGrid");

  // A clean, tabular time prefix — strips the leading zero ("09:30" → "9:30").
  // Hidden in the time-grid (the row's vertical position already says the hour).
  const timeLabel =
    entry.start_time && !timed ? (
      <span className={list ? "cal-list-time" : "cal-chip-time"}>
        {`${Number(entry.start_time.slice(0, 2))}:${entry.start_time.slice(3)}`}
      </span>
    ) : null;

  const checkbox = entry.is_deadline ? null : (
    <button
      type="button"
      onClick={(e) => {
        e.stopPropagation();
        void toggle(entry.id, !entry.completed);
      }}
      title={entry.completed ? t("calendar.markNotStudied") : t("calendar.markStudied")}
      aria-label={
        entry.completed ? t("calendar.markNotStudied") : t("calendar.markStudied")
      }
      className={cn(
        "grid size-4 shrink-0 place-items-center rounded-sm border transition-colors",
        entry.completed
          ? entry.on_time === false
            ? "border-warning bg-warning text-white"
            : "border-success bg-success text-white"
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
        if (window.confirm(t("calendar.removeConfirm", { title: entry.title }))) {
          void remove(entry.id);
        }
      }}
      title={t("calendar.removeFromCalendar")}
      aria-label={t("calendar.removeFromCalendar")}
      className="grid size-4 shrink-0 place-items-center rounded-sm opacity-0 transition-opacity hover:bg-black/10 focus-visible:opacity-100 group-hover/chip:opacity-70 hover:!opacity-100"
    >
      <X className="size-3" strokeWidth={2.5} />
    </button>
  );

  if (list) {
    return (
      <span className="group/chip flex items-center gap-2.5">
        {checkbox}
        {timeLabel}
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
      {timeLabel}
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
// `key` indexes the localized label under calendar.legend.*.
const LEGEND: { key: string; color: string }[] = [
  { key: "examDeadline", color: "var(--cal-exam)" },
  { key: "reviewSm2", color: "var(--cal-sm2)" },
  { key: "aiPlan", color: "var(--cal-ai)" },
  { key: "topicMoved", color: "var(--cal-manual)" },
  { key: "customEvent", color: "var(--cal-custom)" },
  { key: "revisionBuffer", color: "var(--cal-buffer)" },
];

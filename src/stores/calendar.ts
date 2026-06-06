import { create } from "zustand";

import { ApiError, api } from "@/lib/api";
import type {
  CalendarEntry,
  CatalogSubject,
  ScheduleEntryCreate,
  ScheduleEntryUpdate,
} from "@/types/calendar";

type Load = "idle" | "loading" | "loaded" | "error";

interface CalendarStore {
  entries: CalendarEntry[];
  loadState: Load;
  error: string | null;
  /** The currently-displayed range, so mutations can refresh it. */
  range: { start: string; end: string } | null;

  /** Topic/subject catalog for the "study a topic" picker (lazy-loaded once). */
  catalog: CatalogSubject[];
  catalogLoaded: boolean;

  /** Load entries for a date range (inclusive YYYY-MM-DD). Skips the network
   *  call when the range is already loaded unless `force` is set. */
  fetchRange: (start: string, end: string, force?: boolean) => Promise<void>;
  /** Re-fetch the current range (after a mutation). */
  refresh: () => Promise<void>;
  /** Move an entry to a new date (and optionally a new start time, or `null` to
   *  clear it); throws on failure so the UI can revert. */
  reschedule: (
    entryId: number,
    date: string,
    startTime?: string | null,
  ) => Promise<void>;

  createEntry: (body: ScheduleEntryCreate) => Promise<CalendarEntry>;
  updateEntry: (entryId: number, body: ScheduleEntryUpdate) => Promise<CalendarEntry>;
  toggleCompleted: (entryId: number, completed: boolean) => Promise<void>;
  deleteEntry: (entryId: number) => Promise<void>;

  /** Force a catalog reload (e.g. after planning marks topics studied). */
  fetchCatalog: (force?: boolean) => Promise<void>;
  /** Generate an AI study plan for a subject; returns the created entries.
   *  `studiedTopicIds` (when given) are excluded from the plan and persisted. */
  generatePlan: (
    subjectId: number,
    studiedTopicIds?: number[],
  ) => Promise<CalendarEntry[]>;
  /** Delete a subject's AI plan; returns how many entries were removed. */
  deletePlan: (subjectId: number) => Promise<number>;
}

export const useCalendarStore = create<CalendarStore>((set, get) => ({
  entries: [],
  loadState: "idle",
  error: null,
  range: null,
  catalog: [],
  catalogLoaded: false,

  fetchRange: async (start, end, force = false) => {
    // Skip redundant refetches for a range we already hold — a fresh entries
    // array on every `datesSet` would otherwise re-render the calendar and
    // re-fire `datesSet`, forming an infinite loop. Mutations pass `force` via
    // `refresh()` to bypass this.
    const { range, loadState } = get();
    if (
      !force &&
      range &&
      range.start === start &&
      range.end === end &&
      (loadState === "loaded" || loadState === "loading")
    ) {
      // Already have this range, or a fetch for it is already in flight — skip the
      // refetch (and the duplicate concurrent GET). "error"/"idle" still retry.
      return;
    }
    if (get().entries.length === 0) set({ loadState: "loading" });
    set({ range: { start, end } });
    try {
      const entries = await api.get<CalendarEntry[]>(
        `/study/calendar?start=${start}&end=${end}`,
      );
      set({ entries, loadState: "loaded", error: null });
    } catch (err) {
      set({
        loadState: "error",
        error:
          err instanceof ApiError ? err.message : "Failed to load the calendar.",
      });
    }
  },

  refresh: async () => {
    const { range, fetchRange } = get();
    if (range) await fetchRange(range.start, range.end, true);
  },

  reschedule: async (entryId, date, startTime) => {
    const body: ScheduleEntryUpdate = { date };
    // undefined → leave the time unchanged; null → clear; "HH:MM" → set.
    if (startTime !== undefined) body.start_time = startTime;
    const updated = await api.patch<CalendarEntry>(
      `/study/schedule/${entryId}`,
      body,
    );
    set((state) => ({
      entries: state.entries.map((e) => (e.id === entryId ? updated : e)),
    }));
  },

  createEntry: async (body) => {
    const created = await api.post<CalendarEntry>("/study/schedule", body);
    await get().refresh();
    return created;
  },

  updateEntry: async (entryId, body) => {
    const updated = await api.patch<CalendarEntry>(
      `/study/schedule/${entryId}`,
      body,
    );
    set((state) => ({
      entries: state.entries.map((e) => (e.id === entryId ? updated : e)),
    }));
    return updated;
  },

  toggleCompleted: async (entryId, completed) => {
    // Optimistic: flip immediately, reconcile with the server response.
    set((state) => ({
      entries: state.entries.map((e) =>
        e.id === entryId ? { ...e, completed } : e,
      ),
    }));
    try {
      await get().updateEntry(entryId, { completed });
    } catch {
      set((state) => ({
        entries: state.entries.map((e) =>
          e.id === entryId ? { ...e, completed: !completed } : e,
        ),
      }));
    }
  },

  deleteEntry: async (entryId) => {
    await api.del(`/study/schedule/${entryId}`);
    set((state) => ({ entries: state.entries.filter((e) => e.id !== entryId) }));
  },

  fetchCatalog: async (force = false) => {
    if (get().catalogLoaded && !force) return;
    const catalog = await api.get<CatalogSubject[]>("/study/topic-catalog");
    set({ catalog, catalogLoaded: true });
  },

  generatePlan: async (subjectId, studiedTopicIds) => {
    const entries = await api.post<CalendarEntry[]>("/study/plan", {
      subject_id: subjectId,
      studied_topic_ids: studiedTopicIds ?? null,
    });
    // Topics may have been marked studied — keep the catalog fresh.
    await get().fetchCatalog(true);
    await get().refresh();
    return entries;
  },

  deletePlan: async (subjectId) => {
    const { deleted } = await api.del<{ deleted: number }>(
      `/study/plan/${subjectId}`,
    );
    await get().refresh();
    return deleted;
  },
}));

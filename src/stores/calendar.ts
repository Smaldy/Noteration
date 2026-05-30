import { create } from "zustand";

import { ApiError, api } from "@/lib/api";
import type { CalendarEntry } from "@/types/calendar";

type Load = "idle" | "loading" | "loaded" | "error";

interface CalendarStore {
  entries: CalendarEntry[];
  loadState: Load;
  error: string | null;
  /** Load entries for a date range (inclusive YYYY-MM-DD). */
  fetchRange: (start: string, end: string) => Promise<void>;
  /** Move an entry to a new date; throws on failure so the UI can revert. */
  reschedule: (entryId: number, date: string) => Promise<void>;
}

export const useCalendarStore = create<CalendarStore>((set, get) => ({
  entries: [],
  loadState: "idle",
  error: null,

  fetchRange: async (start, end) => {
    if (get().entries.length === 0) set({ loadState: "loading" });
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

  reschedule: async (entryId, date) => {
    const updated = await api.patch<CalendarEntry>(
      `/study/schedule/${entryId}`,
      { date },
    );
    set((state) => ({
      entries: state.entries.map((e) => (e.id === entryId ? updated : e)),
    }));
  },
}));

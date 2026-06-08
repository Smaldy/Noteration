import { create } from "zustand";

import { api } from "@/lib/api";
import type {
  ChapterQueueState,
  DocumentChapters,
} from "@/types/chapter";

// Completed chapters the user has "cleared" from the queue. Persisted so they stay
// gone across the 5s poll and app restarts (the data itself lives on in the Library;
// this only hides finished chapters from the active queue view).
const DISMISS_KEY = "noteration.queue.dismissedChapters";

function loadDismissed(): number[] {
  try {
    const raw = localStorage.getItem(DISMISS_KEY);
    const ids = raw ? (JSON.parse(raw) as unknown) : [];
    return Array.isArray(ids) ? ids.filter((n): n is number => typeof n === "number") : [];
  } catch {
    return [];
  }
}

function saveDismissed(ids: number[]): void {
  try {
    localStorage.setItem(DISMISS_KEY, JSON.stringify(ids));
  } catch {
    // Best-effort: a full/blocked localStorage just means dismissals don't persist.
  }
}

interface ChaptersState {
  /** Chapter lanes for every in-progress book, grouped by document. */
  groups: DocumentChapters[];
  busy: number | null; // chapter id mid pause/resume
  error: string | null;
  /** Completed chapter ids the user has cleared from the queue (hidden in the view). */
  dismissed: number[];
  /** Fetch (or refresh) the per-book chapter lanes shown on the Queue page. */
  fetchGroups: () => Promise<void>;
  /** PATCH a chapter lane, then refresh the grouped statuses. */
  setQueueState: (chapterId: number, state: ChapterQueueState) => Promise<void>;
  /** Hide a set of completed chapters from the queue (after the dust animation). */
  dismiss: (chapterIds: number[]) => void;
}

export const useChaptersStore = create<ChaptersState>((set, get) => ({
  groups: [],
  busy: null,
  error: null,
  dismissed: loadDismissed(),

  fetchGroups: async () => {
    try {
      const groups = await api.get<DocumentChapters[]>("/queue/chapters");
      set({ groups, error: null });
    } catch {
      set({ error: "Could not load chapter status." });
    }
  },

  setQueueState: async (chapterId, state) => {
    set({ busy: chapterId });
    try {
      await api.patch(`/chapters/${chapterId}/queue_state`, { queue_state: state });
      await get().fetchGroups();
    } finally {
      set({ busy: null });
    }
  },

  dismiss: (chapterIds) => {
    const next = Array.from(new Set([...get().dismissed, ...chapterIds]));
    saveDismissed(next);
    set({ dismissed: next });
  },
}));

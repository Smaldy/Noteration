import { create } from "zustand";

import { api } from "@/lib/api";
import type {
  ChapterQueueState,
  DocumentChapters,
} from "@/types/chapter";

interface ChaptersState {
  /** Chapter lanes for every in-progress book, grouped by document. */
  groups: DocumentChapters[];
  busy: number | null; // chapter id mid pause/resume
  error: string | null;
  /** Fetch (or refresh) the per-book chapter lanes shown on the Queue page. */
  fetchGroups: () => Promise<void>;
  /** PATCH a chapter lane, then refresh the grouped statuses. */
  setQueueState: (chapterId: number, state: ChapterQueueState) => Promise<void>;
}

export const useChaptersStore = create<ChaptersState>((set, get) => ({
  groups: [],
  busy: null,
  error: null,

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
}));

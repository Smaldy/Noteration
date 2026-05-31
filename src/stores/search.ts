import { create } from "zustand";

import { ApiError, api } from "@/lib/api";
import type { SearchResult } from "@/types/search";

interface SearchStore {
  results: SearchResult[];
  loading: boolean;
  error: string | null;
  /** Run a search; later calls win (out-of-order responses are dropped). */
  search: (query: string, subjectId: number | null) => Promise<void>;
  /** Clear results and invalidate any in-flight request. */
  reset: () => void;
}

// Monotonic request id so a slow earlier response can't overwrite a newer one.
let seq = 0;

export const useSearchStore = create<SearchStore>((set) => ({
  results: [],
  loading: false,
  error: null,

  search: async (query, subjectId) => {
    const q = query.trim();
    if (!q) {
      seq++;
      set({ results: [], loading: false, error: null });
      return;
    }
    const mine = ++seq;
    set({ loading: true, error: null });
    try {
      const params = new URLSearchParams({ q });
      if (subjectId != null) params.set("subject_id", String(subjectId));
      const results = await api.get<SearchResult[]>(`/search?${params.toString()}`);
      if (mine === seq) set({ results, loading: false });
    } catch (err) {
      if (mine === seq) {
        set({
          loading: false,
          error: err instanceof ApiError ? err.message : "Search failed.",
        });
      }
    }
  },

  reset: () => {
    seq++;
    set({ results: [], loading: false, error: null });
  },
}));

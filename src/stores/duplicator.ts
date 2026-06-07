import { create } from "zustand";

import { ApiError, api } from "@/lib/api";
import type { ExerciseSession } from "@/types/duplicator";

const POLL_MS = 4000;

/** A session whose every exercise has reached a terminal state needs no polling. */
function allSettled(session: ExerciseSession | null): boolean {
  if (!session) return true;
  return session.exercises.every(
    (e) => e.status === "done" || e.status === "error",
  );
}

interface DuplicatorStore {
  session: ExerciseSession | null;
  loading: boolean;
  error: string | null;
  upload: (
    file: File,
    yearLevel: number,
    subjectHint?: string,
  ) => Promise<void>;
  poll: (sessionId: number) => void;
  stopPolling: () => void;
  removeExercise: (exerciseId: number) => Promise<void>;
  findMore: (exerciseId: number) => Promise<void>;
  reset: () => void;
}

// Interval handle kept outside the store (not reactive state).
let timer: ReturnType<typeof setInterval> | null = null;

export const useDuplicatorStore = create<DuplicatorStore>((set, get) => ({
  session: null,
  loading: false,
  error: null,

  upload: async (file, yearLevel, subjectHint) => {
    get().stopPolling();
    set({ loading: true, error: null, session: null });
    const form = new FormData();
    form.append("file", file);
    form.append("year_level", String(yearLevel));
    if (subjectHint && subjectHint.trim()) {
      form.append("subject_hint", subjectHint.trim());
    }
    try {
      const session = await api.upload<ExerciseSession>(
        "/duplicator/sessions",
        form,
      );
      set({ session, loading: false });
      if (!allSettled(session)) get().poll(session.id);
    } catch (err) {
      set({
        loading: false,
        error:
          err instanceof ApiError
            ? err.message
            : "Could not extract exercises from that PDF.",
      });
    }
  },

  poll: (sessionId) => {
    get().stopPolling();
    timer = setInterval(async () => {
      try {
        const session = await api.get<ExerciseSession>(
          `/duplicator/sessions/${sessionId}`,
        );
        set({ session });
        if (allSettled(session)) get().stopPolling();
      } catch {
        // Transient poll failure — keep the last good session, try again next tick.
      }
    }, POLL_MS);
  },

  stopPolling: () => {
    if (timer !== null) {
      clearInterval(timer);
      timer = null;
    }
  },

  // Optimistically drop the exercise from view, then delete it server-side. On
  // failure we re-fetch so the UI re-syncs with the truth instead of lying.
  removeExercise: async (exerciseId) => {
    const current = get().session;
    if (current) {
      set({
        session: {
          ...current,
          exercises: current.exercises.filter((e) => e.id !== exerciseId),
        },
      });
    }
    try {
      await api.del(`/duplicator/exercises/${exerciseId}`);
    } catch {
      if (current) {
        try {
          const fresh = await api.get<ExerciseSession>(
            `/duplicator/sessions/${current.id}`,
          );
          set({ session: fresh });
        } catch {
          set({ session: current }); // restore the pre-delete snapshot
        }
      }
    }
  },

  // Queue another variant search for one exercise; the server resets it to
  // pending and the worker appends new results, so we resume polling.
  findMore: async (exerciseId) => {
    try {
      const session = await api.post<ExerciseSession>(
        `/duplicator/exercises/${exerciseId}/search`,
      );
      set({ session });
      if (!allSettled(session)) get().poll(session.id);
    } catch (err) {
      set({
        error:
          err instanceof ApiError ? err.message : "Could not start a new search.",
      });
    }
  },

  reset: () => {
    get().stopPolling();
    set({ session: null, loading: false, error: null });
  },
}));

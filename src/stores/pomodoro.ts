import { create } from "zustand";

export type PomodoroPhase = "work" | "break";

interface PomodoroStore {
  phase: PomodoroPhase;
  running: boolean;
  /** Whole seconds left in the current phase. */
  remaining: number;
  /** Completed focus (work) sessions this run. */
  workSessions: number;
  /** Whether the widget panel is expanded. */
  expanded: boolean;
  /** Bumped each time a phase finishes — Wave 3 watches this to ring the alarm. */
  completedTick: number;

  // Durations (minutes), synced from Settings.
  workMin: number;
  breakMin: number;

  // Internal: wall-clock deadline while running (epoch ms), else null.
  endsAt: number | null;

  /** Sync durations from Settings. Updates the live countdown only when idle. */
  configure: (workMin: number, breakMin: number) => void;
  start: () => void;
  pause: () => void;
  toggle: () => void;
  reset: () => void;
  /** Jump to the next phase without finishing the current one. */
  skip: () => void;
  /** Recompute `remaining` from the deadline; rolls over to the next phase at 0. */
  tick: () => void;
  setExpanded: (expanded: boolean) => void;
}

const minToSec = (m: number) => Math.max(1, Math.round(m)) * 60;

export const usePomodoroStore = create<PomodoroStore>((set, get) => ({
  phase: "work",
  running: false,
  remaining: 25 * 60,
  workSessions: 0,
  expanded: false,
  completedTick: 0,
  workMin: 25,
  breakMin: 5,
  endsAt: null,

  configure: (workMin, breakMin) => {
    const s = get();
    const changed = workMin !== s.workMin || breakMin !== s.breakMin;
    if (!changed) return;
    set({ workMin, breakMin });
    // Only retime a phase the user hasn't started counting down yet.
    if (!s.running && s.endsAt === null) {
      set({ remaining: minToSec(s.phase === "work" ? workMin : breakMin) });
    }
  },

  start: () => {
    const s = get();
    const remaining = s.remaining > 0 ? s.remaining : minToSec(
      s.phase === "work" ? s.workMin : s.breakMin,
    );
    set({ running: true, remaining, endsAt: Date.now() + remaining * 1000 });
  },

  pause: () => {
    const s = get();
    const remaining =
      s.endsAt !== null
        ? Math.max(0, Math.round((s.endsAt - Date.now()) / 1000))
        : s.remaining;
    set({ running: false, remaining, endsAt: null });
  },

  toggle: () => (get().running ? get().pause() : get().start()),

  reset: () => {
    const s = get();
    set({
      phase: "work",
      running: false,
      endsAt: null,
      remaining: minToSec(s.workMin),
      workSessions: 0,
    });
  },

  skip: () => {
    const s = get();
    const next: PomodoroPhase = s.phase === "work" ? "break" : "work";
    const remaining = minToSec(next === "work" ? s.workMin : s.breakMin);
    set({
      phase: next,
      remaining,
      endsAt: s.running ? Date.now() + remaining * 1000 : null,
    });
  },

  tick: () => {
    const s = get();
    if (!s.running || s.endsAt === null) return;
    const remaining = Math.max(0, Math.round((s.endsAt - Date.now()) / 1000));
    if (remaining > 0) {
      set({ remaining });
      return;
    }
    // Phase finished → roll to the next phase and keep running (auto-continue).
    const next: PomodoroPhase = s.phase === "work" ? "break" : "work";
    const nextSeconds = minToSec(next === "work" ? s.workMin : s.breakMin);
    set({
      phase: next,
      remaining: nextSeconds,
      endsAt: Date.now() + nextSeconds * 1000,
      workSessions: s.phase === "work" ? s.workSessions + 1 : s.workSessions,
      completedTick: s.completedTick + 1,
    });
  },

  setExpanded: (expanded) => set({ expanded }),
}));

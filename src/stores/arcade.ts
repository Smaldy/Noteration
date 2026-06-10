import { create } from "zustand";

import { api, ApiError } from "@/lib/api";
import type { StudyEvent } from "@/lib/arcadeEvents";
import type { ArcadeState, RunStart } from "@/types/arcade";

/**
 * Arcade minigame store. Holds the server-authoritative economy/records plus the
 * client-side game lifecycle. The browser runs the game loop; every currency or
 * record change round-trips through the backend so nothing is lost on refresh.
 */

export type GamePhase = "off" | "starting" | "playing" | "over";

export interface RunResult {
  ok: boolean;
  error?: string;
}

interface ArcadeStore {
  state: ArcadeState | null;
  status: "idle" | "loading" | "error";
  overlayOpen: boolean;

  // Game lifecycle (the overlay hub hands off to the game layer).
  phase: GamePhase;
  run: RunStart | null;

  fetchState: () => Promise<void>;
  openOverlay: () => void;
  closeOverlay: () => void;

  earn: (kind: StudyEvent, count?: number) => Promise<void>;
  startRun: (mode: "fresh" | "resume") => Promise<RunResult>;
  endRun: (waveReached: number, scoreEarned: number, died: boolean) => Promise<void>;
  dismissGameOver: () => void;
  buyUpgrade: (key: string) => Promise<RunResult>;

  // Developer tools (only invoked from the DEV_MODE panel).
  devGrant: () => Promise<void>;
  devResetUpgrades: () => Promise<void>;
}

export const useArcadeStore = create<ArcadeStore>((set, get) => ({
  state: null,
  status: "idle",
  overlayOpen: false,
  phase: "off",
  run: null,

  fetchState: async () => {
    if (get().state === null) set({ status: "loading" });
    try {
      const state = await api.get<ArcadeState>("/arcade/state");
      set({ state, status: "idle" });
    } catch {
      set({ status: "error" });
    }
  },

  openOverlay: () => {
    set({ overlayOpen: true });
    void get().fetchState();
  },
  closeOverlay: () => set({ overlayOpen: false }),

  earn: async (kind, count = 1) => {
    try {
      const state = await api.post<ArcadeState>("/arcade/coins/earn", {
        source: kind,
        count,
      });
      set({ state });
    } catch {
      // Earning is best-effort; a failed award must never disrupt studying.
    }
  },

  startRun: async (mode) => {
    try {
      const run = await api.post<RunStart>("/arcade/run/start", { mode });
      set({ run, phase: "starting", overlayOpen: false });
      void get().fetchState();
      return { ok: true };
    } catch (err) {
      const error =
        err instanceof ApiError
          ? err.status === 402
            ? "Not enough coins"
            : err.message
          : "Could not start the run";
      return { ok: false, error };
    }
  },

  endRun: async (waveReached, scoreEarned, died) => {
    const run = get().run;
    if (run === null) return;
    try {
      const state = await api.post<ArcadeState>("/arcade/run/end", {
        session_id: run.session_id,
        wave_reached: waveReached,
        score_earned: scoreEarned,
        died,
      });
      set({ state, phase: "over" });
    } catch {
      set({ phase: "over" });
    }
  },

  dismissGameOver: () => set({ phase: "off", run: null }),

  buyUpgrade: async (key) => {
    try {
      const state = await api.post<ArcadeState>(`/arcade/upgrades/${key}/buy`);
      set({ state });
      return { ok: true };
    } catch (err) {
      const error =
        err instanceof ApiError
          ? err.status === 402
            ? "Not enough score points"
            : err.message
          : "Could not buy upgrade";
      return { ok: false, error };
    }
  },

  devGrant: async () => {
    try {
      set({ state: await api.post<ArcadeState>("/arcade/dev/grant") });
    } catch {
      // Dev tool; failures are non-fatal.
    }
  },

  devResetUpgrades: async () => {
    try {
      set({ state: await api.post<ArcadeState>("/arcade/dev/reset-upgrades") });
    } catch {
      // Dev tool; failures are non-fatal.
    }
  },
}));

/** Advance the game from the "WAVE 1" slam into active play. */
export function beginPlaying(): void {
  useArcadeStore.setState({ phase: "playing" });
}

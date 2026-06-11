import { create } from "zustand";

import { DEV_MODE } from "@/features/arcade/devMode";
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

  // Sectors (route ids) that currently have a live bomb — the running game
  // publishes this so the real Library nav buttons can glow. Empty when idle.
  bombSectors: string[];
  setBombSectors: (sectors: string[]) => void;

  // Sectors currently unlocked by the running game (sections unlock every 5
  // waves). The real Library buttons show a lock badge for the rest while playing.
  unlockedSectors: string[];
  setUnlockedSectors: (sectors: string[]) => void;

  fetchState: () => Promise<void>;
  openOverlay: () => void;
  closeOverlay: () => void;

  earn: (kind: StudyEvent, count?: number) => Promise<void>;
  startRun: (mode: "fresh" | "resume") => Promise<RunResult>;
  endRun: (waveReached: number, scoreEarned: number, died: boolean) => Promise<void>;
  dismissGameOver: () => void;
  buyUpgrade: (key: string) => Promise<RunResult>;
  prestige: () => Promise<RunResult>;
  setSpecial: (special: string) => Promise<RunResult>;

  // Developer tools (only invoked from the DEV_MODE panel).
  devGrant: () => Promise<void>;
  devResetUpgrades: () => Promise<void>;
  devAction: (path: string) => Promise<void>;
}

export const useArcadeStore = create<ArcadeStore>((set, get) => ({
  state: null,
  status: "idle",
  overlayOpen: false,
  phase: "off",
  run: null,
  bombSectors: [],
  setBombSectors: (sectors) => set({ bombSectors: sectors }),
  unlockedSectors: [],
  setUnlockedSectors: (sectors) => set({ unlockedSectors: sectors }),

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
      const run = await api.post<RunStart>("/arcade/run/start", { mode, dev: DEV_MODE });
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

  prestige: async () => {
    try {
      const state = await api.post<ArcadeState>("/arcade/prestige");
      set({ state });
      return { ok: true };
    } catch (err) {
      const error =
        err instanceof ApiError ? err.message : "Could not prestige";
      return { ok: false, error };
    }
  },

  setSpecial: async (special) => {
    try {
      const state = await api.post<ArcadeState>(`/arcade/special/${special}`);
      set({ state });
      return { ok: true };
    } catch (err) {
      const error =
        err instanceof ApiError ? err.message : "Could not set special";
      return { ok: false, error };
    }
  },

  devGrant: async () => {
    try {
      set({ state: await api.post<ArcadeState>("/arcade/dev/grant") });
    } catch (err) {
      // Dev tool; non-fatal, but surface so a stale backend (no /dev route yet —
      // restart it) isn't a silent no-op.
      console.warn("[arcade] dev grant failed — restart the backend?", err);
    }
  },

  devResetUpgrades: async () => {
    try {
      set({ state: await api.post<ArcadeState>("/arcade/dev/reset-upgrades") });
    } catch (err) {
      console.warn("[arcade] dev reset failed — restart the backend?", err);
    }
  },

  // Generic dev endpoint caller (e.g. "reset-prestige", "max-upgrades").
  devAction: async (path) => {
    try {
      set({ state: await api.post<ArcadeState>(`/arcade/dev/${path}`) });
    } catch (err) {
      console.warn(`[arcade] dev ${path} failed — restart the backend?`, err);
    }
  },
}));

/** Advance the game from the "WAVE 1" slam into active play. */
export function beginPlaying(): void {
  useArcadeStore.setState({ phase: "playing" });
}

import { create } from "zustand";

import * as audio from "@/features/pomodoro/audio";
import type { SoundKind } from "@/features/pomodoro/audio";

interface SoundStore {
  kind: SoundKind;
  volume: number; // 0–1
  muted: boolean;
  customName: string | null;
  /** True once the custom buffer is decoded and ready to play. */
  customLoaded: boolean;
  customError: string | null;
  hydrated: boolean;

  setKind: (kind: SoundKind) => void;
  setVolume: (volume: number) => void;
  toggleMuted: () => void;
  loadCustomFile: (file: File) => Promise<void>;
  clearCustom: () => Promise<void>;
  /** Load persisted prefs + re-decode the saved custom file (call once at boot). */
  hydrate: () => Promise<void>;
}

const PREFS_KEY = "noteration.sound";

interface Prefs {
  kind: SoundKind;
  volume: number;
  muted: boolean;
  customName: string | null;
}

function persist(state: SoundStore): void {
  const prefs: Prefs = {
    kind: state.kind,
    volume: state.volume,
    muted: state.muted,
    customName: state.customName,
  };
  try {
    localStorage.setItem(PREFS_KEY, JSON.stringify(prefs));
  } catch {
    // storage may be unavailable (private mode); prefs just won't persist
  }
}

function readPrefs(): Prefs | null {
  try {
    const raw = localStorage.getItem(PREFS_KEY);
    return raw ? (JSON.parse(raw) as Prefs) : null;
  } catch {
    return null;
  }
}

export const useSoundStore = create<SoundStore>((set, get) => ({
  kind: "none",
  volume: 0.6,
  muted: false,
  customName: null,
  customLoaded: false,
  customError: null,
  hydrated: false,

  setKind: (kind) => {
    set({ kind });
    persist(get());
  },

  setVolume: (volume) => {
    set({ volume: Math.max(0, Math.min(1, volume)) });
    persist(get());
  },

  toggleMuted: () => {
    set({ muted: !get().muted });
    persist(get());
  },

  loadCustomFile: async (file) => {
    set({ customError: null });
    try {
      const bytes = await file.arrayBuffer();
      await audio.loadCustomFromBytes(bytes); // decode (may throw)
      await audio.saveCustomBytes(bytes); // persist for next session
      set({ kind: "custom", customName: file.name, customLoaded: true });
      persist(get());
    } catch {
      set({ customError: "Couldn't load that audio file." });
    }
  },

  clearCustom: async () => {
    await audio.clearCustomBytes();
    const nextKind = get().kind === "custom" ? "none" : get().kind;
    set({ customName: null, customLoaded: false, kind: nextKind });
    persist(get());
  },

  hydrate: async () => {
    if (get().hydrated) return;
    const prefs = readPrefs();
    if (prefs) {
      set({
        kind: prefs.kind,
        volume: prefs.volume,
        muted: prefs.muted,
        customName: prefs.customName,
      });
    }
    // Re-decode a previously saved custom file, if any.
    try {
      const bytes = await audio.readCustomBytes();
      if (bytes) {
        await audio.loadCustomFromBytes(bytes);
        set({ customLoaded: true });
      } else if (get().kind === "custom") {
        set({ kind: "none" }); // saved file is gone; fall back
      }
    } catch {
      if (get().kind === "custom") set({ kind: "none" });
    }
    set({ hydrated: true });
    persist(get());
  },
}));

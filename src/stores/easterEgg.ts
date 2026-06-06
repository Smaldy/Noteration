import { create } from "zustand";

/**
 * Hidden easter egg: tapping the Library title 4 times in quick succession opens
 * the credits. The title looks like a plain heading — nothing hints it's
 * clickable — so this only ever fires for someone deliberately mashing it.
 */

// How many taps, and how tight the window has to be, to count as "a quick session".
const TAPS_REQUIRED = 4;
const WINDOW_MS = 1200;

interface EasterEggStore {
  /** Recent tap timestamps within the rolling window. */
  taps: number[];
  /** Whether the credits overlay is showing. */
  creditsOpen: boolean;
  /** Call on each Library-title tap; opens credits once 4 land within the window. */
  registerLibraryTap: () => void;
  closeCredits: () => void;
}

export const useEasterEggStore = create<EasterEggStore>((set, get) => ({
  taps: [],
  creditsOpen: false,

  registerLibraryTap: () => {
    if (get().creditsOpen) return;
    const now = Date.now();
    const taps = [...get().taps, now].filter((t) => now - t <= WINDOW_MS);
    if (taps.length >= TAPS_REQUIRED) {
      set({ taps: [], creditsOpen: true });
    } else {
      set({ taps });
    }
  },

  closeCredits: () => set({ creditsOpen: false, taps: [] }),
}));

import { create } from "zustand";

import { ApiError, api } from "@/lib/api";
import type { Settings, SettingsUpdate } from "@/types/settings";

type Load = "idle" | "loading" | "loaded" | "error";

/** Apply persisted appearance to the document (dark class + base font size). */
function applyAppearance(settings: Settings): void {
  const root = document.documentElement;
  const prefersDark =
    typeof window.matchMedia === "function" &&
    window.matchMedia("(prefers-color-scheme: dark)").matches;
  const dark =
    settings.theme === "dark" || (settings.theme === "system" && prefersDark);
  root.classList.toggle("dark", dark);
  root.style.fontSize = `${settings.font_size}px`;
}

interface SettingsStore {
  settings: Settings | null;
  loadState: Load;
  error: string | null;
  saving: boolean;
  saveError: string | null;
  fetchSettings: () => Promise<void>;
  updateSettings: (changes: SettingsUpdate) => Promise<void>;
}

export const useSettingsStore = create<SettingsStore>((set) => ({
  settings: null,
  loadState: "idle",
  error: null,
  saving: false,
  saveError: null,

  fetchSettings: async () => {
    set({ loadState: "loading", error: null });
    try {
      const settings = await api.get<Settings>("/settings");
      applyAppearance(settings);
      set({ settings, loadState: "loaded" });
    } catch (err) {
      set({
        loadState: "error",
        error:
          err instanceof ApiError ? err.message : "Failed to load settings.",
      });
    }
  },

  updateSettings: async (changes) => {
    set({ saving: true, saveError: null });
    try {
      const settings = await api.patch<Settings>("/settings", changes);
      applyAppearance(settings);
      set({ settings });
    } catch (err) {
      set({
        saveError:
          err instanceof ApiError ? err.message : "Failed to save settings.",
      });
      throw err;
    } finally {
      set({ saving: false });
    }
  },
}));

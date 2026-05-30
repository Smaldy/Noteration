import { create } from "zustand";

import { ApiError, api } from "@/lib/api";
import type { Settings, SettingsUpdate } from "@/types/settings";

type Load = "idle" | "loading" | "loaded" | "error";

/** Font-family options → CSS font stacks (Inter is bundled via @fontsource). */
export const FONT_STACKS: Record<string, string> = {
  system: 'system-ui, -apple-system, "Segoe UI", sans-serif',
  inter: '"Inter Variable", system-ui, sans-serif',
  serif: 'Georgia, Cambria, "Times New Roman", serif',
  mono: '"JetBrains Mono", ui-monospace, SFMono-Regular, monospace',
};

/** Pick a readable foreground (near-black/near-white) for a hex background. */
function contrastFor(hex: string): string {
  const m = /^#?([0-9a-f]{6})$/i.exec(hex.trim());
  if (!m) return "#ffffff";
  const n = parseInt(m[1], 16);
  const r = (n >> 16) & 255;
  const g = (n >> 8) & 255;
  const b = n & 255;
  // Relative luminance (sRGB) → dark text on light accents, white on dark.
  const lum = (0.299 * r + 0.587 * g + 0.114 * b) / 255;
  return lum > 0.6 ? "#18181b" : "#ffffff";
}

export interface Appearance {
  theme: string;
  font_size: number;
  accent_color: string | null;
  font_family: string | null;
}

/** Apply appearance to the document: theme, accent, font, size. Exported so the
 *  Settings page can preview changes live before they're saved. */
export function applyAppearance(a: Appearance): void {
  const root = document.documentElement;
  const prefersDark =
    typeof window.matchMedia === "function" &&
    window.matchMedia("(prefers-color-scheme: dark)").matches;
  const dark = a.theme === "dark" || (a.theme === "system" && prefersDark);
  root.classList.toggle("dark", dark);
  root.style.fontSize = `${a.font_size}px`;

  // Accent: drive the primary + ring tokens (or clear to fall back to the theme).
  if (a.accent_color) {
    root.style.setProperty("--primary", a.accent_color);
    root.style.setProperty("--ring", a.accent_color);
    root.style.setProperty("--primary-foreground", contrastFor(a.accent_color));
  } else {
    root.style.removeProperty("--primary");
    root.style.removeProperty("--ring");
    root.style.removeProperty("--primary-foreground");
  }

  // Font family: body reads var(--app-font).
  const stack = a.font_family ? FONT_STACKS[a.font_family] : null;
  if (stack) root.style.setProperty("--app-font", stack);
  else root.style.removeProperty("--app-font");
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

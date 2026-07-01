import { create } from "zustand";

import { setLanguage } from "@/i18n";
import { ApiError, api } from "@/lib/api";
import type { Settings, SettingsUpdate } from "@/types/settings";

type Load = "idle" | "loading" | "loaded" | "error";

/** Font-family options → CSS font stacks (all bundled via @fontsource). */
export const FONT_STACKS: Record<string, string> = {
  sans: '"Plus Jakarta Sans Variable", system-ui, -apple-system, sans-serif',
  system: 'system-ui, -apple-system, "Segoe UI", sans-serif',
  inter: '"Inter Variable", system-ui, sans-serif',
  serif: '"Newsreader Variable", Georgia, "Times New Roman", serif',
  mono: '"JetBrains Mono", ui-monospace, SFMono-Regular, monospace',
};

/** Indigo — the brand accent used when the user hasn't picked one, so the UI
 *  always carries color rather than falling back to neutral gray. */
export const DEFAULT_ACCENT = "#6366f1";

/** Parse #rgb / #rrggbb → {r,g,b} (0–255), or null if malformed. */
function parseHex(hex: string): { r: number; g: number; b: number } | null {
  let h = /^#?([0-9a-f]{3}|[0-9a-f]{6})$/i.exec(hex.trim())?.[1];
  if (!h) return null;
  if (h.length === 3) h = h.split("").map((c) => c + c).join("");
  const n = parseInt(h, 16);
  return { r: (n >> 16) & 255, g: (n >> 8) & 255, b: n & 255 };
}

/** WCAG relative luminance (gamma-corrected sRGB) of a parsed color. */
function relativeLuminance(c: { r: number; g: number; b: number }): number {
  const lin = (v: number) => {
    const s = v / 255;
    return s <= 0.04045 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * lin(c.r) + 0.7152 * lin(c.g) + 0.0722 * lin(c.b);
}

// Near-black foreground candidate (zinc-900); its luminance is fixed.
const DARK_FG = "#18181b";
const DARK_FG_LUM = relativeLuminance({ r: 0x18, g: 0x18, b: 0x1b });

/** Pick a readable foreground (near-black/near-white) for a hex background.
 *  Chooses whichever candidate has the higher WCAG contrast ratio, so
 *  mid-luminance accents (orange, vivid red) get dark text instead of the
 *  white that a simple luma threshold would pick but that fails AA. */
function contrastFor(hex: string): string {
  const c = parseHex(hex);
  if (!c) return "#ffffff";
  const lum = relativeLuminance(c);
  const vsWhite = 1.05 / (lum + 0.05);
  const vsDark = (lum + 0.05) / (DARK_FG_LUM + 0.05);
  return vsDark >= vsWhite ? DARK_FG : "#ffffff";
}

/** Hue (deg) + saturation (0–1) of a hex color, for tinting derived tokens. */
function hueSat(hex: string): { h: number; s: number } {
  const c = parseHex(hex);
  if (!c) return { h: 240, s: 0.8 };
  const r = c.r / 255;
  const g = c.g / 255;
  const b = c.b / 255;
  const max = Math.max(r, g, b);
  const min = Math.min(r, g, b);
  const l = (max + min) / 2;
  const d = max - min;
  if (d === 0) return { h: 240, s: 0 };
  const s = d / (1 - Math.abs(2 * l - 1));
  let h: number;
  if (max === r) h = ((g - b) / d) % 6;
  else if (max === g) h = (b - r) / d + 2;
  else h = (r - g) / d + 4;
  h *= 60;
  if (h < 0) h += 360;
  return { h, s };
}

/** Generate a full, readable token palette from one accent hex for the active
 *  theme. Tint saturation scales with the accent's own saturation so vivid
 *  accents read rich and near-gray accents (e.g. slate) stay tastefully muted. */
function buildPalette(hex: string, dark: boolean): Record<string, string> {
  const { h, s } = hueSat(hex);
  const hr = Math.round(h);
  // hsl token at `baseS%` saturation (scaled by accent saturation) and `l%`.
  const t = (baseS: number, l: number) =>
    `hsl(${hr} ${Math.round(baseS * s)}% ${l}%)`;
  const fg = contrastFor(hex);

  return dark
    ? {
        "--background": t(24, 8),
        "--foreground": t(16, 95),
        "--card": t(22, 11),
        "--card-foreground": t(16, 95),
        "--popover": t(22, 12),
        "--popover-foreground": t(16, 95),
        "--primary": hex,
        "--primary-foreground": fg,
        "--primary-soft": t(34, 20),
        "--primary-soft-foreground": t(55, 84),
        "--secondary": t(16, 18),
        "--secondary-foreground": t(16, 92),
        "--muted": t(14, 16),
        "--muted-foreground": t(12, 66),
        "--accent": t(30, 24),
        "--accent-foreground": t(55, 84),
        "--border": t(16, 22),
        "--input": t(16, 25),
        "--ring": hex,
      }
    : {
        "--background": t(36, 98.5),
        "--foreground": t(22, 12),
        "--card": t(40, 99.5),
        "--card-foreground": t(22, 12),
        "--popover": t(40, 99.5),
        "--popover-foreground": t(22, 12),
        "--primary": hex,
        "--primary-foreground": fg,
        "--primary-soft": t(62, 95),
        "--primary-soft-foreground": t(55, 32),
        "--secondary": t(30, 94),
        "--secondary-foreground": t(35, 26),
        "--muted": t(26, 95.5),
        "--muted-foreground": t(14, 44),
        "--accent": t(48, 92),
        "--accent-foreground": t(50, 30),
        "--border": t(22, 89.5),
        "--input": t(22, 86),
        "--ring": hex,
      };
}

export interface Appearance {
  theme: string;
  font_size: number;
  accent_color: string | null;
  font_family: string | null;
}

// The appearance currently on the document, so the OS-scheme listener can
// re-derive the palette when theme is "system" and the user flips dark/light.
let activeAppearance: Appearance | null = null;
let osSchemeBound = false;

function bindOsSchemeListener(): void {
  if (osSchemeBound || typeof window.matchMedia !== "function") return;
  osSchemeBound = true;
  const mql = window.matchMedia("(prefers-color-scheme: dark)");
  const reapply = () => {
    if (activeAppearance?.theme === "system") applyAppearance(activeAppearance);
  };
  if (typeof mql.addEventListener === "function") mql.addEventListener("change", reapply);
  else mql.addListener(reapply); // older Safari
}

/** Apply appearance to the document: theme, accent, font, size. Exported so the
 *  Settings page can preview changes live before they're saved. */
export function applyAppearance(a: Appearance): void {
  activeAppearance = a;
  bindOsSchemeListener();
  const root = document.documentElement;
  const prefersDark =
    typeof window.matchMedia === "function" &&
    window.matchMedia("(prefers-color-scheme: dark)").matches;
  const dark = a.theme === "dark" || (a.theme === "system" && prefersDark);
  root.classList.toggle("dark", dark);
  root.style.fontSize = `${a.font_size}px`;

  // Color: derive the entire token palette from the accent (or the brand
  // default) so one picked color flows cohesively through the whole UI.
  const palette = buildPalette(a.accent_color || DEFAULT_ACCENT, dark);
  for (const [token, value] of Object.entries(palette)) {
    root.style.setProperty(token, value);
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
      setLanguage(settings.language); // reconcile the cached language with the backend
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
      setLanguage(settings.language);
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

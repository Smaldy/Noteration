/** Settings form model: the editable state, its mapping from persisted
 *  `Settings`, and the static option tables the sections render from. */

import {
  CalendarClock,
  FileText,
  Globe,
  KeyRound,
  Palette,
  Sparkles,
  Timer,
} from "lucide-react";
import type { ComponentType } from "react";

import type { Language } from "@/i18n";
import type { CalendarSlot, GeminiModel, Settings, Theme } from "@/types/settings";

export interface FormState {
  allow_paid: boolean;
  ollama_enabled: boolean;
  ollama_model: string;
  gemini_enabled: boolean;
  gemini_rotation: boolean;
  gemini_model: GeminiModel;
  per_document_token_budget: number;
  note_length: number;
  pomodoro_work_min: number;
  pomodoro_break_min: number;
  calendar_day_start_hour: number;
  calendar_day_end_hour: number;
  calendar_slot_minutes: CalendarSlot;
  theme: Theme;
  accent_color: string; // "" = follow theme default
  font_family: string;
  font_size: number;
  language: Language;
}

/** Setter shared by every section: patch one form field. */
export type SetField = <K extends keyof FormState>(
  key: K,
  value: FormState[K],
) => void;

export const SLOT_OPTIONS: { value: CalendarSlot; label: string }[] = [
  { value: 15, label: "15 min" },
  { value: 30, label: "30 min" },
  { value: 60, label: "1 hour" },
  { value: 90, label: "1.5 hr" },
  { value: 120, label: "2 hours" },
];

const SLOT_VALUES: CalendarSlot[] = [15, 30, 60, 90, 120];

/** Snap an arbitrary stored slot value to the nearest allowed option. */
function toSlot(n: number): CalendarSlot {
  return SLOT_VALUES.includes(n as CalendarSlot)
    ? (n as CalendarSlot)
    : SLOT_VALUES.reduce((best, v) =>
        Math.abs(v - n) < Math.abs(best - n) ? v : best,
      );
}

/** Format an hour (0–24) as a clock label, e.g. 8 → "8:00", 23 → "23:00". */
export function hourLabel(h: number): string {
  return `${h}:00`;
}

// The four selectable Gemini models. Names stay as-is (proper names); the per-tier
// hint is translated via key. ROTATION_ORDER mirrors the backend's best-first order.
export const GEMINI_MODELS: {
  value: GeminiModel;
  label: string;
  hintKey: string;
}[] = [
  {
    value: "gemini-2.5-flash-lite",
    label: "2.5 Flash Lite",
    hintKey: "settings.providers.models.flashLiteHint",
  },
  {
    value: "gemini-2.5-flash",
    label: "2.5 Flash",
    hintKey: "settings.providers.models.flashHint",
  },
  {
    value: "gemini-3.1-flash-lite",
    label: "3.1 Flash Lite",
    hintKey: "settings.providers.models.flashLiteHint",
  },
  {
    value: "gemini-3.5-flash",
    label: "3.5 Flash",
    hintKey: "settings.providers.models.flashHint",
  },
];

// Best-first order tried when rotation is on (mirrors backend ROTATION_ORDER).
export const ROTATION_ORDER: GeminiModel[] = [
  "gemini-3.5-flash",
  "gemini-3.1-flash-lite",
  "gemini-2.5-flash",
  "gemini-2.5-flash-lite",
];

export function modelLabel(value: GeminiModel): string {
  return GEMINI_MODELS.find((m) => m.value === value)?.label ?? value;
}

// Curated accent palette (hex drives the whole derived palette live). `key`
// indexes the localized color name under settings.appearance.colors.
export const PRESET_ACCENTS: { key: string; hex: string }[] = [
  { key: "indigo", hex: "#6366f1" },
  { key: "violet", hex: "#8b5cf6" },
  { key: "blue", hex: "#3b82f6" },
  { key: "sky", hex: "#0ea5e9" },
  { key: "teal", hex: "#14b8a6" },
  { key: "emerald", hex: "#10b981" },
  { key: "amber", hex: "#f59e0b" },
  { key: "rose", hex: "#f43f5e" },
  { key: "slate", hex: "#475569" },
];

export const FONT_OPTIONS: { value: string; label: string }[] = [
  { value: "sans", label: "Jakarta" },
  { value: "system", label: "System" },
  { value: "inter", label: "Inter" },
  { value: "serif", label: "Newsreader" },
  { value: "mono", label: "Mono" },
];

// Render each font button in its own typeface as a preview.
export const FONT_PREVIEW: Record<string, string> = {
  sans: '"Plus Jakarta Sans Variable", system-ui, sans-serif',
  system: "system-ui, sans-serif",
  inter: '"Inter Variable", system-ui, sans-serif',
  serif: '"Newsreader Variable", Georgia, serif',
  mono: '"JetBrains Mono", ui-monospace, monospace',
};

// Section registry powers both the scroll-spy sidebar and the rendered cards,
// so the nav can never drift out of sync with the content.
export const SECTIONS: {
  id: string;
  /** i18n key for the nav label. */
  labelKey: string;
  icon: ComponentType<{ className?: string }>;
}[] = [
  { id: "api-keys", labelKey: "settings.nav.apiKeys", icon: KeyRound },
  { id: "providers", labelKey: "settings.nav.providers", icon: Sparkles },
  { id: "generation", labelKey: "settings.nav.generation", icon: FileText },
  { id: "language", labelKey: "settings.nav.language", icon: Globe },
  { id: "pomodoro", labelKey: "settings.nav.pomodoro", icon: Timer },
  { id: "calendar", labelKey: "settings.nav.calendar", icon: CalendarClock },
  { id: "appearance", labelKey: "settings.nav.appearance", icon: Palette },
];

export function toForm(s: Settings): FormState {
  return {
    allow_paid: s.allow_paid,
    ollama_enabled: s.ollama_enabled,
    ollama_model: s.ollama_model ?? "",
    gemini_enabled: s.gemini_enabled,
    gemini_rotation: s.gemini_rotation,
    gemini_model: (s.gemini_model as GeminiModel) ?? "gemini-2.5-flash-lite",
    per_document_token_budget: s.per_document_token_budget,
    note_length: s.note_length ?? 3,
    pomodoro_work_min: s.pomodoro_work_min,
    pomodoro_break_min: s.pomodoro_break_min,
    calendar_day_start_hour: s.calendar_day_start_hour,
    calendar_day_end_hour: s.calendar_day_end_hour,
    calendar_slot_minutes: toSlot(s.calendar_slot_minutes),
    theme: (s.theme as Theme) ?? "system",
    accent_color: s.accent_color ?? "",
    font_family: s.font_family ?? "sans",
    font_size: s.font_size,
    language: (s.language as Language) ?? "en",
  };
}

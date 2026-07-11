/** Settings form model: the editable state, its mapping from persisted
 *  `Settings`, and the static option tables the sections render from. */

import {
  CalendarClock,
  Cpu,
  FileText,
  Globe,
  KeyRound,
  Palette,
  Sparkles,
  Timer,
} from "lucide-react";
import type { ComponentType } from "react";

import type { Language } from "@/i18n";
import { FONT_STACKS } from "@/stores/settings";
import type {
  AIStyle,
  CalendarSlot,
  GeminiModel,
  Settings,
  StudyField,
  Theme,
} from "@/types/settings";

export interface FormState {
  allow_paid: boolean;
  gemini_enabled: boolean;
  gemini_rotation: boolean;
  gemini_model: GeminiModel;
  per_document_token_budget: number;
  note_length: number;
  study_field: StudyField;
  ai_style: AIStyle;
  pomodoro_work_min: number;
  pomodoro_break_min: number;
  calendar_day_start_hour: number;
  calendar_day_end_hour: number;
  calendar_slot_minutes: CalendarSlot;
  theme: Theme;
  accent_color: string; // "" = follow theme default
  font_family: string;
  font_family_heading: string;
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

// Fields of study the AI tutor can be tuned to (mirrors backend STUDY_FIELDS).
// Labels + hints are localized under settings.generation.fields.<value>.
export const STUDY_FIELD_VALUES: StudyField[] = [
  "general",
  "engineering",
  "mathematics",
  "natural_sciences",
  "medicine",
  "law",
  "economics",
  "humanities",
  "languages",
];

// Writing styles for generated content (mirrors backend AI_STYLES). Labels +
// hints are localized under settings.generation.styles.<value>.
export const AI_STYLE_VALUES: AIStyle[] = [
  "balanced",
  "simple",
  "technical",
  "discursive",
  "concise",
  "academic",
];

function isStudyField(v: string): v is StudyField {
  return (STUDY_FIELD_VALUES as string[]).includes(v);
}

function isAIStyle(v: string): v is AIStyle {
  return (AI_STYLE_VALUES as string[]).includes(v);
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

// Body-text faces: popular, readable, all bundled via @fontsource.
export const FONT_OPTIONS: { value: string; label: string }[] = [
  { value: "sans", label: "Jakarta" },
  { value: "system", label: "System" },
  { value: "inter", label: "Inter" },
  { value: "roboto", label: "Roboto" },
  { value: "opensans", label: "Open Sans" },
  { value: "nunito", label: "Nunito" },
  { value: "sourcesans", label: "Source Sans" },
  { value: "mono", label: "Mono" },
];

// Heading faces: the built-in display font first, then the body list (minus
// Mono, which reads poorly at title sizes).
export const HEADING_FONT_OPTIONS: { value: string; label: string }[] = [
  { value: "montserrat", label: "Montserrat" },
  ...FONT_OPTIONS.filter((f) => f.value !== "mono"),
];

// Render each font button in its own typeface as a preview (the app-wide
// stacks double as the preview stacks).
export const FONT_PREVIEW: Record<string, string> = FONT_STACKS;

// Section registry powers both the scroll-spy sidebar and the rendered cards,
// so the nav can never drift out of sync with the content.
export const SECTIONS: {
  id: string;
  /** i18n key for the nav label. */
  labelKey: string;
  icon: ComponentType<{ className?: string }>;
}[] = [
  { id: "appearance", labelKey: "settings.nav.appearance", icon: Palette },
  { id: "pomodoro", labelKey: "settings.nav.pomodoro", icon: Timer },
  { id: "language", labelKey: "settings.nav.language", icon: Globe },
  { id: "calendar", labelKey: "settings.nav.calendar", icon: CalendarClock },
  { id: "api-keys", labelKey: "settings.nav.apiKeys", icon: KeyRound },
  { id: "providers", labelKey: "settings.nav.providers", icon: Sparkles },
  { id: "local-ai", labelKey: "settings.nav.localAi", icon: Cpu },
  { id: "generation", labelKey: "settings.nav.generation", icon: FileText },
];

/** Per-browser prefs for the section list: display order + hidden sections.
 *  Pure UI taste, so it lives in localStorage rather than the settings API.
 *  Loading reconciles against SECTIONS so added/removed sections stay sound. */
// v2: bumped when the default order changed (appearance-first), so installs
// that stored the old default pick up the new one.
const SECTION_PREFS_KEY = "noteration-settings-sections-v2";

export interface SectionPrefs {
  order: string[];
  hidden: string[];
}

export function loadSectionPrefs(): SectionPrefs {
  const ids = SECTIONS.map((s) => s.id);
  try {
    const raw = localStorage.getItem(SECTION_PREFS_KEY);
    if (raw) {
      const parsed = JSON.parse(raw) as Partial<SectionPrefs>;
      const stored = Array.isArray(parsed.order)
        ? parsed.order.filter((id) => ids.includes(id))
        : [];
      return {
        order: [...stored, ...ids.filter((id) => !stored.includes(id))],
        hidden: Array.isArray(parsed.hidden)
          ? parsed.hidden.filter((id) => ids.includes(id))
          : [],
      };
    }
  } catch {
    // Unreadable JSON or storage denied: fall back to defaults.
  }
  return { order: ids, hidden: [] };
}

export function saveSectionPrefs(prefs: SectionPrefs) {
  try {
    localStorage.setItem(SECTION_PREFS_KEY, JSON.stringify(prefs));
  } catch {
    // Storage unavailable (private mode); the prefs just won't persist.
  }
}

export function toForm(s: Settings): FormState {
  return {
    allow_paid: s.allow_paid,
    gemini_enabled: s.gemini_enabled,
    gemini_rotation: s.gemini_rotation,
    gemini_model: (s.gemini_model as GeminiModel) ?? "gemini-2.5-flash-lite",
    per_document_token_budget: s.per_document_token_budget,
    note_length: s.note_length ?? 3,
    study_field: isStudyField(s.study_field) ? s.study_field : "general",
    ai_style: isAIStyle(s.ai_style) ? s.ai_style : "balanced",
    pomodoro_work_min: s.pomodoro_work_min,
    pomodoro_break_min: s.pomodoro_break_min,
    calendar_day_start_hour: s.calendar_day_start_hour,
    calendar_day_end_hour: s.calendar_day_end_hour,
    calendar_slot_minutes: toSlot(s.calendar_slot_minutes),
    theme: (s.theme as Theme) ?? "system",
    accent_color: s.accent_color ?? "",
    // A stored face that no longer exists (e.g. the removed Newsreader) snaps
    // back to the built-in default so the picker always has a valid selection.
    font_family: s.font_family && FONT_STACKS[s.font_family] ? s.font_family : "sans",
    font_family_heading:
      s.font_family_heading && FONT_STACKS[s.font_family_heading]
        ? s.font_family_heading
        : "montserrat",
    font_size: s.font_size,
    language: (s.language as Language) ?? "en",
  };
}

/** Mirrors `backend/schemas/settings.py`. */

export type Theme = "system" | "light" | "dark";
export type GeminiModel =
  | "gemini-2.5-flash-lite"
  | "gemini-2.5-flash"
  | "gemini-3.1-flash-lite"
  | "gemini-3.5-flash";
export type CalendarSlot = 15 | 30 | 60 | 90 | 120;
export type Language = "en" | "it" | "es";
/** The student's field of study — sets the AI tutor persona and notes coverage. */
export type StudyField =
  | "general"
  | "engineering"
  | "mathematics"
  | "natural_sciences"
  | "medicine"
  | "law"
  | "economics"
  | "humanities"
  | "languages";
/** How the AI words generated content; "balanced" adds no directive. */
export type AIStyle =
  | "balanced"
  | "simple"
  | "technical"
  | "discursive"
  | "concise"
  | "academic";

export interface Settings {
  allow_paid: boolean;
  provider_order: string[] | null;
  ollama_enabled: boolean;
  ollama_model: string | null;
  gemini_model: string;
  gemini_enabled: boolean;
  gemini_rotation: boolean;
  /** Per-document token ceiling. 0 = automatic (estimate × factor). */
  per_document_token_budget: number;
  /** Notes length per topic, in "pages" (units of content). 1-10. */
  note_length: number;
  pomodoro_work_min: number;
  pomodoro_break_min: number;
  calendar_day_start_hour: number;
  calendar_day_end_hour: number;
  calendar_slot_minutes: number;
  theme: string;
  accent_color: string | null;
  font_family: string | null;
  font_family_heading: string | null;
  font_size: number;
  language: string;
  study_field: string;
  ai_style: string;
  gemini_key_set: boolean;
  claude_key_set: boolean;
}

/** Partial update — only included fields are applied; empty api_key_* clears it. */
export interface SettingsUpdate {
  api_key_gemini?: string;
  api_key_claude?: string;
  allow_paid?: boolean;
  provider_order?: string[] | null;
  ollama_enabled?: boolean;
  /** Empty string clears the stored model name. */
  ollama_model?: string;
  gemini_model?: GeminiModel;
  gemini_enabled?: boolean;
  gemini_rotation?: boolean;
  per_document_token_budget?: number;
  note_length?: number;
  pomodoro_work_min?: number;
  pomodoro_break_min?: number;
  calendar_day_start_hour?: number;
  calendar_day_end_hour?: number;
  calendar_slot_minutes?: CalendarSlot;
  theme?: Theme;
  accent_color?: string | null;
  font_family?: string | null;
  font_family_heading?: string | null;
  font_size?: number;
  language?: Language;
  study_field?: StudyField;
  ai_style?: AIStyle;
}

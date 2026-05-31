/** Mirrors `backend/schemas/settings.py`. */

export type Theme = "system" | "light" | "dark";
export type GeminiModel = "gemini-2.5-flash-lite" | "gemini-2.5-flash";

export interface Settings {
  allow_paid: boolean;
  provider_order: string[] | null;
  ollama_enabled: boolean;
  gemini_model: string;
  /** Per-document token ceiling. 0 = automatic (estimate × factor). */
  per_document_token_budget: number;
  pomodoro_work_min: number;
  pomodoro_break_min: number;
  theme: string;
  accent_color: string | null;
  font_family: string | null;
  font_size: number;
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
  gemini_model?: GeminiModel;
  per_document_token_budget?: number;
  pomodoro_work_min?: number;
  pomodoro_break_min?: number;
  theme?: Theme;
  accent_color?: string | null;
  font_family?: string | null;
  font_size?: number;
}

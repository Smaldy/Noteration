/** Mirrors `backend/schemas/study.py::CalendarEntryOut` (+ catalog schemas). */

export type ScheduleSource = "sm2" | "manual" | "deadline" | "ai";
export type CalendarKind = "topic" | "subject" | "custom" | "deadline";

export interface CalendarEntry {
  id: number;
  /** ISO date (YYYY-MM-DD). */
  date: string;
  /** "HH:MM" wall-clock start, or null for an all-day item. */
  start_time: string | null;
  source: ScheduleSource;
  is_revision_buffer: boolean;
  is_deadline: boolean;
  kind: CalendarKind;
  /** Effective display title (event name, else topic/subject name). */
  title: string;
  description: string | null;
  completed: boolean;
  completed_at: string | null;
  /** True if completed on/before its date; null when not completed. */
  on_time: boolean | null;

  topic_id: number | null;
  topic_title: string | null;
  document_id: number | null;
  subject_id: number | null;
  subject_name: string | null;
}

// --- topic picker catalog (study/topic-catalog) ---------------------------- //

export interface CatalogTopic {
  id: number;
  title: string;
  chapter_title: string;
  document_id: number;
  document_filename: string;
  studied: boolean;
}

export interface CatalogSubject {
  id: number;
  name: string;
  topics: CatalogTopic[];
}

// --- request bodies -------------------------------------------------------- //

export interface ScheduleEntryCreate {
  date: string;
  /** "HH:MM" — pin to an hour; omit for an all-day item. */
  start_time?: string;
  topic_id?: number;
  subject_id?: number;
  title?: string;
  description?: string;
  is_deadline?: boolean;
}

export interface ScheduleEntryUpdate {
  date?: string;
  /** "HH:MM" to pin, null to clear (all-day), omit to leave unchanged. */
  start_time?: string | null;
  title?: string;
  description?: string;
  completed?: boolean;
}

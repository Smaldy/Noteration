/** Mirrors `backend/schemas/study.py::CalendarEntryOut`. */

export type ScheduleSource = "sm2" | "manual" | "deadline";

export interface CalendarEntry {
  id: number;
  topic_id: number;
  topic_title: string;
  document_id: number;
  /** ISO date (YYYY-MM-DD). */
  date: string;
  is_revision_buffer: boolean;
  source: ScheduleSource;
}

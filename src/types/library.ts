/** Mirrors `backend/schemas/library.py::DocumentSummaryOut`. */

export type DocumentStatus =
  | "transcribing"
  | "uploaded"
  | "processing"
  | "ready"
  | "error";

/** Which section a document belongs to: full study vs assessment-only exam prep. */
export type DocumentMode = "study" | "exam";

/** Where a document came from: an uploaded PDF, or transcribed audio. */
export type SourceType = "pdf" | "audio";

export interface DocumentSummary {
  id: number;
  filename: string;
  subject_id: number;
  subject_name: string;
  subject_bookmarked: boolean;
  /** ISO date (YYYY-MM-DD) or null when no exam date is set. */
  exam_date: string | null;
  status: DocumentStatus;
  /** Human-readable detail for the status (e.g. a transcription wait message). */
  status_detail: string | null;
  source_type: SourceType;
  mode: DocumentMode;
  /** ISO datetime. */
  uploaded_at: string;
  topics_total: number;
  topics_ready: number;
  chapters_total: number;
  /** Chapter lanes set to process (running). */
  chapters_running: number;
}

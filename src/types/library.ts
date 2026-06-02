/** Mirrors `backend/schemas/library.py::DocumentSummaryOut`. */

export type DocumentStatus = "uploaded" | "processing" | "ready" | "error";

/** Which section a document belongs to: full study vs assessment-only exam prep. */
export type DocumentMode = "study" | "exam";

export interface DocumentSummary {
  id: number;
  filename: string;
  subject_id: number;
  subject_name: string;
  subject_bookmarked: boolean;
  /** ISO date (YYYY-MM-DD) or null when no exam date is set. */
  exam_date: string | null;
  status: DocumentStatus;
  mode: DocumentMode;
  /** ISO datetime. */
  uploaded_at: string;
  topics_total: number;
  topics_ready: number;
}

/** Mirrors `backend/schemas/library.py::DocumentSummaryOut`. */

export type DocumentStatus = "uploaded" | "processing" | "ready" | "error";

export interface DocumentSummary {
  id: number;
  filename: string;
  subject_id: number;
  subject_name: string;
  /** ISO date (YYYY-MM-DD) or null when no exam date is set. */
  exam_date: string | null;
  status: DocumentStatus;
  /** ISO datetime. */
  uploaded_at: string;
  topics_total: number;
  topics_ready: number;
}

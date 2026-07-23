/** Mirrors `backend/schemas/subject.py`. */

export interface Subject {
  id: number;
  name: string;
  accent_color: string | null;
  /** ISO date (YYYY-MM-DD) or null. */
  exam_date: string | null;
  /** ISO datetime. */
  created_at: string;
  /** How many documents this subject has (0 for a freshly created, empty subject). */
  document_count: number;
}

export interface SubjectCreate {
  name: string;
  accent_color?: string | null;
  exam_date?: string | null;
}

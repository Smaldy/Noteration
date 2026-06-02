/** Mirrors `backend/schemas/assessment.py::AggregateAssessmentOut`. */

import type { FlashcardContent, MCQ } from "./study";

export type AssessmentScope = "chapters" | "documents" | "subjects";

export interface AggregateAssessment {
  scope: "chapter" | "document" | "subject";
  id: number;
  title: string;
  topic_count: number;
  mcqs: MCQ[];
  flashcards: FlashcardContent[];
}

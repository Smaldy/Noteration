/** Types mirroring the backend Exercise Duplicator schemas. */

export type VizType =
  | "mafs_function"
  | "mafs_parametric"
  | "plotly_3d"
  | "plotly_complex"
  | "matter_simulation"
  | "force_diagram";

export interface VizBlock {
  type: VizType;
  expression?: string;
  domain?: [number, number];
  params?: Record<string, unknown>;
}

export type ExerciseSessionStatus = "extracting" | "ready" | "error";
export type ExerciseStatus = "pending" | "searching" | "done" | "error";

export interface DuplicateResult {
  id: number;
  source_url: string | null;
  problem_text: string;
  viz: VizBlock | null;
  difficulty_score: number | null;
}

export interface ExtractedExercise {
  id: number;
  order_index: number;
  raw_text: string;
  topic: string;
  subtopic: string | null;
  difficulty_signals: string[];
  viz: VizBlock | null;
  status: ExerciseStatus;
  results: DuplicateResult[];
}

export interface ExerciseSession {
  id: number;
  document_hash: string;
  year_level: number;
  subject_hint: string | null;
  status: ExerciseSessionStatus;
  exercises: ExtractedExercise[];
}

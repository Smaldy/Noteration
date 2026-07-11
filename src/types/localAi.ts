/** Mirrors `backend/schemas/local_ai.py` (and the dataclass snapshots inside). */

export type LocalAiStatusValue =
  | "not_configured"
  | "detected"
  | "queued"
  | "installing_ollama"
  | "pulling"
  | "ready"
  | "failed";

/** Snapshot of `services/local_ai/hardware.HardwareProfile`. */
export interface HardwareSnapshot {
  os_name: string;
  arch: string;
  ram_bytes: number | null;
  gpu_vendor: string | null;
  gpu_name: string | null;
  vram_bytes: number | null;
  graphics_class: "dedicated" | "integrated" | "cpu_only";
  backend: "cuda" | "rocm" | "metal" | "cpu";
  usable_memory_bytes: number;
  eligible_quants: string[];
  confidence: "high" | "medium" | "low";
  sources: Record<string, string>;
  notes: string[];
}

/** Snapshot of `services/local_ai/selection.ModelChoice`. */
export interface ModelChoiceSnapshot {
  tag: string;
  display: string;
  quant: string;
  context: number;
  download_bytes: number;
  est_tok_s: number;
}

/** Snapshot of `services/local_ai/selection.SelectionResult`. */
export interface SelectionSnapshot {
  quality: ModelChoiceSnapshot | null;
  fast: ModelChoiceSnapshot | null;
  converged: boolean;
  weak_machine: boolean;
  messages: string[];
}

export interface RolePick {
  tag: string;
  quant: string;
}

export interface LocalAiStatus {
  status: LocalAiStatusValue;
  hardware: HardwareSnapshot | null;
  selection: SelectionSnapshot | null;
  chosen: { quality: RolePick | null; fast: RolePick | null } | null;
  quality_model: string | null;
  fast_model: string | null;
  pull_tag: string | null;
  pull_completed: number;
  pull_total: number;
  error: string | null;
  ollama: {
    binary_present: boolean;
    server_reachable: boolean;
    installed_models: string[];
  };
  manual_commands: string[];
}

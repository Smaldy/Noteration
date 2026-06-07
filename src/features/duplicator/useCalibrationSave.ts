import { useState } from "react";

import { api } from "@/lib/api";
import type { DuplicateResult } from "@/types/duplicator";

/**
 * "Save to calibration" state + action for a variant, shared by the inline
 * variant card and its full-screen view so both stay in their own (separate)
 * saved state without duplicating the request logic.
 */
export function useCalibrationSave(
  result: DuplicateResult,
  topic: string,
  subtopic: string | null,
  yearLevel: number,
) {
  const [saved, setSaved] = useState(false);
  const [saving, setSaving] = useState(false);

  const save = async () => {
    setSaving(true);
    try {
      await api.post("/duplicator/calibration/samples", {
        topic,
        subtopic,
        year_level: yearLevel,
        source_text: result.problem_text,
      });
      setSaved(true);
    } catch {
      // Non-fatal — the button just doesn't flip to "saved".
    } finally {
      setSaving(false);
    }
  };

  return { saved, saving, save };
}

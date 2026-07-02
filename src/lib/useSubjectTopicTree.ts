import { useEffect, useState } from "react";

import { ApiError, api } from "@/lib/api";
import type { SubjectTopicTree } from "@/types/assessment";
import type { DocumentMode } from "@/types/library";

export type SubjectTopicTreeStatus = "loading" | "loaded" | "error";

/**
 * Load a subject's document→chapter→topic tree while `enabled` (dialog open),
 * reloading whenever it re-opens or the subject changes. `fallbackError` is the
 * translated message used when the failure carries no API message; `mode`
 * scopes the tree to one section's documents (study vs exam).
 */
export function useSubjectTopicTree(
  subjectId: number,
  enabled: boolean,
  fallbackError: string,
  mode?: DocumentMode,
): {
  tree: SubjectTopicTree | null;
  status: SubjectTopicTreeStatus;
  error: string | null;
} {
  const [tree, setTree] = useState<SubjectTopicTree | null>(null);
  const [status, setStatus] = useState<SubjectTopicTreeStatus>("loading");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!enabled || !Number.isFinite(subjectId)) return;
    let cancelled = false;
    setStatus("loading");
    const query = mode ? `?mode=${mode}` : "";
    api
      .get<SubjectTopicTree>(`/subjects/${subjectId}/topics${query}`)
      .then((res) => {
        if (cancelled) return;
        setTree(res);
        setStatus("loaded");
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err instanceof ApiError ? err.message : fallbackError);
        setStatus("error");
      });
    return () => {
      cancelled = true;
    };
  }, [enabled, subjectId, mode, fallbackError]);

  return { tree, status, error };
}

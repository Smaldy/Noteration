import { Sparkles, Trash2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { ApiError } from "@/lib/api";
import { useCalendarStore } from "@/stores/calendar";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function AiPlanDialog({ open, onOpenChange }: Props) {
  const { catalog, fetchCatalog, generatePlan, deletePlan } = useCalendarStore();
  const [subjectId, setSubjectId] = useState("");
  const [studied, setStudied] = useState<Set<number>>(new Set());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<number | null>(null);

  useEffect(() => {
    if (!open) return;
    void fetchCatalog();
    setSubjectId("");
    setStudied(new Set());
    setBusy(false);
    setError(null);
    setDone(null);
  }, [open, fetchCatalog]);

  const topics = useMemo(
    () => catalog.find((s) => String(s.id) === subjectId)?.topics ?? [],
    [catalog, subjectId],
  );

  // When the subject changes, seed the checked set from each topic's stored
  // `studied` flag (checked = already studied = excluded from the plan).
  function selectSubject(id: string) {
    setSubjectId(id);
    setDone(null);
    setError(null);
    const subj = catalog.find((s) => String(s.id) === id);
    setStudied(new Set(subj?.topics.filter((t) => t.studied).map((t) => t.id)));
  }

  function toggleTopic(id: number) {
    setStudied((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function handleGenerate() {
    if (!subjectId) return;
    setBusy(true);
    setError(null);
    setDone(null);
    try {
      const entries = await generatePlan(Number(subjectId), Array.from(studied));
      setDone(entries.length);
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "Couldn't build a plan. Please try again.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function handleDeletePlan() {
    if (!subjectId) return;
    if (!window.confirm("Remove this subject's AI-generated plan?")) return;
    setBusy(true);
    setError(null);
    try {
      const removed = await deletePlan(Number(subjectId));
      setDone(null);
      setError(
        removed > 0 ? null : "There was no AI plan to remove for this subject.",
      );
    } catch {
      setError("Couldn't remove the plan. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  const remaining = topics.length - studied.size;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90dvh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Sparkles className="size-5 text-primary" />
            AI study plan
          </DialogTitle>
          <DialogDescription>
            Pick a subject and we'll spread its topics across your calendar up to
            the exam date, prioritising exam-critical topics and leaving a revision
            buffer. This replaces any previous AI plan for that subject; your own
            events stay put.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-2">
          <div className="space-y-2">
            <Label htmlFor="plan-subject">Subject</Label>
            <select
              id="plan-subject"
              className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
              value={subjectId}
              onChange={(e) => selectSubject(e.target.value)}
              disabled={busy}
            >
              <option value="">Select a subject…</option>
              {catalog.map((s) => (
                <option key={s.id} value={String(s.id)}>
                  {s.name}
                </option>
              ))}
            </select>
          </div>

          {subjectId && topics.length > 0 && (
            <div className="space-y-2">
              <Label>
                Already studied{" "}
                <span className="text-muted-foreground">
                  (checked topics are skipped — {remaining} to plan)
                </span>
              </Label>
              <div className="max-h-48 space-y-0.5 overflow-y-auto rounded-lg border p-2">
                {topics.map((t) => (
                  <label
                    key={t.id}
                    className="flex cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-muted"
                  >
                    <input
                      type="checkbox"
                      className="size-4 accent-[var(--primary)]"
                      checked={studied.has(t.id)}
                      onChange={() => toggleTopic(t.id)}
                      disabled={busy}
                    />
                    <span
                      className={
                        studied.has(t.id) ? "text-muted-foreground line-through" : ""
                      }
                    >
                      {t.title}
                    </span>
                  </label>
                ))}
              </div>
            </div>
          )}

          {subjectId && topics.length === 0 && (
            <p className="text-sm text-muted-foreground">
              This subject has no topics yet.
            </p>
          )}

          {done !== null && (
            <p className="rounded-md border border-emerald-500/40 bg-emerald-500/5 px-3 py-2 text-sm text-emerald-700 dark:text-emerald-400">
              Planned {done} study session{done === 1 ? "" : "s"}. They're on your
              calendar now.
            </p>
          )}
          {error && <p className="text-sm text-destructive">{error}</p>}
        </div>

        <DialogFooter className="sm:justify-between">
          <Button
            variant="ghost"
            className="text-destructive hover:text-destructive"
            onClick={() => void handleDeletePlan()}
            disabled={busy || !subjectId}
            title="Delete this subject's AI plan"
          >
            <Trash2 className="size-4" />
            Remove plan
          </Button>
          <div className="flex gap-2">
            <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>
              {done !== null ? "Done" : "Cancel"}
            </Button>
            <Button
              onClick={() => void handleGenerate()}
              disabled={busy || !subjectId || remaining <= 0}
            >
              {busy ? "Planning…" : done !== null ? "Re-plan" : "Generate plan"}
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

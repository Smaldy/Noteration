import { GitMerge } from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Switch } from "@/components/ui/switch";
import { TopicTreeSections } from "@/components/TopicTreeSections";
import { ApiError } from "@/lib/api";
import { useSubjectTopicTree } from "@/lib/useSubjectTopicTree";
import { cn } from "@/lib/utils";

interface MergeTopicDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** The subject whose topics are offered as merge targets. */
  subjectId: number;
  /** The topic being folded away (its content moves into the chosen target). */
  sourceTopicId: number;
  sourceTopicTitle: string;
  /** Performs the merge (store mutation + follow-up navigation); rejects on failure. */
  onMerge: (targetId: number, consolidate: boolean) => Promise<void>;
}

/**
 * Cross-document merge picker: fold one topic into any other topic of the same
 * subject (each lesson PDF creates its own topics, so the same subject piles up
 * duplicates — this is how they converge). Quiz/flashcard progress moves with
 * the rows; notes are appended, or rewritten into one document when the AI
 * consolidation toggle is on.
 */
export function MergeTopicDialog({
  open,
  onOpenChange,
  subjectId,
  sourceTopicId,
  sourceTopicTitle,
  onMerge,
}: MergeTopicDialogProps) {
  const { t } = useTranslation();

  const [targetId, setTargetId] = useState<number | null>(null);
  const [consolidate, setConsolidate] = useState(false);
  const [merging, setMerging] = useState(false);
  const [mergeError, setMergeError] = useState<string | null>(null);

  const {
    tree,
    status,
    error: loadError,
  } = useSubjectTopicTree(subjectId, open, t("study.merge.loadFailed"));

  // A study topic carries notes, and exam-prep topics never show a notes tab —
  // merging into one would make the notes invisible. So when the source lives
  // in a study document, exam documents are not offered as targets. (An
  // exam-prep source has no notes, so exam→exam merges stay allowed.)
  const sourceIsStudy =
    tree?.documents.some(
      (doc) =>
        doc.mode === "study" &&
        doc.chapters.some((chapter) =>
          chapter.topics.some((topic) => topic.id === sourceTopicId),
        ),
    ) ?? false;
  const targetDocuments = (tree?.documents ?? []).filter(
    (doc) => !(sourceIsStudy && doc.mode === "exam"),
  );

  // A fresh open starts with no target picked and any stale error cleared.
  useEffect(() => {
    if (!open) return;
    setTargetId(null);
    setMergeError(null);
  }, [open, subjectId]);

  async function handleMerge() {
    if (targetId === null) return;
    setMerging(true);
    setMergeError(null);
    try {
      await onMerge(targetId, consolidate);
      onOpenChange(false);
    } catch (err) {
      setMergeError(
        err instanceof ApiError ? err.message : t("study.merge.failed"),
      );
    } finally {
      setMerging(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[85vh] w-full max-w-lg flex-col gap-0 overflow-hidden p-0">
        <DialogHeader className="border-b px-6 py-4 text-left">
          <DialogTitle className="flex items-center gap-2">
            <GitMerge className="size-4 text-primary" />
            {t("study.merge.title", { title: sourceTopicTitle })}
          </DialogTitle>
          <DialogDescription>{t("study.merge.description")}</DialogDescription>
        </DialogHeader>

        <div className="min-h-0 flex-1 overflow-y-auto px-6 py-4">
          {status === "loading" && (
            <p className="py-12 text-center text-sm text-muted-foreground">
              {t("common.loading")}
            </p>
          )}
          {status === "error" && (
            <p className="py-12 text-center text-sm text-destructive">{loadError}</p>
          )}
          {status === "loaded" && (
            <div className="space-y-5">
              <TopicTreeSections
                documents={targetDocuments}
                topicFilter={(topic) => topic.id !== sourceTopicId}
                documentBadge={(doc) =>
                  doc.mode === "exam" && (
                    <Badge variant="secondary" className="shrink-0">
                      {t("study.merge.examBadge")}
                    </Badge>
                  )
                }
                renderTopic={(topic) => (
                  <li key={topic.id}>
                    <button
                      type="button"
                      onClick={() => setTargetId(topic.id)}
                      className={cn(
                        "flex w-full items-center gap-2.5 rounded-md px-2 py-1.5 text-left text-sm transition-colors hover:bg-accent/60",
                        targetId === topic.id &&
                          "bg-primary/10 font-medium text-primary",
                      )}
                    >
                      <span
                        aria-hidden
                        className={cn(
                          "size-3.5 shrink-0 rounded-full border-2 transition-colors",
                          targetId === topic.id
                            ? "border-primary bg-primary"
                            : "border-input",
                        )}
                      />
                      <span className="min-w-0 flex-1 truncate">
                        {topic.title}
                      </span>
                    </button>
                  </li>
                )}
              />
            </div>
          )}
        </div>

        <div className="space-y-3 border-t px-6 py-4">
          <label className="flex cursor-pointer select-none items-center justify-between gap-3">
            <span className="text-sm">
              {t("study.merge.consolidate")}
              <span className="block text-xs text-muted-foreground">
                {t("study.merge.consolidateHint")}
              </span>
            </span>
            <Switch checked={consolidate} onCheckedChange={setConsolidate} />
          </label>
          {mergeError && <p className="text-sm text-destructive">{mergeError}</p>}
          <div className="flex justify-end gap-2">
            <Button variant="outline" size="sm" onClick={() => onOpenChange(false)}>
              {t("common.cancel")}
            </Button>
            <Button
              size="sm"
              disabled={targetId === null || merging}
              onClick={() => void handleMerge()}
            >
              {merging ? t("study.merge.merging") : t("study.merge.confirm")}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

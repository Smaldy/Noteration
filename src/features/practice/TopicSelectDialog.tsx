import { AnimatePresence, motion } from "framer-motion";
import { Check, Layers, Minus } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { ApiError, api } from "@/lib/api";
import { cn } from "@/lib/utils";
import type {
  SelectableTopic,
  SubjectTopicTree,
} from "@/types/assessment";
import type { DocumentMode } from "@/types/library";

interface TopicSelectDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** The subject whose topics are offered for selection. */
  subjectId: number;
  /** Scope the tree to one section's documents (study vs exam), to stay coherent. */
  mode?: DocumentMode;
}

type Status = "loading" | "loaded" | "error";

/** A topic counts as selectable only if it has something to pool. */
function hasContent(topic: SelectableTopic): boolean {
  return topic.mcq_count > 0 || topic.flashcard_count > 0;
}

/**
 * Custom-practice selector: pick any subset of a subject's topics (across all its
 * PDFs) and launch a pooled quiz or flashcard run. "Select all" ticks everything
 * with content in one tap. Reuses the assessment `topics` scope on the practice
 * page, so the chosen ids travel in the URL.
 */
export function TopicSelectDialog({
  open,
  onOpenChange,
  subjectId,
  mode,
}: TopicSelectDialogProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();

  const [tree, setTree] = useState<SubjectTopicTree | null>(null);
  const [status, setStatus] = useState<Status>("loading");
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<Set<number>>(new Set());

  // (Re)load the subject's topic tree whenever the dialog opens for a subject.
  useEffect(() => {
    if (!open || !Number.isFinite(subjectId)) return;
    let cancelled = false;
    setStatus("loading");
    setSelected(new Set());
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
        setError(
          err instanceof ApiError ? err.message : t("exam.practice.selector.loadFailed"),
        );
        setStatus("error");
      });
    return () => {
      cancelled = true;
    };
  }, [open, subjectId, mode, t]);

  // All topics with content, flattened — the universe for "select all" + totals.
  const selectableTopics = useMemo(() => {
    const all: SelectableTopic[] = [];
    for (const doc of tree?.documents ?? [])
      for (const chapter of doc.chapters)
        for (const topic of chapter.topics) if (hasContent(topic)) all.push(topic);
    return all;
  }, [tree]);

  const totals = useMemo(() => {
    let mcqs = 0;
    let cards = 0;
    for (const topic of selectableTopics)
      if (selected.has(topic.id)) {
        mcqs += topic.mcq_count;
        cards += topic.flashcard_count;
      }
    return { mcqs, cards };
  }, [selectableTopics, selected]);

  const allSelected =
    selectableTopics.length > 0 && selected.size === selectableTopics.length;
  const someSelected = selected.size > 0;

  function toggle(id: number) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function toggleMany(ids: number[], on: boolean) {
    setSelected((prev) => {
      const next = new Set(prev);
      for (const id of ids) {
        if (on) next.add(id);
        else next.delete(id);
      }
      return next;
    });
  }

  function toggleAll() {
    if (allSelected) setSelected(new Set());
    else setSelected(new Set(selectableTopics.map((topic) => topic.id)));
  }

  function launch(tab: "quiz" | "flashcards") {
    const ids = [...selected];
    if (ids.length === 0) return;
    navigate(`/exam/practice/topics/set?ids=${ids.join(",")}&tab=${tab}`);
    onOpenChange(false);
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[85vh] w-full max-w-2xl flex-col gap-0 overflow-hidden p-0">
        <DialogHeader className="border-b px-6 py-4 text-left">
          <DialogTitle className="flex items-center gap-2">
            <Layers className="size-4 text-primary" />
            {t("exam.practice.selector.title")}
          </DialogTitle>
          <DialogDescription>
            {t("exam.practice.selector.description")}
          </DialogDescription>
        </DialogHeader>

        {/* Toolbar: master select-all + live selection summary. */}
        {status === "loaded" && selectableTopics.length > 0 && (
          <div className="flex items-center justify-between gap-3 border-b bg-muted/30 px-6 py-2.5">
            <button
              type="button"
              onClick={toggleAll}
              className="flex items-center gap-2 text-sm font-medium text-foreground transition-colors hover:text-primary"
            >
              <CheckBox checked={allSelected} indeterminate={someSelected && !allSelected} />
              {allSelected
                ? t("exam.practice.selector.clear")
                : t("exam.practice.selector.selectAll")}
            </button>
            <span className="text-xs tabular-nums text-muted-foreground">
              {t("exam.practice.selector.selected", { count: selected.size })}
            </span>
          </div>
        )}

        {/* Body */}
        <div className="min-h-0 flex-1 overflow-y-auto px-6 py-4">
          {status === "loading" && (
            <p className="py-12 text-center text-sm text-muted-foreground">
              {t("exam.practice.selector.loading")}
            </p>
          )}
          {status === "error" && (
            <p className="py-12 text-center text-sm text-destructive">{error}</p>
          )}
          {status === "loaded" && selectableTopics.length === 0 && (
            <p className="py-12 text-center text-sm text-muted-foreground">
              {t("exam.practice.selector.empty")}
            </p>
          )}
          {status === "loaded" && selectableTopics.length > 0 && (
            <div className="space-y-6">
              {tree?.documents.map((doc) => {
                const docTopicIds = doc.chapters
                  .flatMap((chapter) => chapter.topics)
                  .filter(hasContent)
                  .map((topic) => topic.id);
                const docAllOn = docTopicIds.every((id) => selected.has(id));
                return (
                  <section key={doc.id}>
                    <div className="mb-2 flex items-center justify-between gap-2">
                      <div className="flex min-w-0 items-center gap-2">
                        <span className="truncate text-sm font-semibold">
                          {doc.filename}
                        </span>
                        <Badge variant="secondary" className="shrink-0">
                          {doc.mode === "exam"
                            ? t("exam.practice.selector.examBadge")
                            : t("exam.practice.selector.studyBadge")}
                        </Badge>
                      </div>
                      <button
                        type="button"
                        onClick={() => toggleMany(docTopicIds, !docAllOn)}
                        className="shrink-0 rounded px-1.5 py-0.5 text-xs font-medium text-primary hover:bg-primary/10"
                      >
                        {docAllOn
                          ? t("exam.practice.selector.clear")
                          : t("exam.practice.selector.selectAll")}
                      </button>
                    </div>
                    <div className="space-y-3 border-l border-border/60 pl-3">
                      {doc.chapters.map((chapter) => (
                        <div key={chapter.id}>
                          <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                            {chapter.title}
                          </p>
                          <ul className="space-y-0.5">
                            {chapter.topics.map((topic) => (
                              <TopicRow
                                key={topic.id}
                                topic={topic}
                                checked={selected.has(topic.id)}
                                onToggle={() => toggle(topic.id)}
                              />
                            ))}
                          </ul>
                        </div>
                      ))}
                    </div>
                  </section>
                );
              })}
            </div>
          )}
        </div>

        {/* Footer: launch a pooled quiz or flashcard run from the selection. */}
        <div className="flex items-center justify-between gap-3 border-t px-6 py-3">
          <AnimatePresence mode="wait" initial={false}>
            <motion.span
              key={someSelected ? "totals" : "hint"}
              initial={{ opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -4 }}
              transition={{ duration: 0.15 }}
              className="text-xs tabular-nums text-muted-foreground"
            >
              {someSelected
                ? t("exam.practice.selector.totals", {
                    mcqs: totals.mcqs,
                    cards: totals.cards,
                  })
                : ""}
            </motion.span>
          </AnimatePresence>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={!someSelected}
              onClick={() => launch("flashcards")}
            >
              {t("exam.practice.selector.startCards")}
            </Button>
            <Button size="sm" disabled={!someSelected} onClick={() => launch("quiz")}>
              {t("exam.practice.selector.startQuiz")}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function TopicRow({
  topic,
  checked,
  onToggle,
}: {
  topic: SelectableTopic;
  checked: boolean;
  onToggle: () => void;
}) {
  const { t } = useTranslation();
  const disabled = !hasContent(topic);
  return (
    <li>
      <button
        type="button"
        disabled={disabled}
        onClick={onToggle}
        className={cn(
          "flex w-full items-center gap-2.5 rounded-md px-2 py-1.5 text-left text-sm transition-colors",
          disabled
            ? "cursor-not-allowed text-muted-foreground/50"
            : "hover:bg-accent/60",
          checked && "bg-primary/5",
        )}
      >
        <CheckBox checked={checked} disabled={disabled} />
        <span className="min-w-0 flex-1 truncate">{topic.title}</span>
        {!disabled && (
          <span className="shrink-0 text-xs tabular-nums text-muted-foreground">
            {t("exam.practice.selector.perTopic", {
              mcqs: topic.mcq_count,
              cards: topic.flashcard_count,
            })}
          </span>
        )}
      </button>
    </li>
  );
}

function CheckBox({
  checked,
  indeterminate = false,
  disabled = false,
}: {
  checked: boolean;
  indeterminate?: boolean;
  disabled?: boolean;
}) {
  const active = checked || indeterminate;
  return (
    <span
      aria-hidden
      className={cn(
        "flex size-4 shrink-0 items-center justify-center rounded border transition-colors",
        active
          ? "border-primary bg-primary text-primary-foreground"
          : "border-input bg-background",
        disabled && "opacity-40",
      )}
    >
      {indeterminate ? (
        <Minus className="size-3" strokeWidth={3} />
      ) : checked ? (
        <Check className="size-3" strokeWidth={3} />
      ) : null}
    </span>
  );
}

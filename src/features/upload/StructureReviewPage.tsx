import { ArrowLeft, Plus, Trash2 } from "lucide-react";
import { type ReactNode, useEffect, useReducer, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { cn } from "@/lib/utils";
import { ApiError, api } from "@/lib/api";
import type {
  ConfirmStructureResult,
  ProposedStructure,
} from "@/types/structure";

import { PriorityPills } from "./PriorityPills";
import {
  emptyEditState,
  generatableTopicCount,
  isChapterSkipped,
  isConfirmable,
  structureReducer,
  toConfirmPayload,
} from "./structureReducer";

type LoadStatus = "loading" | "ready" | "error";

// Rough per-topic token estimate; mirrors EST_TOKENS_PER_TOPIC in
// backend/services/queue.py (notes + assessment, bounded input + capped output).
const EST_TOKENS_PER_TOPIC = 8000;

export function StructureReviewPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { t } = useTranslation();
  const [searchParams] = useSearchParams();
  const documentId = Number(id);
  // Exam-prep uploads pass ?from=exam so we return to the right section.
  const fromExam = searchParams.get("from") === "exam";
  const homePath = fromExam ? "/exam" : "/";

  const [status, setStatus] = useState<LoadStatus>("loading");
  const [loadError, setLoadError] = useState<string | null>(null);
  const [needsManual, setNeedsManual] = useState(false);
  const [hasHeadings, setHasHeadings] = useState(true);
  const [state, dispatch] = useReducer(structureReducer, emptyEditState);
  const [examDate, setExamDate] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    if (!Number.isFinite(documentId)) {
      setStatus("error");
      setLoadError(t("upload.review.invalidDocument"));
      return;
    }
    setStatus("loading");
    api
      .get<ProposedStructure>(`/documents/${documentId}/structure`)
      .then((structure) => {
        if (cancelled) return;
        setNeedsManual(structure.needs_manual);
        setHasHeadings(structure.has_headings);
        dispatch({ type: "init", structure });
        setStatus("ready");
      })
      .catch((err) => {
        if (cancelled) return;
        setLoadError(
          err instanceof ApiError ? err.message : t("upload.review.loadFailed"),
        );
        setStatus("error");
      });
    return () => {
      cancelled = true;
    };
  }, [documentId, t]);

  async function handleConfirm() {
    setSubmitting(true);
    setSubmitError(null);
    try {
      await api.post<ConfirmStructureResult>(
        `/documents/${documentId}/structure`,
        toConfirmPayload(state, examDate.trim() === "" ? null : examDate),
      );
      // Go to the Queue so the user immediately sees which chapters are
      // processing (and can resume the paused ones) rather than the Library.
      // The queue lists every book's chapter lanes, so no document scope is
      // needed — they stay reachable whenever the user returns.
      navigate("/queue");
    } catch (err) {
      setSubmitError(
        err instanceof ApiError ? err.message : t("upload.review.confirmFailed"),
      );
      setSubmitting(false);
    }
  }

  if (status === "loading") {
    return <CenteredNote>{t("upload.review.loading")}</CenteredNote>;
  }

  if (status === "error") {
    return (
      <div className="mx-auto max-w-3xl px-6 py-10">
        <BackLink onClick={() => navigate(homePath)} exam={fromExam} />
        <div className="rounded-lg border border-destructive/40 bg-destructive/5 p-4 text-sm text-destructive">
          {loadError}
        </div>
      </div>
    );
  }

  const generatable = generatableTopicCount(state);
  const confirmable = isConfirmable(state) && !submitting;

  return (
    <div className="mx-auto max-w-3xl px-6 py-10">
      <BackLink onClick={() => navigate(homePath)} exam={fromExam} />
      <h1 className="text-2xl font-semibold tracking-tight">
        {t("upload.review.title")}
      </h1>
      <p className="mt-1 text-sm text-muted-foreground">{t("upload.review.intro")}</p>

      {needsManual && (
        <div className="mt-4 rounded-lg border border-amber-500/40 bg-amber-500/5 p-3 text-sm">
          {t("upload.review.needsManual")}
        </div>
      )}

      {!hasHeadings && !needsManual && (
        <div className="mt-4 rounded-lg border border-amber-500/40 bg-amber-500/5 p-3 text-sm">
          {t("upload.review.noHeadings")}
        </div>
      )}

      <div className="mt-6 space-y-4">
        {state.chapters.map((chapter) => {
          const skipped = isChapterSkipped(chapter);
          const running = chapter.queueState !== "paused";
          const range =
            chapter.pageStart != null && chapter.pageEnd != null
              ? t("upload.review.pages", {
                  start: chapter.pageStart,
                  end: chapter.pageEnd,
                })
              : null;
          return (
          <div
            key={chapter.uid}
            className={cn(
              "rounded-xl border p-4 transition-colors",
              skipped
                ? "border-dashed bg-muted/30 opacity-70"
                : running
                  ? "border-l-2 border-l-primary bg-primary-soft/30"
                  : "",
            )}
          >
            <div className="flex items-center gap-2">
              <Input
                value={chapter.title}
                placeholder={t("upload.review.chapterTitlePlaceholder")}
                onChange={(e) =>
                  dispatch({
                    type: "setChapterTitle",
                    cuid: chapter.uid,
                    title: e.target.value,
                  })
                }
                className={cn(
                  "font-medium",
                  skipped && "text-muted-foreground line-through",
                )}
              />
              {range && (
                <Badge
                  variant="secondary"
                  className="shrink-0 tabular-nums font-normal text-muted-foreground"
                >
                  {range}
                </Badge>
              )}
              {skipped ? (
                <Badge
                  variant="outline"
                  className="shrink-0 text-[10px] uppercase tracking-wide text-muted-foreground"
                >
                  {t("upload.review.autoSkipped")}
                </Badge>
              ) : (
                <label className="flex shrink-0 cursor-pointer select-none items-center gap-2">
                  <span
                    className={cn(
                      "text-xs font-medium tabular-nums",
                      running ? "text-primary" : "text-muted-foreground",
                    )}
                  >
                    {running ? t("upload.review.process") : t("upload.review.paused")}
                  </span>
                  <Switch
                    checked={running}
                    onCheckedChange={(on) =>
                      dispatch({
                        type: "setChapterQueueState",
                        cuid: chapter.uid,
                        state: on ? "running" : "paused",
                      })
                    }
                    aria-label={t("upload.review.processChapterAria")}
                  />
                </label>
              )}
              <Button
                variant="ghost"
                size="icon"
                title={t("upload.review.removeChapter")}
                onClick={() => dispatch({ type: "removeChapter", cuid: chapter.uid })}
              >
                <Trash2 />
              </Button>
            </div>

            <div
              className={cn("mt-3 space-y-2 pl-2", skipped && "opacity-70")}
            >
              {chapter.topics.map((topic) => (
                <div key={topic.uid} className="flex items-center gap-2">
                  <Input
                    value={topic.title}
                    placeholder={t("upload.review.topicTitlePlaceholder")}
                    onChange={(e) =>
                      dispatch({
                        type: "setTopicTitle",
                        cuid: chapter.uid,
                        tuid: topic.uid,
                        title: e.target.value,
                      })
                    }
                  />
                  <PriorityPills
                    value={topic.priority}
                    onChange={(priority) =>
                      dispatch({
                        type: "setTopicPriority",
                        cuid: chapter.uid,
                        tuid: topic.uid,
                        priority,
                      })
                    }
                  />
                  <Button
                    variant="ghost"
                    size="icon"
                    title={t("upload.review.removeTopic")}
                    onClick={() =>
                      dispatch({
                        type: "removeTopic",
                        cuid: chapter.uid,
                        tuid: topic.uid,
                      })
                    }
                  >
                    <Trash2 />
                  </Button>
                </div>
              ))}
              <Button
                variant="ghost"
                size="sm"
                onClick={() => dispatch({ type: "addTopic", cuid: chapter.uid })}
              >
                <Plus />
                {t("upload.review.addTopic")}
              </Button>
            </div>
          </div>
          );
        })}

        <Button variant="outline" onClick={() => dispatch({ type: "addChapter" })}>
          <Plus />
          {t("upload.review.addChapter")}
        </Button>
      </div>

      <div className="mt-8 space-y-2">
        <Label htmlFor="exam-date">{t("upload.review.examDate")}</Label>
        <Input
          id="exam-date"
          type="date"
          value={examDate}
          onChange={(e) => setExamDate(e.target.value)}
          className="w-auto"
        />
        <p className="text-xs text-muted-foreground">
          {t("upload.review.examDateHint")}
        </p>
      </div>

      <div className="mt-8 flex items-center justify-between gap-4 border-t pt-6">
        <p className="text-sm text-muted-foreground">
          {t("upload.review.estimate", {
            count: generatable,
            tokens: t("upload.review.tokens", {
              count: Math.round((generatable * EST_TOKENS_PER_TOPIC) / 1000),
            }),
          })}
        </p>
        <Button onClick={() => void handleConfirm()} disabled={!confirmable}>
          {submitting ? t("upload.review.confirming") : t("upload.review.confirm")}
        </Button>
      </div>

      {submitError && (
        <p className="mt-3 text-right text-sm text-destructive">{submitError}</p>
      )}
    </div>
  );
}

function CenteredNote({ children }: { children: ReactNode }) {
  return (
    <div className="mx-auto max-w-3xl px-6 py-20 text-center text-sm text-muted-foreground">
      {children}
    </div>
  );
}

function BackLink({ onClick, exam = false }: { onClick: () => void; exam?: boolean }) {
  const { t } = useTranslation();
  return (
    <button
      type="button"
      onClick={onClick}
      className="mb-4 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
    >
      <ArrowLeft className="size-4" />
      {exam ? t("upload.review.backToExam") : t("upload.review.backToLibrary")}
    </button>
  );
}

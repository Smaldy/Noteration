import { ArrowLeft, Plus, Trash2 } from "lucide-react";
import { type ReactNode, useEffect, useReducer, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ApiError, api } from "@/lib/api";
import type {
  ConfirmStructureResult,
  ProposedStructure,
} from "@/types/structure";

import { PriorityPills } from "./PriorityPills";
import {
  emptyEditState,
  generatableTopicCount,
  isConfirmable,
  structureReducer,
  toConfirmPayload,
} from "./structureReducer";

type LoadStatus = "loading" | "ready" | "error";

// Rough per-topic token estimate; mirrors EST_TOKENS_PER_TOPIC in
// backend/services/queue.py (notes + assessment, bounded input + capped output).
const EST_TOKENS_PER_TOPIC = 8000;

function estTokensLabel(topics: number): string {
  const k = Math.round((topics * EST_TOKENS_PER_TOPIC) / 1000);
  return `${k}k tokens`;
}

export function StructureReviewPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const documentId = Number(id);

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
      setLoadError("Invalid document.");
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
          err instanceof ApiError ? err.message : "Failed to load the structure.",
        );
        setStatus("error");
      });
    return () => {
      cancelled = true;
    };
  }, [documentId]);

  async function handleConfirm() {
    setSubmitting(true);
    setSubmitError(null);
    try {
      await api.post<ConfirmStructureResult>(
        `/documents/${documentId}/structure`,
        toConfirmPayload(state, examDate.trim() === "" ? null : examDate),
      );
      navigate("/");
    } catch (err) {
      setSubmitError(
        err instanceof ApiError ? err.message : "Could not confirm. Try again.",
      );
      setSubmitting(false);
    }
  }

  if (status === "loading") {
    return (
      <CenteredNote>Reading your PDF and detecting structure…</CenteredNote>
    );
  }

  if (status === "error") {
    return (
      <div className="mx-auto max-w-3xl px-6 py-10">
        <BackLink onClick={() => navigate("/")} />
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
      <BackLink onClick={() => navigate("/")} />
      <h1 className="text-2xl font-semibold tracking-tight">Review structure</h1>
      <p className="mt-1 text-sm text-muted-foreground">
        Rename, add, or remove chapters and topics, and set each topic&apos;s
        priority. Nothing is generated until you confirm.
      </p>

      {needsManual && (
        <div className="mt-4 rounded-lg border border-amber-500/40 bg-amber-500/5 p-3 text-sm">
          We couldn&apos;t detect a structure automatically. Add chapters and
          topics below to build one.
        </div>
      )}

      {!hasHeadings && !needsManual && (
        <div className="mt-4 rounded-lg border border-amber-500/40 bg-amber-500/5 p-3 text-sm">
          This PDF has no detected headings, so notes are scoped to each topic by
          its position in the document. Keep topics in the order they appear, and
          split long sections into separate topics for the most relevant notes.
        </div>
      )}

      <div className="mt-6 space-y-4">
        {state.chapters.map((chapter) => (
          <div key={chapter.uid} className="rounded-xl border p-4">
            <div className="flex items-center gap-2">
              <Input
                value={chapter.title}
                placeholder="Chapter title"
                onChange={(e) =>
                  dispatch({
                    type: "setChapterTitle",
                    cuid: chapter.uid,
                    title: e.target.value,
                  })
                }
                className="font-medium"
              />
              <Button
                variant="ghost"
                size="icon"
                title="Remove chapter"
                onClick={() => dispatch({ type: "removeChapter", cuid: chapter.uid })}
              >
                <Trash2 />
              </Button>
            </div>

            <div className="mt-3 space-y-2 pl-2">
              {chapter.topics.map((topic) => (
                <div key={topic.uid} className="flex items-center gap-2">
                  <Input
                    value={topic.title}
                    placeholder="Topic title"
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
                    title="Remove topic"
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
                Add topic
              </Button>
            </div>
          </div>
        ))}

        <Button variant="outline" onClick={() => dispatch({ type: "addChapter" })}>
          <Plus />
          Add chapter
        </Button>
      </div>

      <div className="mt-8 space-y-2">
        <Label htmlFor="exam-date">Exam date (optional)</Label>
        <Input
          id="exam-date"
          type="date"
          value={examDate}
          onChange={(e) => setExamDate(e.target.value)}
          className="w-auto"
        />
        <p className="text-xs text-muted-foreground">
          Setting an exam date pulls reviews forward so nothing lands after it.
        </p>
      </div>

      <div className="mt-8 flex items-center justify-between gap-4 border-t pt-6">
        <p className="text-sm text-muted-foreground">
          ~{generatable} {generatable === 1 ? "topic" : "topics"} to generate ·
          ~{estTokensLabel(generatable)} · free tier ($0) · paid only if you
          enable it.
        </p>
        <Button onClick={() => void handleConfirm()} disabled={!confirmable}>
          {submitting ? "Confirming…" : "Confirm & start"}
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

function BackLink({ onClick }: { onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="mb-4 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
    >
      <ArrowLeft className="size-4" />
      Back to library
    </button>
  );
}

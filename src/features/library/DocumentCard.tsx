import { useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import {
  AudioLines,
  CalendarDays,
  Download,
  FileText,
  GripVertical,
  Loader2,
  RotateCw,
  Trash2,
} from "lucide-react";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { BookmarkButton } from "@/features/bookmarks/BookmarkButton";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { Transcript } from "@/types/document";
import type { DocumentSummary } from "@/types/library";

import { StatusBadge } from "./StatusBadge";

function formatExamDate(iso: string, locale: string): string {
  // `iso` is a date-only string (YYYY-MM-DD); parse as local to avoid a TZ shift.
  const [y, m, d] = iso.split("-").map(Number);
  const date = new Date(y, m - 1, d);
  return date.toLocaleDateString(locale, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

/** Strip the extension for a friendly download name. */
function baseName(filename: string): string {
  const dot = filename.lastIndexOf(".");
  return dot > 0 ? filename.slice(0, dot) : filename;
}

export function DocumentCard({
  doc,
  onDelete,
  onToggleBookmark,
  onRetryTranscription,
  actions,
}: {
  doc: DocumentSummary;
  onDelete?: (doc: DocumentSummary) => void;
  onToggleBookmark: (subjectId: number, bookmarked: boolean) => void;
  /** Re-queue a failed/rate-limited audio transcription. */
  onRetryTranscription?: (doc: DocumentSummary) => void;
  /** Optional footer actions (e.g. Exam Prep deck Quiz/Flashcards buttons). */
  actions?: ReactNode;
}) {
  const navigate = useNavigate();
  const { t, i18n } = useTranslation();
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } =
    useSortable({ id: doc.id });

  const isAudio = doc.source_type === "audio";
  const transcribing = doc.status === "transcribing";
  const audioError = isAudio && doc.status === "error";
  // A transcript exists once transcription has finished (any state past it).
  const hasTranscript =
    isAudio && (doc.status === "uploaded" || doc.status === "processing" || doc.status === "ready");

  const progress =
    doc.topics_total === 0
      ? t("library.card.noTopicsYet")
      : t("library.card.topicsReady", {
          ready: doc.topics_ready,
          total: doc.topics_total,
        });

  // Transcribing/failed-audio cards aren't navigable (no content yet). Otherwise
  // not-yet-confirmed documents go to structure review; confirmed ones to study.
  const clickable = !transcribing && !audioError;
  const destination =
    doc.status === "uploaded"
      ? `/documents/${doc.id}/review`
      : `/documents/${doc.id}/study`;

  function go() {
    if (clickable) navigate(destination);
  }

  async function exportTranscript() {
    try {
      const transcript = await api.get<Transcript>(
        `/documents/${doc.id}/transcript`,
      );
      const blob = new Blob([transcript.markdown], { type: "text/markdown" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `${baseName(doc.filename)}.md`;
      link.click();
      URL.revokeObjectURL(url);
    } catch {
      window.alert(t("library.card.transcriptUnavailable"));
    }
  }

  const Icon = isAudio ? AudioLines : FileText;
  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
  };

  return (
    <div
      ref={setNodeRef}
      style={style}
      className={cn(
        "h-full",
        isDragging && "z-10 opacity-80 [&_*]:cursor-grabbing",
      )}
    >
      <Card
        role={clickable ? "button" : undefined}
        tabIndex={clickable ? 0 : undefined}
        onClick={go}
        onKeyDown={(e) => {
          if (clickable && (e.key === "Enter" || e.key === " ")) {
            e.preventDefault();
            go();
          }
        }}
        className={cn(
          "h-full transition-all",
          clickable
            ? "cursor-pointer hover:-translate-y-1 hover:shadow-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            : "cursor-default",
          isDragging && "shadow-xl ring-2 ring-primary/40",
        )}
      >
        <CardHeader>
          <div className="flex items-start justify-between gap-2">
            <div className="flex min-w-0 items-center gap-1.5">
              <button
                type="button"
                aria-label={t("library.card.dragToReorder")}
                title={t("library.card.dragToReorder")}
                onClick={(e) => e.stopPropagation()}
                className="-ml-1 shrink-0 cursor-grab touch-none rounded-md p-1 text-muted-foreground/50 transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring active:cursor-grabbing"
                {...attributes}
                {...listeners}
              >
                <GripVertical className="size-4" />
              </button>
              <Icon className="shrink-0 text-muted-foreground" />
              <CardTitle className="truncate">{doc.subject_name}</CardTitle>
            </div>
            <div className="flex shrink-0 items-center gap-1">
              <BookmarkButton
                bookmarked={doc.subject_bookmarked}
                label={doc.subject_name}
                onToggle={(next) => onToggleBookmark(doc.subject_id, next)}
              />
              {onDelete && (
                <Button
                  variant="ghost"
                  size="icon"
                  title={t("library.card.deleteDocument")}
                  aria-label={t("library.card.deleteDocumentAria", {
                    name: doc.filename,
                  })}
                  className="size-7 text-muted-foreground hover:text-destructive"
                  onClick={(e) => {
                    e.stopPropagation();
                    onDelete(doc);
                  }}
                >
                  <Trash2 className="size-4" />
                </Button>
              )}
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-2 text-sm text-muted-foreground">
          {/* Status lives here rather than the header so long subject names
              keep the full title row. */}
          <div className="flex items-center justify-between gap-2">
            <p className="min-w-0 truncate" title={doc.filename}>
              {doc.filename}
            </p>
            <StatusBadge status={doc.status} />
          </div>

          {transcribing ? (
            <p className="flex items-center gap-2 text-primary">
              <Loader2 className="size-3.5 animate-spin" />
              {doc.status_detail ?? t("library.card.transcribing")}
            </p>
          ) : audioError ? (
            <div
              className="space-y-2"
              onClick={(e) => e.stopPropagation()}
              onKeyDown={(e) => e.stopPropagation()}
              role="presentation"
            >
              <p className="text-destructive">
                {doc.status_detail ?? t("library.card.transcriptionFailed")}
              </p>
              {onRetryTranscription && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => onRetryTranscription(doc)}
                >
                  <RotateCw className="size-3.5" />
                  {t("library.card.retryTranscription")}
                </Button>
              )}
            </div>
          ) : (
            <>
              <div className="flex flex-wrap items-center gap-2">
                <p>{progress}</p>
                {doc.chapters_running > 0 && (
                  <span className="inline-flex items-center rounded-full bg-primary-soft px-2 py-0.5 text-xs font-medium text-primary-soft-foreground tabular-nums">
                    {t("library.card.chaptersProcessing", {
                      running: doc.chapters_running,
                      total: doc.chapters_total,
                    })}
                  </span>
                )}
              </div>
              <p className="flex items-center gap-1.5">
                <CalendarDays className="size-3.5" />
                {doc.exam_date
                  ? formatExamDate(doc.exam_date, i18n.language)
                  : t("library.card.noExamDate")}
              </p>
            </>
          )}

          {hasTranscript && (
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                void exportTranscript();
              }}
              className="inline-flex items-center gap-1.5 rounded-sm text-xs font-medium text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <Download className="size-3.5" />
              {t("library.card.exportTranscript")}
            </button>
          )}

          {actions && (
            <div
              className="pt-1"
              onClick={(e) => e.stopPropagation()}
              onKeyDown={(e) => e.stopPropagation()}
              role="presentation"
            >
              {actions}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

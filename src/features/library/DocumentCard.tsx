import { useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { CalendarDays, FileText, GripVertical, Trash2 } from "lucide-react";
import type { ReactNode } from "react";
import { useNavigate } from "react-router-dom";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { BookmarkButton } from "@/features/bookmarks/BookmarkButton";
import { cn } from "@/lib/utils";
import type { DocumentSummary } from "@/types/library";

import { StatusBadge } from "./StatusBadge";

function formatExamDate(iso: string | null): string {
  if (!iso) return "No exam date";
  // `iso` is a date-only string (YYYY-MM-DD); parse as local to avoid a TZ shift.
  const [y, m, d] = iso.split("-").map(Number);
  const date = new Date(y, m - 1, d);
  return date.toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

export function DocumentCard({
  doc,
  onDelete,
  onToggleBookmark,
  actions,
}: {
  doc: DocumentSummary;
  onDelete?: (doc: DocumentSummary) => void;
  onToggleBookmark: (subjectId: number, bookmarked: boolean) => void;
  /** Optional footer actions (e.g. Exam Prep deck Quiz/Flashcards buttons). */
  actions?: ReactNode;
}) {
  const navigate = useNavigate();
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } =
    useSortable({ id: doc.id });

  const progress =
    doc.topics_total === 0
      ? "No topics yet"
      : `${doc.topics_ready} of ${doc.topics_total} topics ready`;

  // Not-yet-confirmed documents go to structure review; confirmed ones to study.
  const destination =
    doc.status === "uploaded"
      ? `/documents/${doc.id}/review`
      : `/documents/${doc.id}/study`;

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
        role="button"
        tabIndex={0}
        onClick={() => navigate(destination)}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            navigate(destination);
          }
        }}
        className={cn(
          "h-full cursor-pointer transition-all hover:-translate-y-1 hover:shadow-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
          isDragging && "shadow-xl ring-2 ring-primary/40",
        )}
      >
        <CardHeader>
          <div className="flex items-start justify-between gap-2">
            <div className="flex min-w-0 items-center gap-1.5">
              <button
                type="button"
                aria-label="Drag to reorder"
                title="Drag to reorder"
                onClick={(e) => e.stopPropagation()}
                className="-ml-1 shrink-0 cursor-grab touch-none rounded p-1 text-muted-foreground/50 transition-colors hover:text-foreground active:cursor-grabbing"
                {...attributes}
                {...listeners}
              >
                <GripVertical className="size-4" />
              </button>
              <FileText className="shrink-0 text-muted-foreground" />
              <CardTitle className="truncate">{doc.subject_name}</CardTitle>
            </div>
            <div className="flex shrink-0 items-center gap-1">
              <BookmarkButton
                bookmarked={doc.subject_bookmarked}
                label={doc.subject_name}
                onToggle={(next) => onToggleBookmark(doc.subject_id, next)}
              />
              <StatusBadge status={doc.status} />
              {onDelete && (
                <Button
                  variant="ghost"
                  size="icon"
                  title="Delete subject"
                  aria-label={`Delete ${doc.subject_name}`}
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
          <p className="truncate" title={doc.filename}>
            {doc.filename}
          </p>
          <p>{progress}</p>
          <p className="flex items-center gap-1.5">
            <CalendarDays className="size-3.5" />
            {formatExamDate(doc.exam_date)}
          </p>
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

import { motion } from "framer-motion";
import { CalendarDays, FileText, Trash2 } from "lucide-react";
import { useNavigate } from "react-router-dom";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { BookmarkButton } from "@/features/bookmarks/BookmarkButton";
import { useLibraryStore } from "@/stores/library";
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
  index = 0,
  onDelete,
}: {
  doc: DocumentSummary;
  index?: number;
  onDelete?: (doc: DocumentSummary) => void;
}) {
  const navigate = useNavigate();
  const toggleSubjectBookmark = useLibraryStore((s) => s.toggleSubjectBookmark);
  const progress =
    doc.topics_total === 0
      ? "No topics yet"
      : `${doc.topics_ready} of ${doc.topics_total} topics ready`;

  // Not-yet-confirmed documents go to structure review; confirmed ones to study.
  const destination =
    doc.status === "uploaded"
      ? `/documents/${doc.id}/review`
      : `/documents/${doc.id}/study`;

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, delay: Math.min(index * 0.05, 0.3), ease: "easeOut" }}
      whileHover={{ y: -4 }}
      className="h-full"
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
        className="h-full cursor-pointer transition-shadow hover:shadow-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
      <CardHeader>
        <div className="flex items-start justify-between gap-3">
          <div className="flex min-w-0 items-center gap-2">
            <FileText className="text-muted-foreground" />
            <CardTitle className="truncate">{doc.subject_name}</CardTitle>
          </div>
          <div className="flex shrink-0 items-center gap-1">
            <BookmarkButton
              bookmarked={doc.subject_bookmarked}
              label={doc.subject_name}
              onToggle={(next) => void toggleSubjectBookmark(doc.subject_id, next)}
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
      </CardContent>
      </Card>
    </motion.div>
  );
}

import { CalendarDays, FileText } from "lucide-react";

import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
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

export function DocumentCard({ doc }: { doc: DocumentSummary }) {
  const progress =
    doc.topics_total === 0
      ? "No topics yet"
      : `${doc.topics_ready} of ${doc.topics_total} topics ready`;

  return (
    <Card className="transition-shadow hover:shadow-md">
      <CardHeader>
        <div className="flex items-start justify-between gap-3">
          <div className="flex min-w-0 items-center gap-2">
            <FileText className="text-muted-foreground" />
            <CardTitle className="truncate">{doc.subject_name}</CardTitle>
          </div>
          <StatusBadge status={doc.status} />
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
  );
}

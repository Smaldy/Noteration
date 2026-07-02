import { BookOpen, Trash2, UploadCloud } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { BookmarkButton } from "@/features/bookmarks/BookmarkButton";
import type { Subject } from "@/types/subject";

/** A subject with no documents yet — created standalone, waiting for its first upload. */
export function EmptySubjectCard({
  subject,
  onUpload,
  onDelete,
  onToggleBookmark,
}: {
  subject: Subject;
  onUpload: (subject: Subject) => void;
  onDelete: (subject: Subject) => void;
  onToggleBookmark: (subjectId: number, bookmarked: boolean) => void;
}) {
  const { t } = useTranslation();
  return (
    <Card className="h-full border-dashed">
      <CardHeader>
        <div className="flex items-start justify-between gap-2">
          <div className="flex min-w-0 items-center gap-1.5">
            <BookOpen className="shrink-0 text-muted-foreground" />
            <CardTitle className="truncate">{subject.name}</CardTitle>
          </div>
          <div className="flex shrink-0 items-center gap-1">
            <BookmarkButton
              bookmarked={subject.bookmarked}
              label={subject.name}
              onToggle={(next) => onToggleBookmark(subject.id, next)}
            />
            <Button
              variant="ghost"
              size="icon"
              title={t("library.card.deleteSubject")}
              aria-label={t("library.card.deleteSubjectAria", { name: subject.name })}
              className="size-7 text-muted-foreground hover:text-destructive"
              onClick={() => onDelete(subject)}
            >
              <Trash2 className="size-4" />
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-3 text-sm text-muted-foreground">
        <p>{t("library.emptySubject.noDocuments")}</p>
        <Button variant="outline" size="sm" onClick={() => onUpload(subject)}>
          <UploadCloud className="size-3.5" />
          {t("library.emptySubject.upload")}
        </Button>
      </CardContent>
    </Card>
  );
}

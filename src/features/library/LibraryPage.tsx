import {
  closestCenter,
  DndContext,
  type DragEndEvent,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
} from "@dnd-kit/core";
import {
  arrayMove,
  rectSortingStrategy,
  SortableContext,
  sortableKeyboardCoordinates,
} from "@dnd-kit/sortable";
import {
  Bookmark,
  BookOpen,
  CalendarDays,
  GraduationCap,
  ListChecks,
  Plus,
  Settings,
} from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { SearchBar } from "@/features/search/SearchBar";
import { UploadDialog } from "@/features/upload/UploadDialog";
import { useLibraryStore } from "@/stores/library";

import type { DocumentSummary } from "@/types/library";

import { DocumentCard } from "./DocumentCard";

export function LibraryPage() {
  const {
    documents,
    status,
    error,
    fetchDocuments,
    deleteSubject,
    reorderDocuments,
    toggleSubjectBookmark,
    retryTranscription,
  } = useLibraryStore();
  const [uploadOpen, setUploadOpen] = useState(false);
  const [bookmarkedOnly, setBookmarkedOnly] = useState(false);
  const navigate = useNavigate();
  const { t } = useTranslation();

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );

  useEffect(() => {
    void fetchDocuments();
  }, [fetchDocuments]);

  // While anything is mid-flight (audio transcribing or topics generating), poll
  // so the cards update without a manual refresh. Stops once everything settles.
  const inFlight = documents.some(
    (d) => d.status === "transcribing" || d.status === "processing",
  );
  useEffect(() => {
    if (!inFlight) return;
    const id = window.setInterval(() => void fetchDocuments(), 4000);
    return () => window.clearInterval(id);
  }, [inFlight, fetchDocuments]);

  function handleDragEnd(event: DragEndEvent) {
    const { active, over } = event;
    if (!over || active.id === over.id) return;
    const oldIndex = documents.findIndex((d) => d.id === active.id);
    const newIndex = documents.findIndex((d) => d.id === over.id);
    if (oldIndex < 0 || newIndex < 0) return;
    const next = arrayMove(documents, oldIndex, newIndex);
    void reorderDocuments(next.map((d) => d.id));
  }

  async function handleDelete(doc: DocumentSummary) {
    const ok = window.confirm(
      t("library.deleteConfirm", { name: doc.subject_name }),
    );
    if (!ok) return;
    try {
      await deleteSubject(doc.subject_id);
    } catch {
      window.alert(t("library.deleteFailed"));
    }
  }

  // When the bookmarked-only filter is on, show just the bookmarked subjects.
  const visible = bookmarkedOnly
    ? documents.filter((d) => d.subject_bookmarked)
    : documents;

  const renderCard = (doc: DocumentSummary) => (
    <DocumentCard
      key={doc.id}
      doc={doc}
      onDelete={handleDelete}
      onToggleBookmark={(subjectId, bookmarked) =>
        void toggleSubjectBookmark(subjectId, bookmarked)
      }
      onRetryTranscription={(d) => void retryTranscription(d.id)}
    />
  );

  return (
    <div className="mx-auto max-w-5xl px-6 py-10">
      <header className="mb-8 flex flex-wrap items-center justify-between gap-4 animate-rise">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">{t("library.title")}</h1>
          <p className="mt-0.5 text-sm text-muted-foreground">
            {t("library.subtitle")}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" onClick={() => navigate("/exam")}>
            <GraduationCap />
            {t("nav.examPrep")}
          </Button>
          <Button variant="outline" onClick={() => navigate("/bookmarks")}>
            <Bookmark />
            {t("nav.bookmarks")}
          </Button>
          <Button variant="outline" onClick={() => navigate("/calendar")}>
            <CalendarDays />
            {t("nav.calendar")}
          </Button>
          <Button variant="outline" onClick={() => navigate("/queue")}>
            <ListChecks />
            {t("nav.queue")}
          </Button>
          <Button
            variant="outline"
            size="icon"
            title={t("nav.settings")}
            onClick={() => navigate("/settings")}
          >
            <Settings />
          </Button>
          <Button onClick={() => setUploadOpen(true)}>
            <Plus />
            {t("nav.upload")}
          </Button>
        </div>
      </header>

      <UploadDialog
        open={uploadOpen}
        onOpenChange={setUploadOpen}
        onUploaded={(documentId) => navigate(`/documents/${documentId}/review`)}
      />

      <div className="mb-8 flex flex-col gap-2 animate-rise sm:flex-row sm:items-start">
        <div className="flex-1">
          <SearchBar />
        </div>
        <Button
          variant={bookmarkedOnly ? "default" : "outline"}
          size="icon"
          aria-pressed={bookmarkedOnly}
          aria-label={t("library.filterBookmarkedAria")}
          title={t("library.filterBookmarkedAria")}
          onClick={() => setBookmarkedOnly((v) => !v)}
          className="size-11 shrink-0"
        >
          <Bookmark className={bookmarkedOnly ? "fill-current" : undefined} />
        </Button>
      </div>

      {status === "loading" && (
        <p className="text-sm text-muted-foreground">{t("library.loading")}</p>
      )}

      {status === "error" && (
        <div className="rounded-lg border border-destructive/40 bg-destructive/5 p-4 text-sm text-destructive">
          <p>{error}</p>
          <Button
            variant="outline"
            size="sm"
            className="mt-3"
            onClick={() => void fetchDocuments()}
          >
            {t("common.retry")}
          </Button>
        </div>
      )}

      {status === "loaded" && documents.length === 0 && (
        <div className="flex flex-col items-center justify-center rounded-xl border border-dashed py-20 text-center">
          <BookOpen className="mb-4 size-10 text-muted-foreground" />
          <h2 className="text-lg font-medium">{t("library.empty.title")}</h2>
          <p className="mt-1 max-w-sm text-sm text-muted-foreground">
            {t("library.empty.description")}
          </p>
          <Button className="mt-5" onClick={() => setUploadOpen(true)}>
            <Plus />
            {t("library.empty.cta")}
          </Button>
        </div>
      )}

      {/* Filter is on but nothing is bookmarked yet. */}
      {status === "loaded" &&
        documents.length > 0 &&
        bookmarkedOnly &&
        visible.length === 0 && (
          <div className="flex flex-col items-center justify-center rounded-xl border border-dashed py-20 text-center">
            <Bookmark className="mb-4 size-10 text-muted-foreground" />
            <h2 className="text-lg font-medium">{t("library.noBookmarked")}</h2>
            <p className="mt-1 max-w-sm text-sm text-muted-foreground">
              {t("library.noBookmarkedDesc")}
            </p>
          </div>
        )}

      {/* Drag-reorder only in the full view; the filtered view is a plain grid
          so a partial order can't clobber the saved global order. */}
      {status === "loaded" && visible.length > 0 && bookmarkedOnly && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {visible.map(renderCard)}
        </div>
      )}

      {status === "loaded" && visible.length > 0 && !bookmarkedOnly && (
        <DndContext
          sensors={sensors}
          collisionDetection={closestCenter}
          onDragEnd={handleDragEnd}
        >
          <SortableContext
            items={visible.map((d) => d.id)}
            strategy={rectSortingStrategy}
          >
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {visible.map(renderCard)}
            </div>
          </SortableContext>
        </DndContext>
      )}
    </div>
  );
}

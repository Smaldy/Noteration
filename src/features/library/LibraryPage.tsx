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
  Lock,
  Plus,
  Settings,
} from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { SearchBar } from "@/features/search/SearchBar";
import { UploadDialog } from "@/features/upload/UploadDialog";
import { usePolling } from "@/lib/usePolling";
import { cn } from "@/lib/utils";
import { useArcadeStore } from "@/stores/arcade";
import { useEasterEggStore } from "@/stores/easterEgg";
import { useLibraryStore } from "@/stores/library";
import { useSubjectsStore } from "@/stores/subjects";

import type { DocumentSummary } from "@/types/library";
import type { Subject } from "@/types/subject";

import { CreateSubjectDialog } from "./CreateSubjectDialog";
import { DocumentCard } from "./DocumentCard";
import { EmptySubjectCard } from "./EmptySubjectCard";

export function LibraryPage() {
  const {
    documents,
    status,
    error,
    fetchDocuments,
    deleteDocument,
    reorderDocuments,
    toggleSubjectBookmark,
    retryTranscription,
  } = useLibraryStore();
  const {
    subjects,
    loaded: subjectsLoaded,
    fetchSubjects,
    deleteSubject: deleteEmptySubject,
    toggleBookmark: toggleEmptySubjectBookmark,
  } = useSubjectsStore();
  const [uploadOpen, setUploadOpen] = useState(false);
  const [createSubjectOpen, setCreateSubjectOpen] = useState(false);
  const [uploadTargetSubjectId, setUploadTargetSubjectId] = useState<number | undefined>();
  const [bookmarkedOnly, setBookmarkedOnly] = useState(false);
  const navigate = useNavigate();
  const { t } = useTranslation();
  const registerLibraryTap = useEasterEggStore((s) => s.registerLibraryTap);
  // The running arcade game lights these section buttons when a bomb is planted
  // in that sector, and locks the ones whose sector hasn't unlocked yet.
  const bombSectors = useArcadeStore((s) => s.bombSectors);
  const unlockedSectors = useArcadeStore((s) => s.unlockedSectors);
  const playing = useArcadeStore((s) => s.phase) === "playing";
  const glow = (sector: string) => (bombSectors.includes(sector) ? "arcade-bomb-alert" : "");
  const locked = (sector: string) => playing && !unlockedSectors.includes(sector);

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );

  useEffect(() => {
    void fetchDocuments();
    void fetchSubjects();
  }, [fetchDocuments, fetchSubjects]);

  // While anything is mid-flight (audio transcribing or topics generating), poll
  // so the cards update without a manual refresh. Stops once everything settles.
  const inFlight = documents.some(
    (d) => d.status === "transcribing" || d.status === "processing",
  );
  usePolling(fetchDocuments, 4000, { enabled: inFlight, immediate: false });

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
      t("library.deleteDocConfirm", { name: doc.filename }),
    );
    if (!ok) return;
    try {
      await deleteDocument(doc.id);
      // The subject may have just lost its last document — refresh so it
      // reappears as an empty subject card instead of vanishing.
      await fetchSubjects();
    } catch {
      window.alert(t("library.deleteDocFailed"));
    }
  }

  async function handleDeleteEmptySubject(subject: Subject) {
    const ok = window.confirm(t("library.deleteConfirm", { name: subject.name }));
    if (!ok) return;
    try {
      await deleteEmptySubject(subject.id);
    } catch {
      window.alert(t("library.deleteFailed"));
    }
  }

  function handleUploadForSubject(subject: Subject) {
    setUploadTargetSubjectId(subject.id);
    setUploadOpen(true);
  }

  // When the bookmarked-only filter is on, show just the bookmarked subjects.
  const visible = bookmarkedOnly
    ? documents.filter((d) => d.subject_bookmarked)
    : documents;

  // Subjects created standalone (no PDF/audio yet) don't have a document row
  // to appear as, so they get their own lightweight cards.
  const emptySubjects = subjects.filter(
    (s) => s.document_count === 0 && (!bookmarkedOnly || s.bookmarked),
  );
  const visibleCount = visible.length + emptySubjects.length;

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
          {/* Looks like a plain heading, but tapping it 4× quickly is the secret
              door to the credits (handled by the easter-egg store). */}
          <h1
            className="cursor-default text-3xl font-bold tracking-tight select-none"
            onClick={registerLibraryTap}
          >
            {t("library.title")}
          </h1>
          <p className="mt-0.5 text-sm text-muted-foreground">
            {t("library.subtitle")}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            data-arcade-sector="exam"
            className={cn("relative", glow("exam"), locked("exam") && "opacity-50")}
            onClick={() => navigate("/exam")}
          >
            <GraduationCap />
            {t("nav.examPrep")}
            {locked("exam") && <Lock className="absolute -right-1.5 -top-1.5 size-3.5 text-rose-300" />}
          </Button>
          <Button
            variant="outline"
            data-arcade-sector="bookmarks"
            className={cn("relative", glow("bookmarks"), locked("bookmarks") && "opacity-50")}
            onClick={() => navigate("/bookmarks")}
          >
            <Bookmark />
            {t("nav.bookmarks")}
            {locked("bookmarks") && <Lock className="absolute -right-1.5 -top-1.5 size-3.5 text-rose-300" />}
          </Button>
          <Button
            variant="outline"
            data-arcade-sector="calendar"
            className={cn("relative", glow("calendar"), locked("calendar") && "opacity-50")}
            onClick={() => navigate("/calendar")}
          >
            <CalendarDays />
            {t("nav.calendar")}
            {locked("calendar") && <Lock className="absolute -right-1.5 -top-1.5 size-3.5 text-rose-300" />}
          </Button>
          <Button
            variant="outline"
            data-arcade-sector="queue"
            className={cn("relative", glow("queue"), locked("queue") && "opacity-50")}
            onClick={() => navigate("/queue")}
          >
            <ListChecks />
            {t("nav.queue")}
            {locked("queue") && <Lock className="absolute -right-1.5 -top-1.5 size-3.5 text-rose-300" />}
          </Button>
          <Button
            variant="outline"
            size="icon"
            data-arcade-sector="settings"
            className={cn("relative", glow("settings"), locked("settings") && "opacity-50")}
            title={t("nav.settings")}
            onClick={() => navigate("/settings")}
          >
            <Settings />
            {locked("settings") && <Lock className="absolute -right-1.5 -top-1.5 size-3.5 text-rose-300" />}
          </Button>
          <Button
            onClick={() => {
              setUploadTargetSubjectId(undefined);
              setUploadOpen(true);
            }}
          >
            <Plus />
            {t("nav.upload")}
          </Button>
        </div>
      </header>

      <UploadDialog
        open={uploadOpen}
        onOpenChange={setUploadOpen}
        initialSubjectId={uploadTargetSubjectId}
        onUploaded={(documentId) => navigate(`/documents/${documentId}/review`)}
      />

      <CreateSubjectDialog open={createSubjectOpen} onOpenChange={setCreateSubjectOpen} />

      <div className="mb-8 flex flex-col gap-2 animate-rise sm:flex-row sm:items-start">
        <div className="flex-1">
          <SearchBar onCreateSubject={() => setCreateSubjectOpen(true)} />
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

      {status === "loaded" && subjectsLoaded && documents.length === 0 && subjects.length === 0 && (
        <div className="flex flex-col items-center justify-center rounded-xl border border-dashed py-20 text-center">
          <BookOpen className="mb-4 size-10 text-muted-foreground" />
          <h2 className="text-lg font-medium">{t("library.empty.title")}</h2>
          <p className="mt-1 max-w-sm text-sm text-muted-foreground">
            {t("library.empty.description")}
          </p>
          <Button
            className="mt-5"
            onClick={() => {
              setUploadTargetSubjectId(undefined);
              setUploadOpen(true);
            }}
          >
            <Plus />
            {t("library.empty.cta")}
          </Button>
        </div>
      )}

      {/* Filter is on but nothing is bookmarked yet. */}
      {status === "loaded" &&
        (documents.length > 0 || subjects.length > 0) &&
        bookmarkedOnly &&
        visibleCount === 0 && (
          <div className="flex flex-col items-center justify-center rounded-xl border border-dashed py-20 text-center">
            <Bookmark className="mb-4 size-10 text-muted-foreground" />
            <h2 className="text-lg font-medium">{t("library.noBookmarked")}</h2>
            <p className="mt-1 max-w-sm text-sm text-muted-foreground">
              {t("library.noBookmarkedDesc")}
            </p>
          </div>
        )}

      {/* Subjects with no documents yet get their own plain grid — they have
          no document row to drag-reorder alongside. */}
      {status === "loaded" && emptySubjects.length > 0 && (
        <div className="mb-4 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {emptySubjects.map((subject) => (
            <EmptySubjectCard
              key={`subject-${subject.id}`}
              subject={subject}
              onUpload={handleUploadForSubject}
              onDelete={(s) => void handleDeleteEmptySubject(s)}
              onToggleBookmark={(id, bookmarked) =>
                void toggleEmptySubjectBookmark(id, bookmarked)
              }
            />
          ))}
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

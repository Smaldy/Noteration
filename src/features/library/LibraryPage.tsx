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

import { EmptyState, PageHeader, PageShell } from "@/components/PageShell";
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
  const [subjectFilterId, setSubjectFilterId] = useState<number | null>(null);
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

  // Both filters narrow the card grid: bookmarked-only and the subject picker
  // (which also scopes the search dropdown above).
  const filterActive = bookmarkedOnly || subjectFilterId != null;
  const visible = documents.filter(
    (d) =>
      (!bookmarkedOnly || d.subject_bookmarked) &&
      (subjectFilterId == null || d.subject_id === subjectFilterId),
  );

  // Subjects created standalone (no PDF/audio yet) don't have a document row
  // to appear as, so they get their own lightweight cards.
  const emptySubjects = subjects.filter(
    (s) =>
      s.document_count === 0 &&
      (!bookmarkedOnly || s.bookmarked) &&
      (subjectFilterId == null || s.id === subjectFilterId),
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

  // Top-level destinations, rendered identically; settings collapses to icon-only.
  const navItems = [
    { sector: "exam", icon: GraduationCap, label: t("nav.examPrep"), to: "/exam" },
    { sector: "calendar", icon: CalendarDays, label: t("nav.calendar"), to: "/calendar" },
    { sector: "queue", icon: ListChecks, label: t("nav.queue"), to: "/queue" },
  ] as const;

  return (
    <PageShell width="wide">
      <PageHeader
        className="items-center"
        title={
          /* Looks like a plain heading, but tapping it 4× quickly is the secret
             door to the credits (handled by the easter-egg store). */
          <span className="cursor-default select-none" onClick={registerLibraryTap}>
            {t("library.title")}
          </span>
        }
        actions={
          <>
            {navItems.map(({ sector, icon: Icon, label, to }) => (
              <Button
                key={sector}
                variant="outline"
                data-arcade-sector={sector}
                className={cn("relative", glow(sector), locked(sector) && "opacity-50")}
                onClick={() => navigate(to)}
              >
                <Icon />
                {label}
                {locked(sector) && (
                  <Lock className="absolute -right-1.5 -top-1.5 size-3.5 text-destructive/70" />
                )}
              </Button>
            ))}
            <Button
              variant="outline"
              size="icon"
              data-arcade-sector="settings"
              className={cn("relative", glow("settings"), locked("settings") && "opacity-50")}
              title={t("nav.settings")}
              aria-label={t("nav.settings")}
              onClick={() => navigate("/settings")}
            >
              <Settings />
              {locked("settings") && (
                <Lock className="absolute -right-1.5 -top-1.5 size-3.5 text-destructive/70" />
              )}
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
          </>
        }
      />

      <UploadDialog
        open={uploadOpen}
        onOpenChange={setUploadOpen}
        initialSubjectId={uploadTargetSubjectId}
        onUploaded={(documentId) => navigate(`/documents/${documentId}/review`)}
      />

      <CreateSubjectDialog open={createSubjectOpen} onOpenChange={setCreateSubjectOpen} />

      <div className="mb-6 flex flex-col gap-2 sm:flex-row sm:items-start">
        <div className="flex-1">
          <SearchBar
            onCreateSubject={() => setCreateSubjectOpen(true)}
            subjectId={subjectFilterId}
            onSubjectChange={setSubjectFilterId}
          />
        </div>
        <Button
          variant={bookmarkedOnly ? "default" : "outline"}
          size="icon"
          aria-pressed={bookmarkedOnly}
          aria-label={t("library.filterBookmarkedAria")}
          title={t("library.filterBookmarkedAria")}
          onClick={() => setBookmarkedOnly((v) => !v)}
          className="size-11 shrink-0 rounded-xl"
        >
          <Bookmark className={bookmarkedOnly ? "fill-current" : undefined} />
        </Button>
      </div>

      {status === "loading" && (
        <p className="text-sm text-muted-foreground">{t("library.loading")}</p>
      )}

      {status === "error" && (
        <div className="rounded-xl border border-destructive/40 bg-destructive/5 p-4 text-sm text-destructive">
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
        <EmptyState
          icon={BookOpen}
          title={t("library.empty.title")}
          description={t("library.empty.description")}
          action={
            <Button
              onClick={() => {
                setUploadTargetSubjectId(undefined);
                setUploadOpen(true);
              }}
            >
              <Plus />
              {t("library.empty.cta")}
            </Button>
          }
        />
      )}

      {/* Filter is on but nothing is bookmarked yet. */}
      {status === "loaded" &&
        (documents.length > 0 || subjects.length > 0) &&
        bookmarkedOnly &&
        visibleCount === 0 && (
          <EmptyState
            icon={Bookmark}
            title={t("library.noBookmarked")}
            description={t("library.noBookmarkedDesc")}
          />
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
      {status === "loaded" && visible.length > 0 && filterActive && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {visible.map(renderCard)}
        </div>
      )}

      {status === "loaded" && visible.length > 0 && !filterActive && (
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
    </PageShell>
  );
}

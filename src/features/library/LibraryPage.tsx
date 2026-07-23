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
import { Bookmark, BookOpen, ChevronDown, FolderPlus, Plus } from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import {
  EmptyState,
  PageHeader,
  PageShell,
  SectionLabel,
} from "@/components/PageShell";
import { Button } from "@/components/ui/button";
import { SearchBar } from "@/features/search/SearchBar";
import { UploadDialog } from "@/features/upload/UploadDialog";
import { usePolling } from "@/lib/usePolling";
import { cn } from "@/lib/utils";
import { useEasterEggStore } from "@/stores/easterEgg";
import { useFoldersStore } from "@/stores/folders";
import { useLibraryStore } from "@/stores/library";
import { useSubjectsStore } from "@/stores/subjects";

import type { Folder } from "@/types/folder";
import type { DocumentSummary } from "@/types/library";
import type { Subject } from "@/types/subject";

import { AddToFolderDialog } from "./AddToFolderDialog";
import { CreateSubjectDialog } from "./CreateSubjectDialog";
import { DocumentCard } from "./DocumentCard";
import { EmptySubjectCard } from "./EmptySubjectCard";
import { FolderCard } from "./FolderCard";
import { FolderDialog } from "./FolderDialog";

export function LibraryPage() {
  const {
    documents,
    status,
    error,
    fetchDocuments,
    deleteDocument,
    reorderDocuments,
    retryTranscription,
  } = useLibraryStore();
  const {
    subjects,
    loaded: subjectsLoaded,
    fetchSubjects,
    deleteSubject: deleteEmptySubject,
  } = useSubjectsStore();
  const [uploadOpen, setUploadOpen] = useState(false);
  const [createSubjectOpen, setCreateSubjectOpen] = useState(false);
  const [uploadTargetSubjectId, setUploadTargetSubjectId] = useState<number | undefined>();
  const [bookmarkedOnly, setBookmarkedOnly] = useState(false);
  const [subjectFilterId, setSubjectFilterId] = useState<number | null>(null);
  const [folderDialogOpen, setFolderDialogOpen] = useState(false);
  const [editingFolder, setEditingFolder] = useState<Folder | null>(null);
  const [addOpen, setAddOpen] = useState(false);
  const [addTarget, setAddTarget] = useState<Folder | null>(null);
  const navigate = useNavigate();
  const { t } = useTranslation();
  const registerLibraryTap = useEasterEggStore((s) => s.registerLibraryTap);
  const {
    folders,
    status: foldersStatus,
    fetchFolders,
    reorderFolders,
    setFolderBookmark,
  } = useFoldersStore();
  // Collapsed once folders exist: with them doing the organizing, the flat grid
  // is a fallback, and leaving it open reproduces the clutter folders fix.
  // `null` means "not decided yet" — folders start out an empty array while the
  // fetch is in flight, and keying off that would flash the grid open and leave
  // it open for everyone who has folders.
  const [notesOpen, setNotesOpen] = useState<boolean | null>(null);

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );

  useEffect(() => {
    void fetchDocuments();
    void fetchSubjects();
    void fetchFolders();
  }, [fetchDocuments, fetchSubjects, fetchFolders]);

  // Decide the flat grid's initial state once, when the real folder list lands:
  // expanded only if there is no folder to look at instead. After that the user
  // owns the toggle.
  useEffect(() => {
    if (foldersStatus === "loaded") {
      setNotesOpen((current) => current ?? folders.length === 0);
    }
  }, [foldersStatus, folders.length]);

  // While anything is mid-flight (audio transcribing or topics generating), poll
  // so the cards update without a manual refresh. Stops once everything settles.
  const inFlight = documents.some(
    (d) => d.status === "transcribing" || d.status === "processing",
  );
  usePolling(fetchDocuments, 4000, { enabled: inFlight, immediate: false });

  // Only roots are laid out in the grid; children live inside their parent.
  const rootFolders = folders.filter((f) => f.parent_id == null);
  const documentsById = new Map(documents.map((d) => [d.id, d]));

  // Folder filters. The subject picker narrows to folders either tagged to that
  // subject or holding one of its notes, so a manually filled folder still shows
  // up under the subject of what is inside it. The bookmark toggle stars
  // folders, which is the only thing it filters.
  const visibleFolders = rootFolders.filter((folder) => {
    if (bookmarkedOnly && !folder.bookmarked) return false;
    if (subjectFilterId == null) return true;
    if (folder.subject_id === subjectFilterId) return true;
    return folder.preview_ids.some(
      (docId) => documentsById.get(docId)?.subject_id === subjectFilterId,
    );
  });

  function handleFolderDragEnd(event: DragEndEvent) {
    const { active, over } = event;
    if (!over || active.id === over.id) return;
    const oldIndex = rootFolders.findIndex((f) => f.id === active.id);
    const newIndex = rootFolders.findIndex((f) => f.id === over.id);
    if (oldIndex < 0 || newIndex < 0) return;
    const next = arrayMove(rootFolders, oldIndex, newIndex);
    void reorderFolders(next.map((f) => f.id));
  }

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

  // Only the subject picker narrows the flat note grid; the bookmark toggle is
  // folder-scoped. `filterActive` gates drag-reorder, which must be off for any
  // partial view so a partial order can't overwrite the saved one.
  const filterActive = bookmarkedOnly || subjectFilterId != null;
  // The bookmark toggle is a *folder* filter now, so it deliberately does not
  // narrow this list: starring subjects turned out to be near useless, and a
  // toggle that quietly filtered two different things at once read as broken.
  const visible = documents.filter(
    (d) => subjectFilterId == null || d.subject_id === subjectFilterId,
  );

  // Subjects created standalone (no PDF/audio yet) don't have a document row
  // to appear as, so they get their own lightweight cards.
  const emptySubjects = subjects.filter(
    (s) =>
      s.document_count === 0 &&
      (subjectFilterId == null || s.id === subjectFilterId),
  );

  const renderFolder = (folder: Folder) => (
    <FolderCard
      key={folder.id}
      folder={folder}
      preview={folder.preview_ids
        .map((docId) => documentsById.get(docId))
        .filter((d): d is DocumentSummary => d != null)}
      onAdd={(f) => {
        setAddTarget(f);
        setAddOpen(true);
      }}
      onEdit={(f) => {
        setEditingFolder(f);
        setFolderDialogOpen(true);
      }}
      onToggleBookmark={(f, next) => void setFolderBookmark(f.id, next)}
    />
  );

  const renderCard = (doc: DocumentSummary) => (
    <DocumentCard
      key={doc.id}
      doc={doc}
      onDelete={handleDelete}
      onRetryTranscription={(d) => void retryTranscription(d.id)}
    />
  );

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
        subtitle={t("library.subtitle")}
        actions={
          <Button
            size="lg"
            className="rounded-xl"
            onClick={() => {
              setUploadTargetSubjectId(undefined);
              setUploadOpen(true);
            }}
          >
            <Plus />
            {t("nav.upload")}
          </Button>
        }
      />

      <UploadDialog
        open={uploadOpen}
        onOpenChange={setUploadOpen}
        initialSubjectId={uploadTargetSubjectId}
        onUploaded={(documentId) => navigate(`/documents/${documentId}/review`)}
      />

      <CreateSubjectDialog open={createSubjectOpen} onOpenChange={setCreateSubjectOpen} />

      {/* Search, filters and New folder share one toolbar row. The search box
          gives up the width rather than New folder floating off on its own
          line, and every control here is h-11 so they line up. */}
      <div className="mb-6 flex flex-col gap-2 sm:flex-row sm:items-start">
        <div className="min-w-0 flex-1">
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
          aria-label={t("folders.filterBookmarkedAria")}
          title={t("folders.filterBookmarkedAria")}
          onClick={() => setBookmarkedOnly((v) => !v)}
          className="size-11 shrink-0 rounded-xl"
        >
          <Bookmark className={bookmarkedOnly ? "fill-current" : undefined} />
        </Button>
        <Button
          variant="outline"
          onClick={() => {
            setEditingFolder(null);
            setFolderDialogOpen(true);
          }}
          className="h-11 shrink-0 rounded-xl px-4"
        >
          <FolderPlus />
          {t("folders.newFolder")}
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

      {/* Bookmark filter is on but no folder is starred yet. */}
      {status === "loaded" && bookmarkedOnly && visibleFolders.length === 0 && (
        <EmptyState
          icon={Bookmark}
          title={t("folders.noBookmarked")}
          description={t("folders.noBookmarkedDesc")}
        />
      )}

      {/* Folders lead the page: they are the answer to a Library that has
          outgrown one flat grid. The document grid below stays reachable but
          collapses once folders exist, so it stops being the wall of near
          identical cards it becomes at 80 notes. */}
      {status === "loaded" && (
        <section className="mb-8">
          <SectionLabel className="mb-3">{t("folders.sectionTitle")}</SectionLabel>

          {/* A subject filter narrows the folders to that subject rather than
              hiding the whole section: a folder tagged to the filtered subject
              is the most relevant thing on the page, not the least. */}
          {visibleFolders.length === 0 && bookmarkedOnly ? null : visibleFolders.length ===
              0 && filterActive ? (
            <p className="rounded-2xl border border-dashed px-4 py-6 text-center text-sm text-muted-foreground">
              {t("folders.noneForFilter")}
            </p>
          ) : folders.length === 0 ? (
            <button
              type="button"
              onClick={() => {
                setEditingFolder(null);
                setFolderDialogOpen(true);
              }}
              className="flex w-full flex-col items-center gap-1.5 rounded-3xl border-2 border-dashed border-foreground/10 py-10 text-muted-foreground transition-colors hover:border-primary/40 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <FolderPlus className="size-6 opacity-60" />
              <span className="text-sm font-medium">{t("folders.firstFolderCta")}</span>
              <span className="text-xs">{t("folders.firstFolderHint")}</span>
            </button>
          ) : filterActive ? (
            /* Plain grid while filtered, for the same reason the document grid
               drops drag-reorder: a partial order must not overwrite the saved
               global one. */
            <div className="grid grid-cols-1 items-start gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {visibleFolders.map(renderFolder)}
            </div>
          ) : (
            <DndContext
              sensors={sensors}
              collisionDetection={closestCenter}
              onDragEnd={handleFolderDragEnd}
            >
              <SortableContext
                items={visibleFolders.map((f) => f.id)}
                strategy={rectSortingStrategy}
              >
                <div className="grid grid-cols-1 items-start gap-4 sm:grid-cols-2 lg:grid-cols-3">
                  {visibleFolders.map(renderFolder)}
                </div>
              </SortableContext>
            </DndContext>
          )}
        </section>
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
            />
          ))}
        </div>
      )}

      {status === "loaded" && visible.length > 0 && (
        <section>
          <button
            type="button"
            onClick={() => setNotesOpen((v) => !v)}
            aria-expanded={notesOpen ?? false}
            className="mb-3 flex items-center gap-1.5 rounded-lg text-sm font-semibold uppercase tracking-wider text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <ChevronDown
              className={cn("size-4 transition-transform", !notesOpen && "-rotate-90")}
            />
            {t("folders.allNotes", { count: visible.length })}
          </button>

          {notesOpen &&
            /* Drag-reorder only in the unfiltered view; a filtered view is a
               plain grid so a partial order can't clobber the saved one. */
            (filterActive ? (
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
                {visible.map(renderCard)}
              </div>
            ) : (
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
            ))}
        </section>
      )}

      <FolderDialog
        open={folderDialogOpen}
        onOpenChange={setFolderDialogOpen}
        folder={editingFolder}
      />
      <AddToFolderDialog
        open={addOpen}
        onOpenChange={setAddOpen}
        folder={addTarget}
        onUploadRequested={(folder) => {
          setUploadTargetSubjectId(folder.subject_id ?? undefined);
          setUploadOpen(true);
        }}
      />
    </PageShell>
  );
}

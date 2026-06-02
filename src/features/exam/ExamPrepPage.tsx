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
import { ArrowLeft, GraduationCap, Plus } from "lucide-react";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { DocumentCard } from "@/features/library/DocumentCard";
import { UploadDialog } from "@/features/upload/UploadDialog";
import { useExamStore } from "@/stores/library";

import type { DocumentSummary } from "@/types/library";

// The Exam Prep section: documents here are assessment-only (MCQs + flashcards,
// no notes). It reuses the Library's DocumentCard/UploadDialog, driven by the
// separate exam store so its state never mixes with the Library.
export function ExamPrepPage() {
  const {
    documents,
    status,
    error,
    fetchDocuments,
    deleteSubject,
    reorderDocuments,
    toggleSubjectBookmark,
  } = useExamStore();
  const [uploadOpen, setUploadOpen] = useState(false);
  const navigate = useNavigate();

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );

  useEffect(() => {
    void fetchDocuments();
  }, [fetchDocuments]);

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
      `Delete the subject "${doc.subject_name}" and all of its documents, ` +
        `topics, and flashcards? This can't be undone.`,
    );
    if (!ok) return;
    try {
      await deleteSubject(doc.subject_id);
    } catch {
      window.alert("Couldn't delete that subject. Please try again.");
    }
  }

  return (
    <div className="mx-auto max-w-5xl px-6 py-10">
      <header className="mb-8 flex flex-wrap items-center justify-between gap-4 animate-rise">
        <div>
          <button
            type="button"
            onClick={() => navigate("/")}
            className="mb-1 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
          >
            <ArrowLeft className="size-4" />
            Library
          </button>
          <h1 className="flex items-center gap-2 text-3xl font-bold tracking-tight">
            <GraduationCap className="size-7 text-primary" />
            Exam Prep
          </h1>
          <p className="mt-0.5 text-sm text-muted-foreground">
            Drilled practice — every PDF here becomes MCQs (with explanations) and
            flashcards. No notes.
          </p>
        </div>
        <Button onClick={() => setUploadOpen(true)}>
          <Plus />
          Add exam PDF
        </Button>
      </header>

      <UploadDialog
        open={uploadOpen}
        onOpenChange={setUploadOpen}
        store={useExamStore}
        exam
        onUploaded={(documentId) =>
          navigate(`/documents/${documentId}/review?from=exam`)
        }
      />

      {status === "loading" && (
        <p className="text-sm text-muted-foreground">Loading your exam prep…</p>
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
            Retry
          </Button>
        </div>
      )}

      {status === "loaded" && documents.length === 0 && (
        <div className="flex flex-col items-center justify-center rounded-xl border border-dashed py-20 text-center">
          <GraduationCap className="mb-4 size-10 text-muted-foreground" />
          <h2 className="text-lg font-medium">No exam decks yet</h2>
          <p className="mt-1 max-w-sm text-sm text-muted-foreground">
            Add a PDF to generate exam-style MCQs and flashcards, scheduled with
            spaced repetition.
          </p>
          <Button className="mt-5" onClick={() => setUploadOpen(true)}>
            <Plus />
            Add exam PDF
          </Button>
        </div>
      )}

      {status === "loaded" && documents.length > 0 && (
        <DndContext
          sensors={sensors}
          collisionDetection={closestCenter}
          onDragEnd={handleDragEnd}
        >
          <SortableContext
            items={documents.map((d) => d.id)}
            strategy={rectSortingStrategy}
          >
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {documents.map((doc) => (
                <DocumentCard
                  key={doc.id}
                  doc={doc}
                  onDelete={handleDelete}
                  onToggleBookmark={(subjectId, bookmarked) =>
                    void toggleSubjectBookmark(subjectId, bookmarked)
                  }
                />
              ))}
            </div>
          </SortableContext>
        </DndContext>
      )}
    </div>
  );
}

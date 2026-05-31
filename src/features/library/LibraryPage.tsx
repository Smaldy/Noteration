import { BookOpen, CalendarDays, ListChecks, Plus, Settings } from "lucide-react";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { SearchBar } from "@/features/search/SearchBar";
import { UploadDialog } from "@/features/upload/UploadDialog";
import { useLibraryStore } from "@/stores/library";

import type { DocumentSummary } from "@/types/library";

import { DocumentCard } from "./DocumentCard";

export function LibraryPage() {
  const { documents, status, error, fetchDocuments, deleteSubject } =
    useLibraryStore();
  const [uploadOpen, setUploadOpen] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    void fetchDocuments();
  }, [fetchDocuments]);

  async function handleDelete(doc: DocumentSummary) {
    const ok = window.confirm(
      `Delete the subject "${doc.subject_name}" and all of its documents, ` +
        `topics, notes, and schedule? This can't be undone.`,
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
          <h1 className="text-3xl font-bold tracking-tight">Library</h1>
          <p className="mt-0.5 text-sm text-muted-foreground">
            Your uploaded documents and their study progress.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" onClick={() => navigate("/calendar")}>
            <CalendarDays />
            Calendar
          </Button>
          <Button variant="outline" onClick={() => navigate("/queue")}>
            <ListChecks />
            Queue
          </Button>
          <Button
            variant="outline"
            size="icon"
            title="Settings"
            onClick={() => navigate("/settings")}
          >
            <Settings />
          </Button>
          <Button onClick={() => setUploadOpen(true)}>
            <Plus />
            Upload PDF
          </Button>
        </div>
      </header>

      <UploadDialog
        open={uploadOpen}
        onOpenChange={setUploadOpen}
        onUploaded={(documentId) => navigate(`/documents/${documentId}/review`)}
      />

      <div className="mb-8 animate-rise">
        <SearchBar />
      </div>

      {status === "loading" && (
        <p className="text-sm text-muted-foreground">Loading your library…</p>
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
          <BookOpen className="mb-4 size-10 text-muted-foreground" />
          <h2 className="text-lg font-medium">No documents yet</h2>
          <p className="mt-1 max-w-sm text-sm text-muted-foreground">
            Upload an engineering PDF to generate notes, MCQs, flashcards, and a
            study schedule.
          </p>
          <Button className="mt-5" onClick={() => setUploadOpen(true)}>
            <Plus />
            Upload PDF
          </Button>
        </div>
      )}

      {status === "loaded" && documents.length > 0 && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {documents.map((doc, i) => (
            <DocumentCard key={doc.id} doc={doc} index={i} onDelete={handleDelete} />
          ))}
        </div>
      )}
    </div>
  );
}

import { BookOpen, Plus } from "lucide-react";
import { useEffect } from "react";

import { Button } from "@/components/ui/button";
import { useLibraryStore } from "@/stores/library";

import { DocumentCard } from "./DocumentCard";

export function LibraryPage() {
  const { documents, status, error, fetchDocuments } = useLibraryStore();

  useEffect(() => {
    void fetchDocuments();
  }, [fetchDocuments]);

  return (
    <div className="mx-auto max-w-5xl px-6 py-10">
      <header className="mb-8 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Library</h1>
          <p className="text-sm text-muted-foreground">
            Your uploaded documents and their study progress.
          </p>
        </div>
        {/* Upload flow arrives in a later Phase-9 sub-wave. */}
        <Button disabled title="Upload coming soon">
          <Plus />
          Upload PDF
        </Button>
      </header>

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
        </div>
      )}

      {status === "loaded" && documents.length > 0 && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {documents.map((doc) => (
            <DocumentCard key={doc.id} doc={doc} />
          ))}
        </div>
      )}
    </div>
  );
}

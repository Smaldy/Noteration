import { useState, type ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useStudyStore } from "@/stores/study";
import type { Note } from "@/types/study";

interface NotesTabProps {
  topicId: number;
  notes: Note[];
}

export function NotesTab({ topicId, notes }: NotesTabProps) {
  const transcribeFormulas = useStudyStore((s) => s.transcribeFormulas);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (notes.length === 0) {
    return <EmptyTab>No notes yet for this topic.</EmptyTab>;
  }

  const pendingCount = notes.reduce(
    (n, note) => n + note.formulas.filter((f) => f.state === "pending").length,
    0,
  );

  const reconstruct = async () => {
    setBusy(true);
    setError(null);
    try {
      await transcribeFormulas(topicId);
    } catch {
      setError("Couldn't reconstruct formulas — a vision provider may be busy.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-8">
      {notes.map((note) => (
        <article key={note.id}>
          <div className="prose prose-sm max-w-none dark:prose-invert">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {note.content_md || "_This note is empty._"}
            </ReactMarkdown>
          </div>

          {note.formulas.length > 0 && (
            <div className="mt-4 space-y-2">
              <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                Formulas
              </h4>
              {note.formulas.map((formula) => (
                <div
                  key={formula.id}
                  className="flex items-center justify-between gap-3 rounded-md border bg-muted/40 px-3 py-2"
                >
                  <code className="truncate text-sm">
                    {formula.latex || (
                      <span className="text-muted-foreground">
                        equation detected — not yet reconstructed
                      </span>
                    )}
                  </code>
                  <Badge
                    variant={formula.state === "verified" ? "default" : "outline"}
                  >
                    {formula.state}
                  </Badge>
                </div>
              ))}
            </div>
          )}
        </article>
      ))}

      {pendingCount > 0 && (
        <div className="flex items-center gap-3">
          <Button size="sm" onClick={reconstruct} disabled={busy}>
            {busy
              ? "Reconstructing…"
              : `Reconstruct ${pendingCount} formula${pendingCount > 1 ? "s" : ""}`}
          </Button>
          {error && <span className="text-sm text-destructive">{error}</span>}
        </div>
      )}
    </div>
  );
}

function EmptyTab({ children }: { children: ReactNode }) {
  return (
    <p className="py-12 text-center text-sm text-muted-foreground">{children}</p>
  );
}

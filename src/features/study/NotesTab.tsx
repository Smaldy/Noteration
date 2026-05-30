import type { ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { Badge } from "@/components/ui/badge";
import type { Note } from "@/types/study";

interface NotesTabProps {
  notes: Note[];
}

export function NotesTab({ notes }: NotesTabProps) {
  if (notes.length === 0) {
    return <EmptyTab>No notes yet for this topic.</EmptyTab>;
  }

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
                  <code className="truncate text-sm">{formula.latex}</code>
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
    </div>
  );
}

function EmptyTab({ children }: { children: ReactNode }) {
  return (
    <p className="py-12 text-center text-sm text-muted-foreground">{children}</p>
  );
}

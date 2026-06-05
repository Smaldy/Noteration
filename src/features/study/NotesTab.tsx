import { Lock, LockOpen, Pencil, Plus, Trash2 } from "lucide-react";
import { Suspense, lazy, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { MarkdownView } from "@/components/MarkdownView";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { providerInfo } from "@/lib/providers";
import { useStudyStore } from "@/stores/study";
import type { Note } from "@/types/study";

// TipTap is heavy and only needed when the user actually edits a note, so it's
// split out and loaded on demand (keeps it out of the study-page chunk).
const NoteEditor = lazy(() =>
  import("@/components/editor/NoteEditor").then((m) => ({ default: m.NoteEditor })),
);

interface NotesTabProps {
  topicId: number;
  notes: Note[];
  /** Provider that generated this topic's AI content, for the in-view stamp. */
  generatedBy?: string | null;
}

export function NotesTab({ topicId, notes, generatedBy }: NotesTabProps) {
  const { t } = useTranslation();
  const transcribeFormulas = useStudyStore((s) => s.transcribeFormulas);
  const addNote = useStudyStore((s) => s.addNote);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);

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
      setError(t("study.notes.reconstructError"));
    } finally {
      setBusy(false);
    }
  };

  const addManual = async () => {
    setAdding(true);
    try {
      await addNote(topicId, "");
    } finally {
      setAdding(false);
    }
  };

  return (
    <div className="space-y-6">
      {notes.length === 0 ? (
        <EmptyTab>{t("study.notes.empty")}</EmptyTab>
      ) : (
        notes.map((note) => (
          <NoteBlock key={note.id} note={note} generatedBy={generatedBy} />
        ))
      )}

      <div className="flex flex-wrap items-center gap-3">
        <Button variant="outline" size="sm" onClick={addManual} disabled={adding}>
          <Plus className="mr-1.5 size-4" />
          {adding ? t("study.notes.adding") : t("study.notes.add")}
        </Button>

        {pendingCount > 0 && (
          <Button size="sm" onClick={reconstruct} disabled={busy}>
            {busy
              ? t("study.notes.reconstructing")
              : t("study.notes.reconstruct", { count: pendingCount })}
          </Button>
        )}
        {error && <span className="text-sm text-destructive">{error}</span>}
      </div>
    </div>
  );
}

function NoteBlock({
  note,
  generatedBy,
}: {
  note: Note;
  generatedBy?: string | null;
}) {
  const { t } = useTranslation();
  const saveNote = useStudyStore((s) => s.saveNote);
  const removeNote = useStudyStore((s) => s.removeNote);
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);

  const save = async (markdown: string) => {
    setSaving(true);
    try {
      await saveNote(note.id, markdown);
      setEditing(false);
    } finally {
      setSaving(false);
    }
  };

  const remove = async () => {
    if (!window.confirm(t("study.notes.deleteBlockConfirm"))) return;
    await removeNote(note.id);
  };

  const toggleLock = () => saveNote(note.id, note.content_md, !note.locked);

  if (editing) {
    return (
      <Suspense
        fallback={
          <div className="flex min-h-48 items-center justify-center rounded-lg border bg-card">
            <span className="size-5 animate-spin rounded-full border-2 border-muted border-t-primary" />
          </div>
        }
      >
        <NoteEditor
          initialMarkdown={note.content_md}
          onSave={save}
          onCancel={() => setEditing(false)}
          saving={saving}
        />
      </Suspense>
    );
  }

  return (
    <article className="group relative rounded-lg border border-transparent px-1 py-1 transition hover:border-border hover:bg-card/50">
      <div className="absolute right-1 top-1 flex items-center gap-0.5 opacity-0 transition group-hover:opacity-100 focus-within:opacity-100">
        {note.is_manual ? (
          <Badge variant="outline">{t("study.notes.manual")}</Badge>
        ) : (
          generatedBy && (
            <Badge
              variant="outline"
              className={cn("gap-1", providerInfo(generatedBy).text)}
              title={t("study.notes.generatedBy", {
                provider: providerInfo(generatedBy).label,
              })}
            >
              <span className={cn("size-1.5 rounded-full", providerInfo(generatedBy).dot)} />
              {providerInfo(generatedBy).short}
            </Badge>
          )
        )}
        <IconBtn
          label={note.locked ? t("study.notes.unlock") : t("study.notes.lock")}
          onClick={toggleLock}
        >
          {note.locked ? (
            <Lock className="size-4 text-primary" />
          ) : (
            <LockOpen className="size-4" />
          )}
        </IconBtn>
        <IconBtn
          label={t("study.notes.edit")}
          onClick={() => setEditing(true)}
          disabled={note.locked}
        >
          <Pencil className="size-4" />
        </IconBtn>
        <IconBtn label={t("study.notes.delete")} onClick={remove}>
          <Trash2 className="size-4 text-destructive" />
        </IconBtn>
      </div>

      <MarkdownView>{note.content_md || t("study.notes.emptyNote")}</MarkdownView>

      {note.formulas.length > 0 && (
        <div className="mt-4 space-y-2">
          <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            {t("study.notes.formulas")}
          </h4>
          {note.formulas.map((formula) => (
            <div
              key={formula.id}
              className="flex items-center justify-between gap-3 rounded-md border bg-muted/40 px-3 py-2"
            >
              <code className="truncate text-sm">
                {formula.latex || (
                  <span className="text-muted-foreground">
                    {t("study.notes.equationDetected")}
                  </span>
                )}
              </code>
              <Badge variant={formula.state === "verified" ? "default" : "outline"}>
                {t(`study.notes.state.${formula.state}`, {
                  defaultValue: formula.state,
                })}
              </Badge>
            </div>
          ))}
        </div>
      )}
    </article>
  );
}

function IconBtn({
  children,
  label,
  onClick,
  disabled = false,
}: {
  children: ReactNode;
  label: string;
  onClick: () => void;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      title={label}
      aria-label={label}
      onClick={onClick}
      disabled={disabled}
      className="inline-flex size-7 items-center justify-center rounded-md bg-background/80 text-foreground/70 shadow-sm backdrop-blur transition hover:bg-background hover:text-foreground disabled:pointer-events-none disabled:opacity-40"
    >
      {children}
    </button>
  );
}

function EmptyTab({ children }: { children: ReactNode }) {
  return (
    <p className="py-12 text-center text-sm text-muted-foreground">{children}</p>
  );
}

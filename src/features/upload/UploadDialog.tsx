import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ApiError } from "@/lib/api";
import { type LibraryStore, useLibraryStore } from "@/stores/library";
import { useSubjectsStore } from "@/stores/subjects";

const NEW_SUBJECT = "__new__";

// A zustand hook compatible with the documents store (study or exam section).
type DocumentsStoreHook = <T>(selector: (state: LibraryStore) => T) => T;

interface UploadDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Called with the new document id after a successful upload (for routing). */
  onUploaded?: (documentId: number) => void;
  /** Which section's store to upload through (defaults to the Library/study store). */
  store?: DocumentsStoreHook;
  /** Whether this is the Exam Prep section (tweaks the dialog copy). */
  exam?: boolean;
}

export function UploadDialog({
  open,
  onOpenChange,
  onUploaded,
  store = useLibraryStore,
  exam = false,
}: UploadDialogProps) {
  const { subjects, fetchSubjects } = useSubjectsStore();
  const createSubject = useSubjectsStore((s) => s.createSubject);
  const uploadDocument = store((s) => s.uploadDocument);

  const [subjectChoice, setSubjectChoice] = useState<string>(NEW_SUBJECT);
  const [newSubjectName, setNewSubjectName] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Load subjects whenever the dialog opens; reset transient state on close.
  useEffect(() => {
    if (open) {
      void fetchSubjects();
    } else {
      setNewSubjectName("");
      setFile(null);
      setError(null);
      setBusy(false);
    }
  }, [open, fetchSubjects]);

  const creatingNew = subjectChoice === NEW_SUBJECT;
  const canSubmit =
    file !== null &&
    !busy &&
    (creatingNew ? newSubjectName.trim().length > 0 : true);

  async function handleSubmit() {
    if (file === null) return;
    setBusy(true);
    setError(null);
    try {
      const subjectId = creatingNew
        ? (await createSubject({ name: newSubjectName.trim() })).id
        : Number(subjectChoice);
      const result = await uploadDocument(subjectId, file);
      onOpenChange(false);
      onUploaded?.(result.document.id);
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Upload failed. Please try again.",
      );
      setBusy(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{exam ? "Add an exam PDF" : "Upload a PDF"}</DialogTitle>
          <DialogDescription>
            {exam
              ? "We'll read the PDF and propose a structure to review. Exam-prep " +
                "documents generate only MCQs (with explanations) and flashcards — " +
                "no notes."
              : "We'll read the PDF and propose a chapter/topic structure for you " +
                "to review before anything is generated."}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-2">
          <div className="space-y-2">
            <Label htmlFor="subject">Subject</Label>
            <select
              id="subject"
              className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
              value={subjectChoice}
              onChange={(e) => setSubjectChoice(e.target.value)}
              disabled={busy}
            >
              <option value={NEW_SUBJECT}>+ New subject…</option>
              {subjects.map((s) => (
                <option key={s.id} value={String(s.id)}>
                  {s.name}
                </option>
              ))}
            </select>
          </div>

          {creatingNew && (
            <div className="space-y-2">
              <Label htmlFor="subject-name">New subject name</Label>
              <Input
                id="subject-name"
                placeholder="e.g. Thermodynamics"
                value={newSubjectName}
                onChange={(e) => setNewSubjectName(e.target.value)}
                disabled={busy}
              />
            </div>
          )}

          <div className="space-y-2">
            <Label htmlFor="file">PDF file</Label>
            <Input
              id="file"
              type="file"
              accept="application/pdf,.pdf"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              disabled={busy}
            />
          </div>

          {error && <p className="text-sm text-destructive">{error}</p>}
        </div>

        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={busy}
          >
            Cancel
          </Button>
          <Button onClick={() => void handleSubmit()} disabled={!canSubmit}>
            {busy ? "Reading your PDF…" : "Upload"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

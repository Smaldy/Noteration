import { AnimatePresence, motion } from "framer-motion";
import { CheckCircle2, Loader2, UploadCloud } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

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
import type { UploadResult } from "@/types/document";

const NEW_SUBJECT = "__new__";

/** Upload lifecycle: pick a file (form), transfer it, analyse it, done. */
type Phase = "form" | "uploading" | "analysing" | "ready";

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
  const { t } = useTranslation();
  const { subjects, fetchSubjects } = useSubjectsStore();
  const createSubject = useSubjectsStore((s) => s.createSubject);
  const uploadDocument = store((s) => s.uploadDocument);

  const [subjectChoice, setSubjectChoice] = useState<string>(NEW_SUBJECT);
  const [newSubjectName, setNewSubjectName] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [phase, setPhase] = useState<Phase>("form");
  const [uploadPct, setUploadPct] = useState(0);
  const [result, setResult] = useState<UploadResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const routeTimer = useRef<number | null>(null);

  const busy = phase !== "form";

  // Load subjects whenever the dialog opens; reset transient state on close.
  useEffect(() => {
    if (open) {
      void fetchSubjects();
    } else {
      setNewSubjectName("");
      setFile(null);
      setError(null);
      setPhase("form");
      setUploadPct(0);
      setResult(null);
    }
  }, [open, fetchSubjects]);

  // Clean up the auto-route timer on unmount.
  useEffect(
    () => () => {
      if (routeTimer.current) window.clearTimeout(routeTimer.current);
    },
    [],
  );

  const creatingNew = subjectChoice === NEW_SUBJECT;
  const canSubmit =
    file !== null &&
    !busy &&
    (creatingNew ? newSubjectName.trim().length > 0 : true);

  async function handleSubmit() {
    if (file === null) return;
    setError(null);
    setUploadPct(0);
    setPhase("uploading");
    try {
      const subjectId = creatingNew
        ? (await createSubject({ name: newSubjectName.trim() })).id
        : Number(subjectChoice);
      const uploaded = await uploadDocument(subjectId, file, (pct) => {
        setUploadPct(pct);
        if (pct >= 100) setPhase("analysing");
      });
      setResult(uploaded);
      setPhase("ready");
      // Audio is transcribed in the background first (no markdown to review yet),
      // so just close back to the Library — its card shows the transcribing state
      // and becomes reviewable once the transcript is ready. PDFs go straight to
      // structure review.
      const isAudio = uploaded.document.source_type === "audio";
      routeTimer.current = window.setTimeout(
        () => {
          onOpenChange(false);
          if (!isAudio) onUploaded?.(uploaded.document.id);
        },
        isAudio ? 1600 : 1300,
      );
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("upload.failed"));
      setPhase("form");
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        // Don't let an escape/overlay click dismiss the dialog mid-transfer.
        if (!next && (phase === "uploading" || phase === "analysing")) return;
        onOpenChange(next);
      }}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{exam ? t("upload.titleExam") : t("upload.title")}</DialogTitle>
          <DialogDescription>
            {exam ? t("upload.descExam") : t("upload.desc")}
          </DialogDescription>
        </DialogHeader>

        <AnimatePresence mode="wait">
          {busy ? (
            <motion.div
              key="progress"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
            >
              <UploadProgress phase={phase} pct={uploadPct} result={result} exam={exam} />
            </motion.div>
          ) : (
            <motion.div
              key="form"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
            >
        <div className="space-y-4 py-2">
          <div className="space-y-2">
            <Label htmlFor="subject">{t("upload.subject")}</Label>
            <select
              id="subject"
              className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
              value={subjectChoice}
              onChange={(e) => setSubjectChoice(e.target.value)}
              disabled={busy}
            >
              <option value={NEW_SUBJECT}>{t("upload.newSubjectOption")}</option>
              {subjects.map((s) => (
                <option key={s.id} value={String(s.id)}>
                  {s.name}
                </option>
              ))}
            </select>
          </div>

          {creatingNew && (
            <div className="space-y-2">
              <Label htmlFor="subject-name">{t("upload.newSubjectName")}</Label>
              <Input
                id="subject-name"
                placeholder={t("upload.newSubjectPlaceholder")}
                value={newSubjectName}
                onChange={(e) => setNewSubjectName(e.target.value)}
                disabled={busy}
              />
            </div>
          )}

          <div className="space-y-2">
            <Label htmlFor="file">
              {exam ? t("upload.pdfFile") : t("upload.fileLabel")}
            </Label>
            <Input
              id="file"
              type="file"
              accept={
                exam
                  ? "application/pdf,.pdf"
                  : "application/pdf,.pdf,audio/*,.mp3,.wav,.m4a,.aac,.ogg,.flac,.opus"
              }
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              disabled={busy}
            />
            {!exam && (
              <p className="text-xs text-muted-foreground">{t("upload.fileHint")}</p>
            )}
          </div>

          {error && <p className="text-sm text-destructive">{error}</p>}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {t("upload.cancel")}
          </Button>
          <Button onClick={() => void handleSubmit()} disabled={!canSubmit}>
            {t("upload.upload")}
          </Button>
        </DialogFooter>
            </motion.div>
          )}
        </AnimatePresence>
      </DialogContent>
    </Dialog>
  );
}

function UploadProgress({
  phase,
  pct,
  result,
  exam,
}: {
  phase: Phase;
  pct: number;
  result: UploadResult | null;
  exam: boolean;
}) {
  const { t } = useTranslation();
  return (
    <div className="flex flex-col items-center gap-4 py-8 text-center">
      <div className="grid size-14 place-items-center rounded-2xl bg-primary-soft text-primary-soft-foreground">
        {phase === "ready" ? (
          <motion.span
            initial={{ scale: 0.5, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            transition={{ type: "spring", stiffness: 320, damping: 18 }}
          >
            <CheckCircle2 className="size-7" />
          </motion.span>
        ) : phase === "uploading" ? (
          <UploadCloud className="size-7" />
        ) : (
          <Loader2 className="size-7 animate-spin" />
        )}
      </div>

      {phase === "uploading" && (
        <div className="w-full max-w-xs space-y-2">
          <p className="text-sm font-medium">{t("upload.progress.uploading")}</p>
          <div className="h-1.5 overflow-hidden rounded-full bg-muted">
            <motion.div
              className="h-full rounded-full bg-primary"
              initial={false}
              animate={{ width: `${pct}%` }}
              transition={{ duration: 0.2 }}
            />
          </div>
          <p className="text-xs tabular-nums text-muted-foreground">{pct}%</p>
        </div>
      )}

      {phase === "analysing" && (
        <div className="space-y-1">
          <p className="text-sm font-medium">{t("upload.progress.analysing")}</p>
          <p className="text-xs text-muted-foreground">
            {t("upload.progress.analysingHint")}
          </p>
        </div>
      )}

      {phase === "ready" && result && result.document.source_type === "audio" && (
        <div className="space-y-1">
          <p className="text-sm font-medium">{t("upload.progress.transcribing")}</p>
          <p className="text-xs text-muted-foreground">
            {t("upload.progress.transcribingHint")}
          </p>
        </div>
      )}

      {phase === "ready" && result && result.document.source_type !== "audio" && (
        <div className="space-y-1">
          <p className="text-sm font-medium">{t("upload.progress.ready")}</p>
          <p className="text-xs text-muted-foreground">
            {result.book_mode
              ? t("upload.progress.book", { count: result.page_count })
              : exam
                ? t("upload.progress.readExam", { count: result.page_count })
                : t("upload.progress.read", { count: result.page_count })}
          </p>
          <p className="text-xs text-muted-foreground">
            {t("upload.progress.openingReview")}
          </p>
        </div>
      )}
    </div>
  );
}

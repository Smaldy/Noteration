import { useEffect, useState } from "react";
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
import { useSubjectsStore } from "@/stores/subjects";

interface CreateSubjectDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Called with the new subject's id once it's created. */
  onCreated?: (subjectId: number) => void;
}

/** Create a subject on its own — no PDF or audio required. */
export function CreateSubjectDialog({
  open,
  onOpenChange,
  onCreated,
}: CreateSubjectDialogProps) {
  const { t } = useTranslation();
  const createSubject = useSubjectsStore((s) => s.createSubject);

  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) {
      setName("");
      setBusy(false);
      setError(null);
    }
  }, [open]);

  const canSubmit = name.trim().length > 0 && !busy;

  async function handleCreate() {
    if (!canSubmit) return;
    setBusy(true);
    setError(null);
    try {
      const subject = await createSubject({ name: name.trim() });
      onOpenChange(false);
      onCreated?.(subject.id);
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : t("library.newSubjectDialog.failed"),
      );
      setBusy(false);
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!busy) onOpenChange(next);
      }}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("library.newSubjectDialog.title")}</DialogTitle>
          <DialogDescription>{t("library.newSubjectDialog.desc")}</DialogDescription>
        </DialogHeader>

        <div className="space-y-2 py-2">
          <Label htmlFor="new-subject-name">{t("upload.newSubjectName")}</Label>
          <Input
            id="new-subject-name"
            placeholder={t("upload.newSubjectPlaceholder")}
            value={name}
            onChange={(e) => setName(e.target.value)}
            disabled={busy}
            autoFocus
            onKeyDown={(e) => {
              if (e.key === "Enter") void handleCreate();
            }}
          />
          {error && <p className="text-sm text-destructive">{error}</p>}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>
            {t("upload.cancel")}
          </Button>
          <Button onClick={() => void handleCreate()} disabled={!canSubmit}>
            {t("library.newSubjectDialog.create")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

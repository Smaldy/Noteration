/** Turn an inert PDF sitting in a folder into real notes.
 *
 *  Always asks for the subject rather than silently using the folder's tag: the
 *  document is about to join a subject's hierarchy and its whole queue lane, so
 *  it's worth one confirmation. A tagged folder just prefills its own subject.
 */

import { Loader2, Sparkles } from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { api, ApiError } from "@/lib/api";
import { useFoldersStore } from "@/stores/folders";
import { useSubjectsStore } from "@/stores/subjects";
import type { FolderFile } from "@/types/folder";

export function GenerateNotesDialog({
  open,
  onOpenChange,
  file,
  /** Prefilled when the folder follows a subject. */
  defaultSubjectId,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  file: FolderFile | null;
  defaultSubjectId?: number | null;
}) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const subjects = useSubjectsStore((s) => s.subjects);
  const fetchSubjects = useSubjectsStore((s) => s.fetchSubjects);
  const openFolder = useFoldersStore((s) => s.openFolder);

  const [subjectId, setSubjectId] = useState<string>("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    void fetchSubjects();
    setSubjectId(defaultSubjectId != null ? String(defaultSubjectId) : "");
    setBusy(false);
    setError(null);
  }, [open, defaultSubjectId, fetchSubjects]);

  async function handleGenerate() {
    if (!file || !subjectId) return;
    setBusy(true);
    setError(null);
    try {
      const { document_id } = await api.post<{ document_id: number }>(
        `/folders/files/${file.id}/generate`,
        { subject_id: Number(subjectId) },
      );
      // Refresh so the promoted file disappears and its document takes its
      // place, then hand off to structure review like any other upload.
      await openFolder(file.folder_id);
      onOpenChange(false);
      navigate(`/documents/${document_id}/review`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("folders.generateFailed"));
      setBusy(false);
    }
  }

  if (!file) return null;

  return (
    <Dialog open={open} onOpenChange={(next) => !busy && onOpenChange(next)}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("folders.generateTitle")}</DialogTitle>
          <DialogDescription>
            {t("folders.generateDesc", { name: file.filename })}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-2 py-2">
          <Label>{t("folders.subjectTag")}</Label>
          <Select value={subjectId} onValueChange={setSubjectId} disabled={busy}>
            <SelectTrigger>
              <SelectValue placeholder={t("folders.pickSubject")} />
            </SelectTrigger>
            <SelectContent>
              {subjects.map((s) => (
                <SelectItem key={s.id} value={String(s.id)}>
                  {s.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <p className="text-xs text-muted-foreground">{t("folders.generateHelp")}</p>
          {error && <p className="text-sm text-destructive">{error}</p>}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>
            {t("upload.cancel")}
          </Button>
          <Button onClick={() => void handleGenerate()} disabled={busy || !subjectId}>
            {busy ? <Loader2 className="animate-spin" /> : <Sparkles />}
            {t("folders.generate")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/** Create or edit a folder: name, color, subject tag, and delete.
 *
 *  One dialog for both because the fields are identical; passing a `folder`
 *  switches it to edit mode. This also stands in for the "…" menu the
 *  reference layouts show on each tray, which would otherwise need a dropdown
 *  primitive the project doesn't ship.
 */

import { Trash2 } from "lucide-react";
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
import { Switch } from "@/components/ui/switch";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ApiError } from "@/lib/api";
import { DEFAULT_TINT } from "@/lib/tints";
import { useFoldersStore } from "@/stores/folders";
import { useSubjectsStore } from "@/stores/subjects";
import type { Folder } from "@/types/folder";

import { TintPicker } from "./TintPicker";

/** Sentinel for "no subject tag" — Radix Select can't hold an empty string. */
const NO_SUBJECT = "none";

export function FolderDialog({
  open,
  onOpenChange,
  folder,
  parentId,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Omit to create; pass a folder to edit it. */
  folder?: Folder | null;
  /** Create a child of this folder (folders nest one level). */
  parentId?: number | null;
}) {
  const { t } = useTranslation();
  const { createFolder, updateFolder, deleteFolder } = useFoldersStore();
  const subjects = useSubjectsStore((s) => s.subjects);
  const fetchSubjects = useSubjectsStore((s) => s.fetchSubjects);

  const editing = folder != null;
  const [name, setName] = useState("");
  const [tint, setTint] = useState<string>(DEFAULT_TINT);
  const [subjectId, setSubjectId] = useState<string>(NO_SUBJECT);
  const [isMain, setIsMain] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    void fetchSubjects();
    setName(folder?.name ?? "");
    setTint(folder?.tint ?? DEFAULT_TINT);
    setSubjectId(folder?.subject_id != null ? String(folder.subject_id) : NO_SUBJECT);
    // New folders default to main: the common case is one folder per subject,
    // and the very first one has to be main or the subject mirrors nowhere.
    setIsMain(folder ? folder.is_main : true);
    setBusy(false);
    setError(null);
  }, [open, folder, fetchSubjects]);

  const canSubmit = name.trim().length > 0 && !busy;

  async function handleSubmit() {
    if (!canSubmit) return;
    setBusy(true);
    setError(null);
    const tagged = subjectId === NO_SUBJECT ? null : Number(subjectId);
    try {
      if (editing) {
        await updateFolder(folder.id, {
          name: name.trim(),
          tint,
          // `null` means "leave alone" server-side, so untagging is explicit.
          ...(tagged == null
            ? { clear_subject: true }
            : { subject_id: tagged, is_main: isMain }),
        });
      } else {
        await createFolder({
          name: name.trim(),
          tint,
          subject_id: tagged,
          parent_id: parentId ?? null,
          is_main: tagged == null ? undefined : isMain,
        });
      }
      onOpenChange(false);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("folders.saveFailed"));
      setBusy(false);
    }
  }

  async function handleDelete() {
    if (!editing) return;
    const ok = window.confirm(t("folders.deleteConfirm", { name: folder.name }));
    if (!ok) return;
    setBusy(true);
    try {
      await deleteFolder(folder.id);
      onOpenChange(false);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("folders.saveFailed"));
      setBusy(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={(next) => !busy && onOpenChange(next)}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {editing ? t("folders.editTitle") : t("folders.newTitle")}
          </DialogTitle>
          <DialogDescription>
            {editing ? t("folders.editDesc") : t("folders.newDesc")}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-2">
          <div className="space-y-2">
            <Label htmlFor="folder-name">{t("folders.name")}</Label>
            <Input
              id="folder-name"
              placeholder={t("folders.namePlaceholder")}
              value={name}
              onChange={(e) => setName(e.target.value)}
              disabled={busy}
              autoFocus
              onKeyDown={(e) => {
                if (e.key === "Enter") void handleSubmit();
              }}
            />
          </div>

          <TintPicker value={tint} onChange={setTint} />

          <div className="space-y-2">
            <Label>{t("folders.subjectTag")}</Label>
            <Select value={subjectId} onValueChange={setSubjectId} disabled={busy}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={NO_SUBJECT}>{t("folders.noSubject")}</SelectItem>
                {subjects.map((s) => (
                  <SelectItem key={s.id} value={String(s.id)}>
                    {s.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className="text-xs text-muted-foreground">
              {t("folders.subjectTagHelp")}
            </p>
          </div>

          {/* Only the main folder mirrors its subject, so several folders can
              share a subject without every one of them listing all its notes. */}
          {subjectId !== NO_SUBJECT && (
            <div className="flex items-start justify-between gap-4 rounded-xl border p-3">
              <div className="min-w-0">
                <Label htmlFor="folder-main" className="text-sm font-medium">
                  {t("folders.mainFolder")}
                </Label>
                <p className="mt-1 text-xs text-muted-foreground">
                  {t("folders.mainFolderHelp")}
                </p>
              </div>
              <Switch
                id="folder-main"
                checked={isMain}
                onCheckedChange={setIsMain}
                disabled={busy}
              />
            </div>
          )}

          {error && <p className="text-sm text-destructive">{error}</p>}
        </div>

        <DialogFooter className="sm:justify-between">
          {editing ? (
            <Button
              variant="outline"
              onClick={() => void handleDelete()}
              disabled={busy}
              className="text-destructive hover:text-destructive"
            >
              <Trash2 />
              {t("folders.delete")}
            </Button>
          ) : (
            <span />
          )}
          <div className="flex gap-2">
            <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>
              {t("upload.cancel")}
            </Button>
            <Button onClick={() => void handleSubmit()} disabled={!canSubmit}>
              {editing ? t("folders.save") : t("folders.create")}
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

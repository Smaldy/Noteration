/** Create or rename a colored sub-group inside a folder. */

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
import { ApiError } from "@/lib/api";
import { DEFAULT_TINT } from "@/lib/tints";
import { useFoldersStore } from "@/stores/folders";
import type { FolderGroup } from "@/types/folder";

import { TintPicker } from "./TintPicker";

export function GroupDialog({
  open,
  onOpenChange,
  folderId,
  group,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  folderId: number;
  /** Omit to create; pass a group to edit it. */
  group?: FolderGroup | null;
}) {
  const { t } = useTranslation();
  const { createGroup, updateGroup, deleteGroup } = useFoldersStore();

  const editing = group != null;
  const [name, setName] = useState("");
  const [tint, setTint] = useState<string>(DEFAULT_TINT);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setName(group?.name ?? "");
    setTint(group?.tint ?? DEFAULT_TINT);
    setBusy(false);
    setError(null);
  }, [open, group]);

  const canSubmit = name.trim().length > 0 && !busy;

  async function handleSubmit() {
    if (!canSubmit) return;
    setBusy(true);
    setError(null);
    try {
      if (editing) await updateGroup(group.id, { name: name.trim(), tint });
      else await createGroup(folderId, name.trim(), tint);
      onOpenChange(false);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("folders.saveFailed"));
      setBusy(false);
    }
  }

  async function handleDelete() {
    if (!editing) return;
    // Worth stating plainly: unlike deleting a folder, this keeps the contents.
    const ok = window.confirm(t("folders.deleteGroupConfirm", { name: group.name }));
    if (!ok) return;
    setBusy(true);
    try {
      await deleteGroup(group.id);
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
            {editing ? t("folders.editGroupTitle") : t("folders.newGroupTitle")}
          </DialogTitle>
          <DialogDescription>{t("folders.groupDesc")}</DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-2">
          <div className="space-y-2">
            <Label htmlFor="group-name">{t("folders.name")}</Label>
            <Input
              id="group-name"
              placeholder={t("folders.groupNamePlaceholder")}
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

/** Copy a note into another folder.
 *
 *  "Copy" is a reference, not a duplicate: the note keeps living in its subject
 *  and simply becomes visible in a second folder too. Nothing is duplicated on
 *  disk or in the hierarchy, so editing it in one place edits it everywhere.
 */

import { Check, FolderInput } from "lucide-react";
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
import { ApiError } from "@/lib/api";
import { tintSkin } from "@/lib/tints";
import { cn } from "@/lib/utils";
import { useFoldersStore } from "@/stores/folders";
import type { DocumentSummary } from "@/types/library";

export function CopyToFolderDialog({
  open,
  onOpenChange,
  doc,
  /** The folder the note is being copied *from*, hidden from the list. */
  currentFolderId,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  doc: DocumentSummary | null;
  currentFolderId?: number;
}) {
  const { t } = useTranslation();
  const { folders, fetchFolders, addDocuments } = useFoldersStore();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<number | null>(null);

  useEffect(() => {
    if (!open) return;
    void fetchFolders();
    setBusy(false);
    setError(null);
    setDone(null);
  }, [open, fetchFolders]);

  const targets = folders.filter((f) => f.id !== currentFolderId);

  async function copyTo(folderId: number) {
    if (!doc) return;
    setBusy(true);
    setError(null);
    try {
      await addDocuments(folderId, [doc.id]);
      // Stay open with a tick: copying into several folders in a row is the
      // common case, and reopening the dialog each time is friction.
      setDone(folderId);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("folders.copyFailed"));
    } finally {
      setBusy(false);
    }
  }

  if (!doc) return null;

  return (
    <Dialog open={open} onOpenChange={(next) => !busy && onOpenChange(next)}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("folders.copyTitle")}</DialogTitle>
          <DialogDescription>
            {t("folders.copyDesc", { name: doc.filename })}
          </DialogDescription>
        </DialogHeader>

        <div className="max-h-72 space-y-1 overflow-y-auto py-2">
          {targets.length === 0 && (
            <p className="p-3 text-sm text-muted-foreground">
              {t("folders.copyNoTargets")}
            </p>
          )}
          {targets.map((folder) => {
            const skin = tintSkin(folder.tint);
            const copied = done === folder.id;
            return (
              <button
                key={folder.id}
                type="button"
                disabled={busy}
                onClick={() => void copyTo(folder.id)}
                className={cn(
                  "flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left transition-colors",
                  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                  "hover:bg-muted disabled:opacity-60",
                )}
              >
                <span
                  style={skin.dotStyle}
                  className={cn("size-3 shrink-0 rounded-full", skin.dot)}
                />
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm font-medium">
                    {folder.name}
                  </span>
                  {folder.subject_id != null && (
                    <span className="block text-xs text-muted-foreground">
                      {t("folders.followsSubject")}
                    </span>
                  )}
                </span>
                {copied ? (
                  <span className="flex items-center gap-1 text-xs font-medium text-success">
                    <Check className="size-3.5" />
                    {t("folders.copied")}
                  </span>
                ) : (
                  <FolderInput className="size-4 shrink-0 text-muted-foreground" />
                )}
              </button>
            );
          })}
        </div>

        {error && <p className="text-sm text-destructive">{error}</p>}

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>
            {t("folders.doneCopying")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

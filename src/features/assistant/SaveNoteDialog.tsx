import { NotebookPen } from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { ApiError, api } from "@/lib/api";
import type { ReferenceTopic } from "@/stores/assistant";
import type { Note } from "@/types/study";

import { TopicPicker } from "./TopicPicker";

interface SaveNoteDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** The assistant reply markdown being saved. */
  content: string;
  /** Fired after the note is created (the caller flashes its Saved state). */
  onSaved: () => void;
}

/**
 * Topic picker for "Save as note": choose a subject, then one of its study
 * topics, and the reply lands there through the normal manual-note path
 * (`POST /notes`) — the result is an ordinary editable note block.
 */
export function SaveNoteDialog({
  open,
  onOpenChange,
  content,
  onSaved,
}: SaveNoteDialogProps) {
  const { t } = useTranslation();
  const [picked, setPicked] = useState<ReferenceTopic | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setPicked(null);
    setSaveError(null);
  }, [open]);

  async function handleSave() {
    if (picked === null) return;
    setSaving(true);
    setSaveError(null);
    try {
      await api.post<Note>("/notes", {
        topic_id: picked.id,
        content_md: content,
      });
      onOpenChange(false);
      onSaved();
    } catch (err) {
      setSaveError(
        err instanceof ApiError ? err.message : t("assistant.saveDialog.failed"),
      );
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[85vh] w-full max-w-lg flex-col gap-0 overflow-hidden p-0">
        <DialogHeader className="border-b px-6 py-4 text-left">
          <DialogTitle className="flex items-center gap-2">
            <NotebookPen className="size-4 text-primary" />
            {t("assistant.saveDialog.title")}
          </DialogTitle>
          <DialogDescription>
            {t("assistant.saveDialog.description")}
          </DialogDescription>
        </DialogHeader>

        <div className="min-h-0 flex-1 space-y-4 overflow-y-auto px-6 py-4">
          <TopicPicker open={open} value={picked} onChange={setPicked} />
        </div>

        <div className="space-y-3 border-t px-6 py-4">
          {saveError && <p className="text-sm text-destructive">{saveError}</p>}
          <div className="flex justify-end gap-2">
            <Button variant="outline" size="sm" onClick={() => onOpenChange(false)}>
              {t("common.cancel")}
            </Button>
            <Button
              size="sm"
              disabled={picked === null || saving}
              onClick={() => void handleSave()}
            >
              {saving
                ? t("assistant.saveDialog.saving")
                : t("assistant.saveDialog.save")}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

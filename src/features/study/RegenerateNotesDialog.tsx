import { RefreshCw } from "lucide-react";
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
import { Label } from "@/components/ui/label";
import { ApiError } from "@/lib/api";
import { useStudyStore } from "@/stores/study";

interface Props {
  topicId: number;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

/**
 * Regenerate a topic's AI notes when they don't satisfy the reader. The optional
 * "what should change" feedback steers the rewrite; the quiz and flashcards (and
 * their SM-2 review state) are left untouched server-side.
 */
export function RegenerateNotesDialog({ topicId, open, onOpenChange }: Props) {
  const { t } = useTranslation();
  const regenerateNotes = useStudyStore((s) => s.regenerateNotes);
  const [instructions, setInstructions] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Reset the form each time the dialog opens.
  useEffect(() => {
    if (!open) return;
    setInstructions("");
    setBusy(false);
    setError(null);
  }, [open]);

  async function run() {
    setBusy(true);
    setError(null);
    try {
      await regenerateNotes(topicId, instructions);
      onOpenChange(false);
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : t("study.notes.regenerateError"),
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={busy ? undefined : onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <RefreshCw className="size-5 text-primary" />
            {t("study.notes.regenerateDialog.title")}
          </DialogTitle>
          <DialogDescription>
            {t("study.notes.regenerateDialog.desc")}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-2 py-2">
          <Label htmlFor="regen-feedback">
            {t("study.notes.regenerateDialog.feedbackLabel")}
          </Label>
          <textarea
            id="regen-feedback"
            value={instructions}
            onChange={(e) => setInstructions(e.target.value)}
            disabled={busy}
            rows={4}
            maxLength={2000}
            placeholder={t("study.notes.regenerateDialog.feedbackPlaceholder")}
            className="flex w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
          />
          {error && <p className="text-sm text-destructive">{error}</p>}
        </div>

        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={busy}
          >
            {t("study.notes.regenerateDialog.cancel")}
          </Button>
          <Button onClick={() => void run()} disabled={busy}>
            {busy
              ? t("study.notes.regenerating")
              : t("study.notes.regenerateDialog.confirm")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

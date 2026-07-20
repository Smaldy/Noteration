import { BookMarked } from "lucide-react";
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
import { type ReferenceTopic, useAssistantStore } from "@/stores/assistant";

import { TopicPicker } from "./TopicPicker";

/**
 * Pin a topic as the session's reference: from then on every reply is grounded
 * in that topic's stored material (the backend retrieves the relevant passages).
 * The chip in the header shows what is pinned, and removes it.
 */
export function ReferenceTopicDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const { t } = useTranslation();
  const referenceTopic = useAssistantStore((s) => s.referenceTopic);
  const setReferenceTopic = useAssistantStore((s) => s.setReferenceTopic);
  const [picked, setPicked] = useState<ReferenceTopic | null>(null);

  // Reopening starts from whatever is pinned, so the current choice is visible.
  useEffect(() => {
    if (open) setPicked(referenceTopic);
  }, [open, referenceTopic]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[85vh] w-full max-w-lg flex-col gap-0 overflow-hidden p-0">
        <DialogHeader className="border-b px-6 py-4 text-left">
          <DialogTitle className="flex items-center gap-2">
            <BookMarked className="size-4 text-primary" />
            {t("assistant.reference.dialogTitle")}
          </DialogTitle>
          <DialogDescription>
            {t("assistant.reference.dialogDescription")}
          </DialogDescription>
        </DialogHeader>

        <div className="min-h-0 flex-1 space-y-4 overflow-y-auto px-6 py-4">
          <TopicPicker open={open} value={picked} onChange={setPicked} />
        </div>

        <div className="flex justify-end gap-2 border-t px-6 py-4">
          <Button variant="outline" size="sm" onClick={() => onOpenChange(false)}>
            {t("common.cancel")}
          </Button>
          <Button
            size="sm"
            disabled={picked === null}
            onClick={() => {
              setReferenceTopic(picked);
              onOpenChange(false);
            }}
          >
            {t("assistant.reference.confirm")}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

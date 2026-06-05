import { Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useCalendarStore } from "@/stores/calendar";
import type { CalendarEntry } from "@/types/calendar";

import { TimeField } from "./TimeField";

interface Props {
  entry: CalendarEntry | null;
  onClose: () => void;
}

export function EditEventDialog({ entry, onClose }: Props) {
  const { t } = useTranslation();
  const { updateEntry, deleteEntry } = useCalendarStore();
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [date, setDate] = useState("");
  const [useTime, setUseTime] = useState(false);
  const [time, setTime] = useState("09:00");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!entry) return;
    setTitle(entry.title);
    setDescription(entry.description ?? "");
    setDate(entry.date);
    setUseTime(entry.start_time != null);
    setTime(entry.start_time ?? "09:00");
    setBusy(false);
  }, [entry]);

  if (!entry) return null;

  async function handleSave() {
    if (!entry) return;
    setBusy(true);
    try {
      // Off clears the time (back to all-day); on pins it.
      await updateEntry(entry.id, {
        title,
        description,
        date,
        start_time: useTime ? time : null,
      });
      onClose();
    } catch {
      setBusy(false);
    }
  }

  async function handleDelete() {
    if (!entry) return;
    if (!window.confirm(t("calendar.dialog.removeEventConfirm"))) return;
    setBusy(true);
    try {
      await deleteEntry(entry.id);
      onClose();
    } catch {
      setBusy(false);
    }
  }

  // Subject sessions keep their name (the subject label); custom events and
  // deadlines expose a free-text name field.
  const editableTitle = entry.kind === "custom" || entry.kind === "deadline";
  const heading =
    entry.kind === "subject"
      ? t("calendar.dialog.subjectSession")
      : entry.kind === "deadline"
        ? t("calendar.dialog.examDeadline")
        : t("calendar.dialog.editEvent");

  return (
    <Dialog open={entry !== null} onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{heading}</DialogTitle>
        </DialogHeader>

        {entry.kind === "deadline" && (
          <p className="rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-muted-foreground">
            {t("calendar.dialog.deadlineEditHint")}
          </p>
        )}

        <div className="space-y-4 py-2">
          {editableTitle ? (
            <div className="space-y-2">
              <Label htmlFor="edit-title">{t("calendar.dialog.name")}</Label>
              <Input
                id="edit-title"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                disabled={busy}
              />
            </div>
          ) : (
            <p className="rounded-md border bg-muted/40 px-3 py-2 text-sm font-medium">
              {entry.title}
            </p>
          )}

          <div className="space-y-2">
            <Label htmlFor="edit-date">{t("calendar.dialog.date")}</Label>
            <Input
              id="edit-date"
              type="date"
              value={date}
              onChange={(e) => setDate(e.target.value)}
              disabled={busy}
            />
          </div>

          <TimeField
            enabled={useTime}
            onToggle={setUseTime}
            time={time}
            onTime={setTime}
            disabled={busy}
          />

          <div className="space-y-2">
            <Label htmlFor="edit-desc">
              {t("calendar.dialog.notes")}{" "}
              <span className="text-muted-foreground">
                {t("calendar.dialog.optional")}
              </span>
            </Label>
            <textarea
              id="edit-desc"
              rows={3}
              className="flex w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              disabled={busy}
            />
          </div>
        </div>

        <DialogFooter className="sm:justify-between">
          <Button
            variant="ghost"
            className="text-destructive hover:text-destructive"
            onClick={() => void handleDelete()}
            disabled={busy}
          >
            <Trash2 className="size-4" />
            {t("calendar.dialog.delete")}
          </Button>
          <div className="flex gap-2">
            <Button variant="outline" onClick={onClose} disabled={busy}>
              {t("calendar.dialog.cancel")}
            </Button>
            <Button onClick={() => void handleSave()} disabled={busy}>
              {busy ? t("calendar.dialog.saving") : t("calendar.dialog.save")}
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

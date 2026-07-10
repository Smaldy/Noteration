import { Check, Search } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ApiError } from "@/lib/api";
import { cn } from "@/lib/utils";
import { useCalendarStore } from "@/stores/calendar";
import type { CatalogTopic } from "@/types/calendar";

import { TimeField } from "./TimeField";

type Mode = "custom" | "topic" | "subject" | "deadline";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Prefill the date (YYYY-MM-DD). */
  presetDate?: string;
  /** Prefill the start time (HH:MM), e.g. from an hourly-grid slot click. */
  presetTime?: string;
  /** When set, lock to a single topic (e.g. opened from the Study View). */
  presetTopic?: { id: number; title: string };
  onCreated?: () => void;
}

function todayIso(): string {
  // Local calendar date (not UTC) so the default matches the day the user sees —
  // `toISOString()` would roll to tomorrow in negative-UTC zones late in the day.
  const d = new Date();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${d.getFullYear()}-${m}-${day}`;
}

export function AddToCalendarDialog({
  open,
  onOpenChange,
  presetDate,
  presetTime,
  presetTopic,
  onCreated,
}: Props) {
  const { t } = useTranslation();
  const { catalog, fetchCatalog, createEntry } = useCalendarStore();

  const [mode, setMode] = useState<Mode>(presetTopic ? "topic" : "custom");
  const [date, setDate] = useState(presetDate ?? todayIso());
  const [useTime, setUseTime] = useState(!!presetTime);
  const [time, setTime] = useState(presetTime || "09:00");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [search, setSearch] = useState("");
  const [topic, setTopic] = useState<CatalogTopic | null>(null);
  const [subjectId, setSubjectId] = useState<string>("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Reset transient state on open; pull the catalog for the pickers.
  useEffect(() => {
    if (!open) return;
    void fetchCatalog();
    setMode(presetTopic ? "topic" : "custom");
    setDate(presetDate ?? todayIso());
    setUseTime(!!presetTime);
    setTime(presetTime || "09:00");
    setTitle("");
    setDescription("");
    setSearch("");
    setTopic(
      presetTopic
        ? {
            id: presetTopic.id,
            title: presetTopic.title,
            chapter_title: "",
            document_id: 0,
            document_filename: "",
            studied: false,
          }
        : null,
    );
    setSubjectId("");
    setBusy(false);
    setError(null);
  }, [open, presetDate, presetTime, presetTopic, fetchCatalog]);

  const filteredSubjects = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return catalog;
    return catalog
      .map((s) => ({
        ...s,
        topics: s.topics.filter((t) => t.title.toLowerCase().includes(q)),
      }))
      .filter((s) => s.topics.length > 0 || s.name.toLowerCase().includes(q));
  }, [catalog, search]);

  const needsSubject = mode === "subject" || mode === "deadline";
  const canSubmit =
    !busy &&
    !!date &&
    (mode === "custom"
      ? title.trim().length > 0
      : mode === "topic"
        ? topic !== null
        : subjectId !== "");

  async function handleSubmit() {
    setBusy(true);
    setError(null);
    try {
      await createEntry({
        date,
        start_time: useTime ? time : undefined,
        title: title.trim() || undefined,
        description: description.trim() || undefined,
        topic_id: mode === "topic" && topic ? topic.id : undefined,
        subject_id: needsSubject && subjectId ? Number(subjectId) : undefined,
        is_deadline: mode === "deadline" || undefined,
      });
      onOpenChange(false);
      onCreated?.();
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : t("calendar.dialog.addFailed"),
      );
      setBusy(false);
    }
  }

  const locked = !!presetTopic;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90dvh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{t("calendar.dialog.title")}</DialogTitle>
          <DialogDescription>
            {locked
              ? t("calendar.dialog.descLocked")
              : t("calendar.dialog.desc")}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-2">
          {!locked && (
            <div className="grid grid-cols-4 gap-1 rounded-lg bg-muted p-1">
              {(["custom", "topic", "subject", "deadline"] as Mode[]).map((m) => (
                <button
                  key={m}
                  type="button"
                  onClick={() => setMode(m)}
                  className={cn(
                    "rounded-md px-2 py-1.5 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                    mode === m
                      ? "bg-card text-foreground shadow-sm"
                      : "text-muted-foreground hover:text-foreground",
                  )}
                >
                  {t(`calendar.dialog.modes.${m}`)}
                </button>
              ))}
            </div>
          )}

          {locked && (
            <p className="rounded-lg border bg-muted/40 px-3 py-2 text-sm">
              {t("calendar.dialog.lockedTopic", { title: presetTopic.title })}
            </p>
          )}

          {(mode === "custom" || mode === "deadline") && (
            <div className="space-y-2">
              <Label htmlFor="ev-title">
                {mode === "deadline" ? (
                  <>
                    {t("calendar.dialog.examName")}{" "}
                    <span className="text-muted-foreground">
                      {t("calendar.dialog.optional")}
                    </span>
                  </>
                ) : (
                  t("calendar.dialog.eventName")
                )}
              </Label>
              <Input
                id="ev-title"
                placeholder={
                  mode === "deadline"
                    ? t("calendar.dialog.examPlaceholder")
                    : t("calendar.dialog.eventPlaceholder")
                }
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                disabled={busy}
              />
            </div>
          )}

          {mode === "topic" && !locked && (
            <div className="space-y-2">
              <Label>{t("calendar.dialog.topic")}</Label>
              <div className="relative">
                <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                  className="pl-9"
                  placeholder={t("calendar.dialog.searchTopics")}
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  disabled={busy}
                />
              </div>
              <div className="max-h-56 space-y-3 overflow-y-auto rounded-lg border p-2">
                {filteredSubjects.length === 0 && (
                  <p className="px-1 py-2 text-sm text-muted-foreground">
                    {t("calendar.dialog.noTopics")}
                  </p>
                )}
                {filteredSubjects.map((s) => (
                  <div key={s.id}>
                    <p className="px-1 pb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                      {s.name}
                    </p>
                    <ul className="space-y-0.5">
                      {s.topics.map((t) => (
                        <li key={t.id}>
                          <button
                            type="button"
                            onClick={() => setTopic(t)}
                            className={cn(
                              "flex w-full items-center justify-between gap-2 rounded-md px-2 py-1.5 text-left text-sm transition-colors hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                              topic?.id === t.id && "bg-primary-soft text-primary-soft-foreground",
                            )}
                          >
                            <span className="min-w-0 truncate">{t.title}</span>
                            {topic?.id === t.id && <Check className="size-4 shrink-0" />}
                          </button>
                        </li>
                      ))}
                      {s.topics.length === 0 && (
                        <li className="px-2 py-1 text-xs italic text-muted-foreground">
                          {t("calendar.dialog.noTopicsYet")}
                        </li>
                      )}
                    </ul>
                  </div>
                ))}
              </div>
            </div>
          )}

          {needsSubject && (
            <div className="space-y-2">
              <Label htmlFor="ev-subject">{t("calendar.dialog.subject")}</Label>
              <Select value={subjectId || undefined} onValueChange={setSubjectId} disabled={busy}>
                <SelectTrigger id="ev-subject">
                  <SelectValue placeholder={t("calendar.dialog.selectSubject")} />
                </SelectTrigger>
                <SelectContent>
                  {catalog.map((s) => (
                    <SelectItem key={s.id} value={String(s.id)}>
                      {s.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {mode === "deadline" && (
                <p className="text-xs text-muted-foreground">
                  {t("calendar.dialog.deadlineHint")}
                </p>
              )}
            </div>
          )}

          <div className="space-y-2">
            <Label htmlFor="ev-date">{t("calendar.dialog.date")}</Label>
            <Input
              id="ev-date"
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
            <Label htmlFor="ev-desc">
              {t("calendar.dialog.notes")}{" "}
              <span className="text-muted-foreground">
                {t("calendar.dialog.optional")}
              </span>
            </Label>
            <textarea
              id="ev-desc"
              rows={2}
              className="flex w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
              placeholder={t("calendar.dialog.notesPlaceholder")}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              disabled={busy}
            />
          </div>

          {error && <p className="text-sm text-destructive">{error}</p>}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>
            {t("calendar.dialog.cancel")}
          </Button>
          <Button onClick={() => void handleSubmit()} disabled={!canSubmit}>
            {busy ? t("calendar.dialog.adding") : t("calendar.dialog.add")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

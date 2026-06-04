import { Check, Search } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

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
  return new Date().toISOString().slice(0, 10);
}

export function AddToCalendarDialog({
  open,
  onOpenChange,
  presetDate,
  presetTime,
  presetTopic,
  onCreated,
}: Props) {
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
        err instanceof ApiError ? err.message : "Couldn't add it. Please try again.",
      );
      setBusy(false);
    }
  }

  const locked = !!presetTopic;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90dvh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Add to calendar</DialogTitle>
          <DialogDescription>
            {locked
              ? "Schedule a study session for this topic."
              : "Schedule a custom event, a topic or subject to study, or an exam deadline."}
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
                    "rounded-md px-2 py-1.5 text-sm font-medium capitalize transition-colors",
                    mode === m
                      ? "bg-card text-foreground shadow-sm"
                      : "text-muted-foreground hover:text-foreground",
                  )}
                >
                  {m === "custom" ? "Event" : m}
                </button>
              ))}
            </div>
          )}

          {locked && (
            <p className="rounded-md border bg-muted/40 px-3 py-2 text-sm">
              Topic: <span className="font-medium">{presetTopic.title}</span>
            </p>
          )}

          {(mode === "custom" || mode === "deadline") && (
            <div className="space-y-2">
              <Label htmlFor="ev-title">
                {mode === "deadline" ? (
                  <>
                    Exam name{" "}
                    <span className="text-muted-foreground">(optional)</span>
                  </>
                ) : (
                  "Event name"
                )}
              </Label>
              <Input
                id="ev-title"
                placeholder={
                  mode === "deadline"
                    ? "e.g. Final exam"
                    : "e.g. Revise the whole unit"
                }
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                disabled={busy}
              />
            </div>
          )}

          {mode === "topic" && !locked && (
            <div className="space-y-2">
              <Label>Topic</Label>
              <div className="relative">
                <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                  className="pl-9"
                  placeholder="Search topics…"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  disabled={busy}
                />
              </div>
              <div className="max-h-56 space-y-3 overflow-y-auto rounded-lg border p-2">
                {filteredSubjects.length === 0 && (
                  <p className="px-1 py-2 text-sm text-muted-foreground">
                    No topics found.
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
                              "flex w-full items-center justify-between gap-2 rounded-md px-2 py-1.5 text-left text-sm transition-colors hover:bg-muted",
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
                          No topics yet
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
              <Label htmlFor="ev-subject">Subject</Label>
              <select
                id="ev-subject"
                className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                value={subjectId}
                onChange={(e) => setSubjectId(e.target.value)}
                disabled={busy}
              >
                <option value="">Select a subject…</option>
                {catalog.map((s) => (
                  <option key={s.id} value={String(s.id)}>
                    {s.name}
                  </option>
                ))}
              </select>
              {mode === "deadline" && (
                <p className="text-xs text-muted-foreground">
                  Sets this subject's exam date so the AI study plan works toward it.
                </p>
              )}
            </div>
          )}

          <div className="space-y-2">
            <Label htmlFor="ev-date">Date</Label>
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
              Notes <span className="text-muted-foreground">(optional)</span>
            </Label>
            <textarea
              id="ev-desc"
              rows={2}
              className="flex w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
              placeholder="What to focus on…"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              disabled={busy}
            />
          </div>

          {error && <p className="text-sm text-destructive">{error}</p>}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>
            Cancel
          </Button>
          <Button onClick={() => void handleSubmit()} disabled={!canSubmit}>
            {busy ? "Adding…" : "Add to calendar"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

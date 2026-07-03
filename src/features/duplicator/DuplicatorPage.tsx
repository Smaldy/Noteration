import {
  ArrowLeft,
  FileText,
  PanelLeftClose,
  PanelLeftOpen,
  Sparkles,
  Upload,
} from "lucide-react";
import { type DragEvent, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";
import { useDuplicatorStore } from "@/stores/duplicator";

import { ExerciseFocusDialog } from "./ExerciseFocusDialog";
import { ExtractedExerciseCard } from "./ExtractedExerciseCard";

const YEAR_KEY = "duplicator_year_level";
const YEARS = [1, 2, 3, 4, 5];

function initialYear(): number {
  const stored = Number(localStorage.getItem(YEAR_KEY));
  return YEARS.includes(stored) ? stored : 1;
}

export function DuplicatorPage() {
  const navigate = useNavigate();
  const { t } = useTranslation();
  const { session, loading, error, upload, removeExercise, findMore } =
    useDuplicatorStore();
  const [file, setFile] = useState<File | null>(null);
  const [year, setYear] = useState<number>(initialYear);
  const [hint, setHint] = useState("");
  const [dragOver, setDragOver] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [focusIndex, setFocusIndex] = useState<number | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // The store's poll is a module-level setInterval; without this it keeps hitting
  // the API every 4s forever after you leave the page (and never stops if a job
  // is stuck). Tear it down on unmount, and resume it on entry if a prior session
  // is still in flight so returning to the page keeps results updating.
  useEffect(() => {
    const { session: current, poll } = useDuplicatorStore.getState();
    const inFlight = current?.exercises.some(
      (e) => e.status !== "done" && e.status !== "error",
    );
    if (current && inFlight) poll(current.id);
    return () => useDuplicatorStore.getState().stopPolling();
  }, []);

  const pickYear = (y: number) => {
    setYear(y);
    localStorage.setItem(YEAR_KEY, String(y));
  };

  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const dropped = e.dataTransfer.files?.[0];
    if (dropped && dropped.type === "application/pdf") setFile(dropped);
  };

  const submit = () => {
    if (file) {
      void upload(file, year, hint);
      // Hand the screen over to results once a run starts.
      setSidebarOpen(false);
    }
  };

  const exercises = session?.exercises ?? [];

  // Remove an exercise; if focus mode is open, keep the index in range (or close
  // if the list is now empty). removeExercise updates the store optimistically
  // and synchronously, so getState() already reflects the removal here.
  const handleRemove = (id: number) => {
    void removeExercise(id);
    setFocusIndex((idx) => {
      if (idx === null) return null;
      const remaining = useDuplicatorStore.getState().session?.exercises ?? [];
      return remaining.length === 0 ? null : Math.min(idx, remaining.length - 1);
    });
  };

  return (
    <div className="mx-auto max-w-7xl px-6 pb-10">
      {/* Sticky page header — back / panel toggle stay reachable without scrolling up. */}
      <div className="glass sticky top-0 z-20 -mx-6 mb-6 flex items-center gap-2 border-b border-border/60 px-6 py-3">
        <Button
          variant="ghost"
          size="icon"
          onClick={() => setSidebarOpen((v) => !v)}
          aria-label={
            sidebarOpen
              ? t("duplicator.upload.hideAria")
              : t("duplicator.upload.showAria")
          }
          title={
            sidebarOpen
              ? t("duplicator.upload.hideTitle")
              : t("duplicator.upload.showTitle")
          }
        >
          {sidebarOpen ? (
            <PanelLeftClose className="h-5 w-5" />
          ) : (
            <PanelLeftOpen className="h-5 w-5" />
          )}
        </Button>
        <Button variant="ghost" size="sm" data-arcade-sector="exam" onClick={() => navigate("/exam")}>
          <ArrowLeft className="h-4 w-4" /> {t("nav.examPrep")}
        </Button>
        <h1 className="font-display text-2xl font-semibold">{t("nav.duplicator")}</h1>
        {exercises.length > 0 && (
          <span className="ml-1 rounded-full bg-primary/10 px-2.5 py-0.5 text-xs font-semibold text-primary">
            {t("duplicator.header.exerciseCount", { count: exercises.length })}
          </span>
        )}
      </div>

      <div
        className={cn(
          "grid gap-6",
          sidebarOpen ? "lg:grid-cols-[320px_1fr]" : "grid-cols-1",
        )}
      >
        {/* Left control panel (collapsible) */}
        {sidebarOpen && (
          <aside className="animate-rise space-y-5 lg:sticky lg:top-20 lg:self-start">
            <div
              onClick={() => inputRef.current?.click()}
              onDragOver={(e) => {
                e.preventDefault();
                setDragOver(true);
              }}
              onDragLeave={() => setDragOver(false)}
              onDrop={onDrop}
              className={cn(
                "flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed px-4 py-8 text-center transition-colors",
                dragOver ? "border-primary bg-primary/5" : "border-border hover:border-primary/40",
              )}
            >
              <input
                ref={inputRef}
                type="file"
                accept="application/pdf"
                className="hidden"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              />
              {file ? (
                <>
                  <FileText className="mb-2 h-6 w-6 text-primary" />
                  <span className="text-sm font-medium">{file.name}</span>
                  <span className="mt-1 text-xs text-muted-foreground">
                    {t("duplicator.upload.changeFile")}
                  </span>
                </>
              ) : (
                <>
                  <Upload className="mb-2 h-6 w-6 text-muted-foreground" />
                  <span className="text-sm font-medium">
                    {t("duplicator.upload.dropHint")}
                  </span>
                  <span className="mt-1 text-xs text-muted-foreground">
                    {t("duplicator.upload.subtitle")}
                  </span>
                </>
              )}
            </div>

            <div>
              <Label className="mb-2 block text-xs">{t("duplicator.upload.yearLevel")}</Label>
              <div className="flex gap-1">
                {YEARS.map((y) => (
                  <button
                    key={y}
                    type="button"
                    onClick={() => pickYear(y)}
                    className={cn(
                      "flex-1 rounded-md py-1.5 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                      year === y
                        ? "bg-primary text-primary-foreground"
                        : "bg-muted text-muted-foreground hover:bg-muted/70",
                    )}
                  >
                    {t(`duplicator.year.${y}`)}
                  </button>
                ))}
              </div>
            </div>

            <div>
              <Label htmlFor="hint" className="mb-2 block text-xs">
                {t("duplicator.upload.subjectHintLabel")}
              </Label>
              <Input
                id="hint"
                value={hint}
                onChange={(e) => setHint(e.target.value)}
                placeholder={t("duplicator.upload.subjectHintPlaceholder")}
              />
            </div>

            <Button onClick={submit} disabled={!file || loading} className="w-full gap-2">
              <Sparkles className="h-4 w-4" />
              {loading ? t("duplicator.upload.extracting") : t("duplicator.upload.findVariants")}
            </Button>

            {error && <p className="text-sm text-destructive">{error}</p>}
          </aside>
        )}

        {/* Main results panel */}
        <main>
          {loading && exercises.length === 0 && (
            <div className="grid gap-5 lg:grid-cols-2">
              {[0, 1, 2, 3].map((i) => (
                <div
                  key={i}
                  className="h-56 animate-pulse rounded-xl border border-border bg-muted/40"
                />
              ))}
            </div>
          )}

          {!loading && exercises.length === 0 && (
            <div className="flex h-96 flex-col items-center justify-center rounded-xl border border-dashed border-border text-center">
              <Sparkles className="mb-3 h-8 w-8 text-muted-foreground" />
              <p className="text-sm font-medium">{t("duplicator.empty.title")}</p>
              <p className="mt-1 max-w-xs text-xs text-muted-foreground">
                {t("duplicator.empty.description")}
              </p>
              {!sidebarOpen && (
                <Button
                  variant="outline"
                  size="sm"
                  className="mt-4 gap-2"
                  onClick={() => setSidebarOpen(true)}
                >
                  <PanelLeftOpen className="h-4 w-4" /> {t("duplicator.empty.openPanel")}
                </Button>
              )}
            </div>
          )}

          {exercises.length > 0 && (
            <div
              className={cn(
                "grid gap-5",
                // More columns when the sidebar is tucked away.
                sidebarOpen ? "lg:grid-cols-2" : "md:grid-cols-2 xl:grid-cols-3",
              )}
            >
              {exercises.map((exercise, index) => (
                <ExtractedExerciseCard
                  key={exercise.id}
                  exercise={exercise}
                  index={index}
                  onFocus={() => setFocusIndex(index)}
                  onRemove={() => handleRemove(exercise.id)}
                />
              ))}
            </div>
          )}
        </main>
      </div>

      {focusIndex !== null && exercises[focusIndex] && (
        <ExerciseFocusDialog
          exercises={exercises}
          index={focusIndex}
          yearLevel={session?.year_level ?? year}
          onNavigate={setFocusIndex}
          onClose={() => setFocusIndex(null)}
          onRemove={handleRemove}
          onFindMore={findMore}
        />
      )}
    </div>
  );
}

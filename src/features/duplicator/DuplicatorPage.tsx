import { ArrowLeft, FileText, Sparkles, Upload } from "lucide-react";
import { type DragEvent, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useDuplicatorStore } from "@/stores/duplicator";

import { ExtractedExerciseCard } from "./ExtractedExerciseCard";

const YEAR_KEY = "duplicator_year_level";
const YEARS = [1, 2, 3, 4, 5];
const ORDINAL = ["1st", "2nd", "3rd", "4th", "5th"];

function initialYear(): number {
  const stored = Number(localStorage.getItem(YEAR_KEY));
  return YEARS.includes(stored) ? stored : 1;
}

export function DuplicatorPage() {
  const navigate = useNavigate();
  const { session, loading, error, upload } = useDuplicatorStore();
  const [file, setFile] = useState<File | null>(null);
  const [year, setYear] = useState<number>(initialYear);
  const [hint, setHint] = useState("");
  const [dragOver, setDragOver] = useState(false);
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
    if (file) void upload(file, year, hint);
  };

  const exercises = session?.exercises ?? [];

  return (
    <div className="mx-auto max-w-6xl px-6 py-8">
      <div className="mb-6 flex items-center gap-3">
        <Button variant="ghost" size="sm" onClick={() => navigate("/exam")}>
          <ArrowLeft className="h-4 w-4" /> Exam Prep
        </Button>
        <h1 className="font-display text-2xl font-semibold">Exercise Duplicator</h1>
      </div>

      <div className="grid gap-6 md:grid-cols-[320px_1fr]">
        {/* Left control panel */}
        <aside className="space-y-5">
          <div
            onClick={() => inputRef.current?.click()}
            onDragOver={(e) => {
              e.preventDefault();
              setDragOver(true);
            }}
            onDragLeave={() => setDragOver(false)}
            onDrop={onDrop}
            className={`flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed px-4 py-8 text-center transition-colors ${
              dragOver ? "border-primary bg-primary/5" : "border-border"
            }`}
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
                  Click to choose a different file
                </span>
              </>
            ) : (
              <>
                <Upload className="mb-2 h-6 w-6 text-muted-foreground" />
                <span className="text-sm font-medium">Drop a PDF or click to browse</span>
                <span className="mt-1 text-xs text-muted-foreground">
                  University math / physics exercises
                </span>
              </>
            )}
          </div>

          <div>
            <Label className="mb-2 block text-xs">Year level</Label>
            <div className="flex gap-1">
              {YEARS.map((y, i) => (
                <button
                  key={y}
                  type="button"
                  onClick={() => pickYear(y)}
                  className={`flex-1 rounded-md py-1.5 text-xs font-medium transition-colors ${
                    year === y
                      ? "bg-primary text-primary-foreground"
                      : "bg-muted text-muted-foreground hover:bg-muted/70"
                  }`}
                >
                  {ORDINAL[i]}
                </button>
              ))}
            </div>
          </div>

          <div>
            <Label htmlFor="hint" className="mb-2 block text-xs">
              Subject hint (optional)
            </Label>
            <Input
              id="hint"
              value={hint}
              onChange={(e) => setHint(e.target.value)}
              placeholder="e.g. complex analysis"
            />
          </div>

          <Button onClick={submit} disabled={!file || loading} className="w-full gap-2">
            <Sparkles className="h-4 w-4" />
            {loading ? "Extracting…" : "Find variants"}
          </Button>

          {error && <p className="text-sm text-destructive">{error}</p>}
        </aside>

        {/* Main results panel */}
        <main className="space-y-4">
          {loading && exercises.length === 0 && (
            <div className="space-y-4">
              {[0, 1, 2].map((i) => (
                <div
                  key={i}
                  className="h-40 animate-pulse rounded-xl border border-border bg-muted/40"
                />
              ))}
            </div>
          )}

          {!loading && exercises.length === 0 && (
            <div className="flex h-80 flex-col items-center justify-center rounded-xl border border-dashed border-border text-center">
              <Sparkles className="mb-3 h-8 w-8 text-muted-foreground" />
              <p className="text-sm font-medium">No exercises yet</p>
              <p className="mt-1 max-w-xs text-xs text-muted-foreground">
                Upload a PDF of exercises, pick the year level, and we'll extract each
                problem and search for real university-level variants.
              </p>
            </div>
          )}

          {exercises.map((exercise, index) => (
            <ExtractedExerciseCard
              key={exercise.id}
              exercise={exercise}
              index={index}
              yearLevel={session?.year_level ?? year}
            />
          ))}
        </main>
      </div>
    </div>
  );
}

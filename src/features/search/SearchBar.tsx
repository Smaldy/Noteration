import { AnimatePresence, motion } from "framer-motion";
import {
  ChevronDown,
  FileText,
  Layers,
  Loader2,
  Plus,
  Search,
  X,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { cn } from "@/lib/utils";
import { useSearchStore } from "@/stores/search";
import { useSubjectsStore } from "@/stores/subjects";
import type { TopicStatus } from "@/types/study";

// Status dot color for topic hits, mirroring the study view's vocabulary.
const STATUS_DOT: Record<TopicStatus, string> = {
  ready: "bg-emerald-500",
  processing: "bg-amber-500",
  queued: "bg-muted-foreground/50",
  error: "bg-destructive",
};

export function SearchBar({
  onCreateSubject,
}: {
  /** When set, the subject filter grows a "+" segment that opens subject creation. */
  onCreateSubject?: () => void;
}) {
  const navigate = useNavigate();
  const { t } = useTranslation();
  const { subjects, fetchSubjects } = useSubjectsStore();
  const { results, loading, error, search, reset } = useSearchStore();

  const [query, setQuery] = useState("");
  const [subjectId, setSubjectId] = useState<number | null>(null);
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    void fetchSubjects();
  }, [fetchSubjects]);

  // Debounce: search 180ms after the last keystroke / filter change.
  useEffect(() => {
    const id = setTimeout(() => void search(query, subjectId), 180);
    return () => clearTimeout(id);
  }, [query, subjectId, search]);

  // Close the dropdown when clicking outside the search area.
  useEffect(() => {
    function onDown(e: MouseEvent) {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, []);

  function go(documentId: number, kind: string, id: number) {
    const path =
      kind === "topic"
        ? `/documents/${documentId}/study/${id}`
        : `/documents/${documentId}/study`;
    setOpen(false);
    setQuery("");
    reset();
    navigate(path);
  }

  function clear() {
    setQuery("");
    reset();
  }

  const showPanel = open && (query.trim().length > 0 || subjectId != null);

  return (
    <div ref={wrapRef} className="relative">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
        {/* Search input */}
        <div className="relative flex-1">
          <Search className="pointer-events-none absolute left-3.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
          <input
            type="text"
            value={query}
            placeholder={t("search.placeholder")}
            onChange={(e) => setQuery(e.target.value)}
            onFocus={() => setOpen(true)}
            onKeyDown={(e) => {
              if (e.key === "Escape") {
                clear();
                setOpen(false);
              }
            }}
            className="h-11 w-full rounded-xl border bg-card/70 pl-10 pr-10 text-sm shadow-sm outline-none transition-all placeholder:text-muted-foreground focus:border-primary focus:ring-2 focus:ring-ring/40"
          />
          {loading ? (
            <Loader2 className="absolute right-3.5 top-1/2 size-4 -translate-y-1/2 animate-spin text-muted-foreground" />
          ) : (
            query && (
              <button
                type="button"
                onClick={clear}
                className="absolute right-3 top-1/2 -translate-y-1/2 rounded-md p-1 text-muted-foreground transition-colors hover:text-foreground"
                title={t("search.clear")}
              >
                <X className="size-4" />
              </button>
            )
          )}
        </div>

        {/* Subject filter (+ attached "new subject" segment) */}
        <div className="flex">
          <div className="relative flex-1 sm:flex-none">
            <select
              value={subjectId ?? ""}
              onChange={(e) => {
                const next = e.target.value === "" ? null : Number(e.target.value);
                setSubjectId(next);
                // Picking a subject is itself a filter action — open the results
                // panel even if the user never focused the text input.
                if (next != null) setOpen(true);
              }}
              className={cn(
                "h-11 w-full appearance-none rounded-xl border bg-card/70 pl-3.5 pr-9 text-sm shadow-sm outline-none transition-all hover:border-ring/40 focus:border-primary focus:ring-2 focus:ring-ring/40 sm:w-52",
                onCreateSubject && "rounded-r-none border-r-0",
              )}
            >
              <option value="">{t("search.allSubjects")}</option>
              {subjects.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
            <ChevronDown className="pointer-events-none absolute right-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
          </div>
          {onCreateSubject && (
            <button
              type="button"
              onClick={onCreateSubject}
              title={t("library.newSubject")}
              aria-label={t("library.newSubject")}
              className="flex h-11 w-11 shrink-0 items-center justify-center rounded-r-xl border bg-card/70 text-muted-foreground shadow-sm outline-none transition-all hover:border-ring/40 hover:text-foreground focus-visible:border-primary focus-visible:ring-2 focus-visible:ring-ring/40"
            >
              <Plus className="size-4" />
            </button>
          )}
        </div>
      </div>

      {/* Results dropdown */}
      <AnimatePresence>
        {showPanel && (
          <motion.div
            initial={{ opacity: 0, y: -6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -6 }}
            transition={{ duration: 0.16, ease: [0.22, 1, 0.36, 1] }}
            className="glass absolute z-30 mt-2 max-h-96 w-full overflow-y-auto rounded-xl border p-1.5 shadow-xl"
          >
            {error ? (
              <p className="px-3 py-6 text-center text-sm text-destructive">{error}</p>
            ) : results.length === 0 && !loading ? (
              <p className="px-3 py-6 text-center text-sm text-muted-foreground">
                {query.trim()
                  ? t("search.noMatches", { query: query.trim() })
                  : t("search.noMatchesSubject")}
              </p>
            ) : (
              <ul className="space-y-0.5">
                {results.map((r) => (
                  <li key={`${r.kind}-${r.id}`}>
                    <button
                      type="button"
                      onClick={() => go(r.document_id, r.kind, r.id)}
                      className="group flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left transition-colors hover:bg-accent"
                    >
                      <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-primary-soft text-primary-soft-foreground">
                        {r.kind === "topic" ? (
                          <FileText className="size-4" />
                        ) : (
                          <Layers className="size-4" />
                        )}
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="flex items-center gap-2">
                          {r.kind === "topic" && r.status && (
                            <span
                              className={cn(
                                "size-2 shrink-0 rounded-full",
                                STATUS_DOT[r.status],
                              )}
                            />
                          )}
                          <span className="truncate text-sm font-medium">{r.title}</span>
                        </span>
                        <span className="mt-0.5 block truncate text-xs text-muted-foreground">
                          {r.subject_name}
                          {r.kind === "topic" && ` · ${r.chapter_title}`} ·{" "}
                          {r.document_filename}
                        </span>
                      </span>
                      <span className="shrink-0 rounded-full bg-secondary px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-secondary-foreground">
                        {t(`search.kind.${r.kind}`, { defaultValue: r.kind })}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

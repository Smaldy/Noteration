/** The folder's "+" button: three ways to put something in a folder.
 *
 *  - **Generate** — the default, and the reason the dialog is usually opened:
 *    hands off to the normal upload flow, which runs the full ingest →
 *    structure review → generation pipeline.
 *  - **Notes** — place existing documents (this is also the copy action: a
 *    document already living in another folder is referenced, not moved).
 *  - **Files** — drop a PDF or image straight in. Stored inert; the folder view
 *    offers to generate notes from it later.
 */

import { FileUp, Loader2, Search, Sparkles } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ApiError } from "@/lib/api";
import { cn } from "@/lib/utils";
import { useFoldersStore } from "@/stores/folders";
import { useLibraryStore } from "@/stores/library";
import type { Folder } from "@/types/folder";

export function AddToFolderDialog({
  open,
  onOpenChange,
  folder,
  groupId = null,
  onUploadRequested,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  folder: Folder | null;
  /** Pre-file everything added here into this sub-group. */
  groupId?: number | null;
  /** Escape hatch to the full upload flow (the caller owns UploadDialog). */
  onUploadRequested: (folder: Folder) => void;
}) {
  const { t } = useTranslation();
  const { documents, fetchDocuments } = useLibraryStore();
  const { addDocuments, uploadFile } = useFoldersStore();

  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) return;
    void fetchDocuments();
    setQuery("");
    setSelected(new Set());
    setBusy(false);
    setError(null);
  }, [open, fetchDocuments]);

  const matches = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return documents;
    return documents.filter(
      (d) =>
        d.filename.toLowerCase().includes(needle) ||
        d.subject_name.toLowerCase().includes(needle),
    );
  }, [documents, query]);

  function toggle(id: number) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function handleAddNotes() {
    if (!folder || selected.size === 0) return;
    setBusy(true);
    setError(null);
    try {
      await addDocuments(folder.id, [...selected], groupId);
      onOpenChange(false);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("folders.addFailed"));
      setBusy(false);
    }
  }

  async function handleFiles(files: FileList | null) {
    if (!folder || !files?.length) return;
    setBusy(true);
    setError(null);
    try {
      // Sequential rather than Promise.all: SQLite takes one writer at a time,
      // and each upload commits a row.
      for (const file of Array.from(files)) {
        await uploadFile(folder.id, file, groupId);
      }
      onOpenChange(false);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("folders.addFailed"));
      setBusy(false);
    }
  }

  if (!folder) return null;

  return (
    <Dialog open={open} onOpenChange={(next) => !busy && onOpenChange(next)}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{t("folders.addTitle", { name: folder.name })}</DialogTitle>
          <DialogDescription>{t("folders.addDesc")}</DialogDescription>
        </DialogHeader>

        {/* Generating notes is the reason most people open this dialog, so it
            leads and is selected by default; placing existing notes and
            stashing a raw file are the rarer follow-ups. */}
        <Tabs defaultValue="generate">
          <TabsList className="w-full">
            <TabsTrigger value="generate" className="flex-1">
              {t("folders.tabGenerate")}
            </TabsTrigger>
            <TabsTrigger value="notes" className="flex-1">
              {t("folders.tabNotes")}
            </TabsTrigger>
            <TabsTrigger value="files" className="flex-1">
              {t("folders.tabFiles")}
            </TabsTrigger>
          </TabsList>

          <TabsContent value="generate" className="space-y-3">
            <button
              type="button"
              disabled={busy}
              onClick={() => {
                onOpenChange(false);
                onUploadRequested(folder);
              }}
              className="flex w-full flex-col items-center gap-2 rounded-2xl border-2 border-dashed border-primary/30 bg-primary-soft/40 py-10 text-muted-foreground transition-colors hover:border-primary/60 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <Sparkles className="size-6 text-primary" />
              <span className="text-sm font-semibold text-foreground">
                {t("folders.generateCta")}
              </span>
              <span className="px-6 text-center text-xs">
                {t("folders.generateCtaHint")}
              </span>
            </button>
          </TabsContent>

          <TabsContent value="notes" className="space-y-3">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                className="pl-9"
                placeholder={t("folders.searchNotes")}
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                disabled={busy}
              />
            </div>

            <div className="max-h-64 space-y-1 overflow-y-auto rounded-xl border p-1">
              {matches.length === 0 && (
                <p className="p-3 text-sm text-muted-foreground">
                  {t("folders.noNotesFound")}
                </p>
              )}
              {matches.map((doc) => {
                const checked = selected.has(doc.id);
                return (
                  <button
                    key={doc.id}
                    type="button"
                    onClick={() => toggle(doc.id)}
                    aria-pressed={checked}
                    className={cn(
                      "flex w-full items-center gap-3 rounded-lg px-3 py-2 text-left transition-colors",
                      "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                      checked ? "bg-primary-soft" : "hover:bg-muted",
                    )}
                  >
                    <span
                      className={cn(
                        "grid size-4 shrink-0 place-items-center rounded border",
                        checked && "border-primary bg-primary",
                      )}
                    >
                      {checked && (
                        <span className="size-1.5 rounded-full bg-primary-foreground" />
                      )}
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-sm font-medium">
                        {doc.filename}
                      </span>
                      <span className="block truncate text-xs text-muted-foreground">
                        {doc.subject_name}
                      </span>
                    </span>
                  </button>
                );
              })}
            </div>

            <div className="flex justify-end gap-2">
              <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>
                {t("upload.cancel")}
              </Button>
              <Button
                onClick={() => void handleAddNotes()}
                disabled={busy || selected.size === 0}
              >
                {busy && <Loader2 className="animate-spin" />}
                {t("folders.addSelected", { count: selected.size })}
              </Button>
            </div>
          </TabsContent>

          <TabsContent value="files" className="space-y-3">
            <input
              ref={fileInput}
              type="file"
              accept="application/pdf,image/*"
              multiple
              hidden
              onChange={(e) => void handleFiles(e.target.files)}
            />
            <button
              type="button"
              onClick={() => fileInput.current?.click()}
              disabled={busy}
              className="flex w-full flex-col items-center gap-2 rounded-2xl border-2 border-dashed border-foreground/15 py-10 text-muted-foreground transition-colors hover:border-primary/40 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              {busy ? (
                <Loader2 className="size-6 animate-spin" />
              ) : (
                <FileUp className="size-6 opacity-70" />
              )}
              <span className="text-sm font-medium">{t("folders.dropFiles")}</span>
              <span className="text-xs">{t("folders.dropFilesHint")}</span>
            </button>
          </TabsContent>
        </Tabs>

        {error && <p className="text-sm text-destructive">{error}</p>}
      </DialogContent>
    </Dialog>
  );
}

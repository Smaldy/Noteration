/** One opened folder: its sub-groups, notes, loose files and child folders.
 *
 *  Groups are colored bands rather than plain headings, so a folder scanned at
 *  a glance reads the same way the Library grid does. A note carries a group
 *  picker instead of drag-and-drop between bands: with the two membership
 *  sources (subject-tagged and manually placed) a drag would have to mean
 *  different things depending on where the card came from, which is exactly the
 *  ambiguity the picker avoids.
 */

import {
  Bookmark,
  FileText,
  FolderInput,
  FolderPlus,
  Image,
  Plus,
  Settings2,
  Sparkles,
  Trash2,
  X,
} from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useParams } from "react-router-dom";

import { BackLink, EmptyState, PageHeader, PageShell } from "@/components/PageShell";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { UploadDialog } from "@/features/upload/UploadDialog";
import { tintSkin } from "@/lib/tints";
import { cn } from "@/lib/utils";
import { useFoldersStore } from "@/stores/folders";
import type { Folder, FolderFile, FolderGroup } from "@/types/folder";
import type { DocumentSummary } from "@/types/library";

import { BookmarkButton } from "@/features/bookmarks/BookmarkButton";

import { AddToFolderDialog } from "./AddToFolderDialog";
import { CopyToFolderDialog } from "./CopyToFolderDialog";
import { FolderDialog } from "./FolderDialog";
import { FolderNoteCard } from "./FolderNoteCard";
import { GenerateNotesDialog } from "./GenerateNotesDialog";
import { GroupDialog } from "./GroupDialog";

/** Select can't hold an empty value, so ungrouped needs a sentinel. */
const UNGROUPED = "none";

export function FolderPage() {
  const { id } = useParams();
  const folderId = Number(id);
  const navigate = useNavigate();
  const { t } = useTranslation();

  const {
    open: contents,
    openStatus,
    error,
    openFolder,
    clearOpen,
    setDocumentGroup,
    setDocumentBookmark,
    removeDocument,
    deleteFile,
  } = useFoldersStore();

  const [addOpen, setAddOpen] = useState(false);
  const [addGroupId, setAddGroupId] = useState<number | null>(null);
  const [editOpen, setEditOpen] = useState(false);
  const [groupOpen, setGroupOpen] = useState(false);
  const [editingGroup, setEditingGroup] = useState<FolderGroup | null>(null);
  const [childOpen, setChildOpen] = useState(false);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [copyOpen, setCopyOpen] = useState(false);
  const [copyDoc, setCopyDoc] = useState<DocumentSummary | null>(null);
  const [generateOpen, setGenerateOpen] = useState(false);
  const [generateFile, setGenerateFile] = useState<FolderFile | null>(null);
  const [starredOnly, setStarredOnly] = useState(false);

  useEffect(() => {
    if (Number.isFinite(folderId)) void openFolder(folderId);
    return clearOpen;
  }, [folderId, openFolder, clearOpen]);

  if (openStatus === "loading" || (openStatus === "idle" && !contents)) {
    return (
      <PageShell width="wide">
        <p className="text-sm text-muted-foreground">{t("folders.loading")}</p>
      </PageShell>
    );
  }

  if (openStatus === "error" || !contents) {
    return (
      <PageShell width="wide">
        <BackLink />
        <EmptyState
          icon={FolderPlus}
          title={t("folders.notFound")}
          description={error ?? t("folders.notFoundDesc")}
        />
      </PageShell>
    );
  }

  const {
    folder,
    groups,
    documents,
    document_groups: placement,
    document_bookmarks: bookmarks,
    files,
    children,
  } = contents;
  const skin = tintSkin(folder.tint);

  const groupOf = (docId: number) => placement[String(docId)] ?? null;
  // The folder's own bookmark filter: a "sub bookmark" scoped to this folder,
  // independent of which folders are starred in the Library.
  const starred = (docId: number) => bookmarks[String(docId)] ?? false;
  const inGroup = (groupId: number | null) =>
    documents.filter(
      (d) => groupOf(d.id) === groupId && (!starredOnly || starred(d.id)),
    );
  // Loose files have nothing to star, so a starred-only view hides them.
  const filesIn = (groupId: number | null) =>
    starredOnly ? [] : files.filter((f) => f.group_id === groupId);

  function openAdd(groupId: number | null) {
    setAddGroupId(groupId);
    setAddOpen(true);
  }

  const noteActions = (doc: DocumentSummary) => (
    <>
      <BookmarkButton
        bookmarked={bookmarks[String(doc.id)] ?? false}
        label={doc.filename}
        size="sm"
        onToggle={(next) => void setDocumentBookmark(folder.id, doc.id, next)}
        className="shrink-0"
      />
      <Button
        variant="ghost"
        size="icon"
        className="size-7 shrink-0 text-muted-foreground hover:text-foreground"
        title={t("folders.copyTo")}
        aria-label={t("folders.copyToAria", { name: doc.filename })}
        onClick={() => {
          setCopyDoc(doc);
          setCopyOpen(true);
        }}
      >
        <FolderInput className="size-3.5" />
      </Button>
      <Select
        value={groupOf(doc.id) == null ? UNGROUPED : String(groupOf(doc.id))}
        onValueChange={(value) =>
          void setDocumentGroup(
            folder.id,
            doc.id,
            value === UNGROUPED ? null : Number(value),
          )
        }
      >
        <SelectTrigger
          className="h-7 flex-1 text-xs"
          aria-label={t("folders.moveToGroup")}
        >
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={UNGROUPED}>{t("folders.ungrouped")}</SelectItem>
          {groups.map((g) => (
            <SelectItem key={g.id} value={String(g.id)}>
              {g.name}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <Button
        variant="ghost"
        size="icon"
        className="size-7 shrink-0 text-muted-foreground hover:text-destructive"
        title={t("folders.removeFromFolder")}
        aria-label={t("folders.removeFromFolderAria", { name: doc.filename })}
        onClick={() => void removeDocument(folder.id, doc.id)}
      >
        <X className="size-3.5" />
      </Button>
    </>
  );

  const ungroupedNotes = inGroup(null);
  const ungroupedFiles = filesIn(null);

  return (
    <PageShell width="wide">
      <BackLink />
      <PageHeader
        className="items-center"
        title={
          <span className={skin.ink} style={skin.inkStyle}>
            {folder.name}
          </span>
        }
        subtitle={
          folder.subject_id != null
            ? t("folders.subjectTagged")
            : t("folders.itemCount", { count: documents.length + files.length })
        }
        actions={
          <>
            <Button
              variant={starredOnly ? "default" : "outline"}
              size="icon"
              aria-pressed={starredOnly}
              title={t("folders.filterStarredAria")}
              aria-label={t("folders.filterStarredAria")}
              onClick={() => setStarredOnly((v) => !v)}
            >
              <Bookmark className={starredOnly ? "fill-current" : undefined} />
            </Button>
            <Button variant="outline" onClick={() => setGroupOpen(true)}>
              <Plus />
              {t("folders.newGroup")}
            </Button>
            <Button
              variant="outline"
              size="icon"
              title={t("folders.editAria", { name: folder.name })}
              aria-label={t("folders.editAria", { name: folder.name })}
              onClick={() => setEditOpen(true)}
            >
              <Settings2 />
            </Button>
            <Button onClick={() => openAdd(null)}>
              <Plus />
              {t("folders.add")}
            </Button>
          </>
        }
      />

      {/* Child folders read as a shelf above the contents. */}
      {(children.length > 0 || folder.parent_id == null) && (
        <section className="mb-6">
          <div className="flex flex-wrap gap-2">
            {children.map((child) => (
              <ChildChip key={child.id} folder={child} />
            ))}
            {folder.parent_id == null && (
              /* Same outline Button as New folder in the Library toolbar: two
                 buttons that create a folder should not look like different
                 kinds of control. */
              <Button
                variant="outline"
                onClick={() => setChildOpen(true)}
                className="h-11 shrink-0 rounded-xl px-4"
              >
                <FolderPlus />
                {t("folders.newSubfolder")}
              </Button>
            )}
          </div>
        </section>
      )}

      {documents.length === 0 && files.length === 0 && (
        <EmptyState
          icon={FolderPlus}
          title={t("folders.emptyTitle")}
          description={t("folders.emptyDesc")}
          action={
            <Button onClick={() => openAdd(null)}>
              <Plus />
              {t("folders.add")}
            </Button>
          }
        />
      )}

      {groups.map((group) => {
        const skinFor = tintSkin(group.tint);
        const notes = inGroup(group.id);
        const groupFiles = filesIn(group.id);
        return (
          <section
            key={group.id}
            style={skinFor.panelStyle}
            className={cn("mb-4 rounded-3xl p-4", skinFor.panel)}
          >
            <header className="mb-3 flex items-center justify-between gap-2">
              <h2
                style={skinFor.inkStyle}
                className={cn(
                  "font-display text-base font-bold tracking-tight",
                  skinFor.ink,
                )}
              >
                {group.name}
              </h2>
              <div className="flex items-center gap-0.5">
                <Button
                  variant="ghost"
                  size="icon"
                  className={cn("size-7", skinFor.ink)}
                  style={skinFor.inkStyle}
                  title={t("folders.addTo", { name: group.name })}
                  aria-label={t("folders.addTo", { name: group.name })}
                  onClick={() => openAdd(group.id)}
                >
                  <Plus className="size-4" />
                </Button>
                <Button
                  variant="ghost"
                  size="icon"
                  className={cn("size-7", skinFor.ink)}
                  style={skinFor.inkStyle}
                  title={t("folders.editGroupAria", { name: group.name })}
                  aria-label={t("folders.editGroupAria", { name: group.name })}
                  onClick={() => {
                    setEditingGroup(group);
                    setGroupOpen(true);
                  }}
                >
                  <Settings2 className="size-4" />
                </Button>
              </div>
            </header>

            {notes.length === 0 && groupFiles.length === 0 ? (
              <p className="py-4 text-center text-sm text-muted-foreground">
                {t("folders.groupEmpty")}
              </p>
            ) : (
              <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
                {notes.map((doc) => (
                  <FolderNoteCard key={doc.id} doc={doc} actions={noteActions(doc)} showStatus />
                ))}
                {groupFiles.map((file) => (
                  <LooseFileCard
                    key={file.id}
                    file={file}
                    onDelete={() => void deleteFile(file.id)}
                    onGenerate={() => {
                      setGenerateFile(file);
                      setGenerateOpen(true);
                    }}
                  />
                ))}
              </div>
            )}
          </section>
        );
      })}

      {(ungroupedNotes.length > 0 || ungroupedFiles.length > 0) && (
        <section>
          {groups.length > 0 && (
            <h2 className="mb-2 text-sm font-semibold text-muted-foreground">
              {t("folders.ungrouped")}
            </h2>
          )}
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {ungroupedNotes.map((doc) => (
              <FolderNoteCard
                key={doc.id}
                doc={doc}
                actions={noteActions(doc)}
                showStatus
                className="border"
              />
            ))}
            {ungroupedFiles.map((file) => (
              <LooseFileCard
                key={file.id}
                file={file}
                onDelete={() => void deleteFile(file.id)}
                onGenerate={() => {
                  setGenerateFile(file);
                  setGenerateOpen(true);
                }}
                className="border"
              />
            ))}
          </div>
        </section>
      )}

      <AddToFolderDialog
        open={addOpen}
        onOpenChange={setAddOpen}
        folder={folder}
        groupId={addGroupId}
        onUploadRequested={() => setUploadOpen(true)}
      />
      <FolderDialog open={editOpen} onOpenChange={setEditOpen} folder={folder} />
      <FolderDialog open={childOpen} onOpenChange={setChildOpen} parentId={folder.id} />
      <GroupDialog
        open={groupOpen}
        onOpenChange={(next) => {
          setGroupOpen(next);
          if (!next) setEditingGroup(null);
        }}
        folderId={folder.id}
        group={editingGroup}
      />
      <CopyToFolderDialog
        open={copyOpen}
        onOpenChange={setCopyOpen}
        doc={copyDoc}
        currentFolderId={folder.id}
      />
      <GenerateNotesDialog
        open={generateOpen}
        onOpenChange={setGenerateOpen}
        file={generateFile}
        defaultSubjectId={folder.subject_id}
      />
      <UploadDialog
        open={uploadOpen}
        onOpenChange={setUploadOpen}
        initialSubjectId={folder.subject_id ?? undefined}
        onUploaded={(documentId) => navigate(`/documents/${documentId}/review`)}
      />
    </PageShell>
  );
}

/** A child folder, shown as a pill on the parent's shelf. */
function ChildChip({ folder }: { folder: Folder }) {
  const navigate = useNavigate();
  const skin = tintSkin(folder.tint);
  return (
    <button
      type="button"
      onClick={() => navigate(`/folders/${folder.id}`)}
      className={cn(
        "inline-flex items-center gap-2 rounded-full px-3 py-1.5 text-sm font-medium transition-transform hover:-translate-y-0.5",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        skin.panel,
        skin.ink,
      )}
    >
      {folder.name}
      <span className="opacity-60 tabular-nums">{folder.item_count}</span>
    </button>
  );
}

/** A PDF or image dropped straight into the folder. Inert: it opens in a new
 *  tab and carries no topic counts, because nothing has been generated yet. */
function LooseFileCard({
  file,
  onDelete,
  onGenerate,
  className,
}: {
  file: FolderFile;
  onDelete: () => void;
  onGenerate: () => void;
  className?: string;
}) {
  const { t } = useTranslation();
  const Icon = file.kind === "image" ? Image : FileText;
  return (
    <div className={cn("rounded-2xl bg-card p-3 shadow-sm", className)}>
      <a
        href={file.url}
        target="_blank"
        rel="noreferrer"
        className="block rounded-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        <p className="flex items-center gap-1.5 text-sm font-semibold">
          <Icon className="size-3.5 shrink-0 text-muted-foreground" />
          <span className="truncate" title={file.filename}>
            {file.filename}
          </span>
        </p>
        <p className="mt-0.5 text-xs text-muted-foreground">
          {t("folders.looseFile")}
        </p>
      </a>
      <div className="mt-2 flex items-center justify-between gap-1">
        {/* Only PDFs can become notes; an image has no text to work from. */}
        {file.kind === "pdf" ? (
          <Button variant="outline" size="sm" className="h-7 text-xs" onClick={onGenerate}>
            <Sparkles className="size-3.5" />
            {t("folders.generate")}
          </Button>
        ) : (
          <span />
        )}
        <Button
          variant="ghost"
          size="icon"
          className="size-7 shrink-0 text-muted-foreground hover:text-destructive"
          title={t("folders.deleteFile")}
          aria-label={t("folders.deleteFileAria", { name: file.filename })}
          onClick={onDelete}
        >
          <Trash2 className="size-3.5" />
        </Button>
      </div>
    </div>
  );
}

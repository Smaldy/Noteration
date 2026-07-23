/** A folder as it appears in the Library grid: a pastel tray holding a preview
 *  of its contents, per the reference layouts.
 *
 *  Populated and empty are deliberately different shapes rather than the same
 *  card with fewer children — an empty folder is a prompt to put something in
 *  it, so it gets a dashed, quiet treatment and a single call to action, while
 *  a full one shows real cards on its tray.
 */

import { useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { FolderOpen, GripVertical, Plus, Settings2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { BookmarkButton } from "@/features/bookmarks/BookmarkButton";
import { tintSkin } from "@/lib/tints";
import { cn } from "@/lib/utils";
import type { Folder } from "@/types/folder";
import type { DocumentSummary } from "@/types/library";

import { FolderNoteCard } from "./FolderNoteCard";

/** How many items the tray previews before collapsing the rest into "+N more". */
const PREVIEW_LIMIT = 3;

export function FolderCard({
  folder,
  preview,
  onAdd,
  onEdit,
  onToggleBookmark,
}: {
  folder: Folder;
  /** First few documents in the folder, for the tray preview. */
  preview: DocumentSummary[];
  onAdd: (folder: Folder) => void;
  onEdit: (folder: Folder) => void;
  onToggleBookmark: (folder: Folder, bookmarked: boolean) => void;
}) {
  const navigate = useNavigate();
  const { t } = useTranslation();
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } =
    useSortable({ id: folder.id });
  const skin = tintSkin(folder.tint);
  const empty = folder.item_count === 0;

  const shown = preview.slice(0, PREVIEW_LIMIT);
  const remaining = folder.item_count - shown.length;

  function open() {
    navigate(`/folders/${folder.id}`);
  }

  return (
    <div
      ref={setNodeRef}
      style={{ transform: CSS.Transform.toString(transform), transition }}
      className={cn("h-full", isDragging && "z-10 opacity-80")}
    >
      <section
        style={empty ? undefined : skin.panelStyle}
        className={cn(
          "flex h-full flex-col gap-3 rounded-3xl p-4 transition-shadow",
          empty
            ? "border-2 border-dashed border-foreground/10 bg-transparent"
            : skin.panel,
          isDragging && "shadow-xl",
        )}
      >
        <header className="flex items-start justify-between gap-2">
          <div className="flex min-w-0 items-center gap-1">
            <button
              type="button"
              aria-label={t("folders.dragToReorder")}
              title={t("folders.dragToReorder")}
              className={cn(
                "-ml-1 shrink-0 cursor-grab touch-none rounded-md p-1 opacity-40 transition-opacity hover:opacity-100",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring active:cursor-grabbing",
                empty ? "text-muted-foreground" : skin.ink,
              )}
              {...attributes}
              {...listeners}
            >
              <GripVertical className="size-4" />
            </button>
            <button
              type="button"
              onClick={open}
              style={empty ? undefined : skin.inkStyle}
              className={cn(
                "min-w-0 truncate rounded-md text-left font-display text-base font-bold tracking-tight",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                empty ? "text-muted-foreground" : skin.ink,
              )}
            >
              {folder.name}
            </button>
          </div>

          <div className="flex shrink-0 items-center gap-0.5">
            <BookmarkButton
              bookmarked={folder.bookmarked}
              label={folder.name}
              onToggle={(next) => onToggleBookmark(folder, next)}
              className={cn(empty ? "text-muted-foreground" : skin.ink, "opacity-70 hover:opacity-100")}
            />
            <TrayButton
              icon={Plus}
              label={t("folders.addTo", { name: folder.name })}
              ink={empty ? undefined : skin.ink}
              inkStyle={empty ? undefined : skin.inkStyle}
              onClick={() => onAdd(folder)}
            />
            <TrayButton
              icon={Settings2}
              label={t("folders.editAria", { name: folder.name })}
              ink={empty ? undefined : skin.ink}
              inkStyle={empty ? undefined : skin.inkStyle}
              onClick={() => onEdit(folder)}
            />
          </div>
        </header>

        {empty ? (
          <button
            type="button"
            onClick={() => onAdd(folder)}
            className="flex flex-1 flex-col items-center justify-center gap-1.5 rounded-2xl py-8 text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <FolderOpen className="size-6 opacity-60" />
            <span className="text-sm font-medium">{t("folders.emptyCta")}</span>
          </button>
        ) : (
          <div className="flex flex-1 flex-col gap-2">
            {shown.map((doc) => (
              <FolderNoteCard key={doc.id} doc={doc} />
            ))}
            <button
              type="button"
              onClick={open}
              style={skin.inkStyle}
              className={cn(
                "mt-auto rounded-lg pt-1 text-left text-xs font-semibold opacity-70 transition-opacity hover:opacity-100",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                skin.ink,
              )}
            >
              {remaining > 0
                ? t("folders.andMore", { count: remaining })
                : t("folders.openFolder")}
            </button>
          </div>
        )}
      </section>
    </div>
  );
}

/** A tinted icon button on the tray header. */
function TrayButton({
  icon: Icon,
  label,
  ink,
  inkStyle,
  onClick,
}: {
  icon: typeof Plus;
  label: string;
  ink?: string;
  inkStyle?: React.CSSProperties;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      title={label}
      aria-label={label}
      style={inkStyle}
      onClick={onClick}
      className={cn(
        "grid size-7 place-items-center rounded-lg opacity-60 transition-all hover:bg-foreground/5 hover:opacity-100",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        ink ?? "text-muted-foreground",
      )}
    >
      <Icon className="size-4" />
    </button>
  );
}


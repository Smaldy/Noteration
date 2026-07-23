/** One note as it sits on a folder tray: white paper on a colored surface.
 *
 *  Titled by **filename**, not subject name — the Library's flat grid titles
 *  cards by subject, which is exactly what made 80 notes unreadable (six cards
 *  all reading "Psychology"). Inside a folder the subject is already the tray,
 *  so the filename is the distinguishing information.
 */

import { AudioLines, FileText } from "lucide-react";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { cn } from "@/lib/utils";
import type { DocumentSummary } from "@/types/library";

import { StatusBadge } from "./StatusBadge";

export function FolderNoteCard({
  doc,
  actions,
  showStatus = false,
  className,
}: {
  doc: DocumentSummary;
  /** Row of controls rendered under the card (group picker, remove). */
  actions?: ReactNode;
  showStatus?: boolean;
  className?: string;
}) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const Icon = doc.source_type === "audio" ? AudioLines : FileText;

  // Not-yet-confirmed uploads go to structure review; confirmed ones to study.
  const destination =
    doc.status === "uploaded"
      ? `/documents/${doc.id}/review`
      : `/documents/${doc.id}/study`;

  return (
    <div className={cn("rounded-2xl bg-card p-3 shadow-sm", className)}>
      <button
        type="button"
        onClick={() => navigate(destination)}
        className="w-full rounded-lg text-left transition-transform hover:-translate-y-0.5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        <p className="flex items-center gap-1.5 text-sm font-semibold">
          <Icon className="size-3.5 shrink-0 text-muted-foreground" />
          <span className="truncate" title={doc.filename}>
            {doc.filename}
          </span>
        </p>
        <p className="mt-0.5 flex items-center gap-2 text-xs text-muted-foreground">
          <span>
            {doc.topics_total === 0
              ? t("library.card.noTopicsYet")
              : t("library.card.topicsReady", {
                  ready: doc.topics_ready,
                  total: doc.topics_total,
                })}
          </span>
          {showStatus && <StatusBadge status={doc.status} />}
        </p>
      </button>
      {actions && <div className="mt-2 flex items-center gap-1">{actions}</div>}
    </div>
  );
}

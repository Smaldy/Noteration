/** Shared page chrome. Every routed page composes these instead of
 *  hand-rolling its own container, back link, title block, section labels and
 *  empty states — consistency is structural, not copy-pasted:
 *
 *    <PageShell width="narrow">
 *      <BackLink />
 *      <PageHeader icon={<Bookmark …/>} title={…} subtitle={…} actions={…} />
 *      <SectionLabel>{…}</SectionLabel>
 *      …
 *    </PageShell>
 */

import { ArrowLeft, type LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { cn } from "@/lib/utils";

/** One container per page: centered, fixed side padding, entrance rise.
 *  Widths are semantic — reading columns are narrow, grids/boards go wider. */
const WIDTHS = {
  narrow: "max-w-3xl", // single reading column (queue, bookmarks, review)
  default: "max-w-5xl", // card grids (library, exam prep)
  wide: "max-w-6xl", // sidebar + content (study)
  xl: "max-w-7xl", // dense boards (duplicator)
} as const;

export function PageShell({
  width = "default",
  className,
  children,
}: {
  width?: keyof typeof WIDTHS;
  className?: string;
  children: ReactNode;
}) {
  return (
    <div className={cn("mx-auto animate-rise px-6 py-10", WIDTHS[width], className)}>
      {children}
    </div>
  );
}

/** The quiet "← Library" breadcrumb every non-home page leads with.
 *  `sector` feeds the arcade's location tracking (data-arcade-sector).
 *  Pass `onClick` to override the destination (e.g. history back). */
export function BackLink({
  to = "/",
  label,
  sector = "library",
  className,
  onClick,
}: {
  to?: string;
  label?: string;
  sector?: string;
  className?: string;
  onClick?: () => void;
}) {
  const navigate = useNavigate();
  const { t } = useTranslation();
  return (
    <button
      type="button"
      data-arcade-sector={sector}
      onClick={onClick ?? (() => navigate(to))}
      className={cn(
        "mb-5 inline-flex items-center gap-1.5 rounded-md text-sm font-medium text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background",
        className,
      )}
    >
      <ArrowLeft className="size-4" />
      {label ?? t("common.library")}
    </button>
  );
}

/** Title block: icon + h1 + one-line subtitle, with an optional right-aligned
 *  actions slot. The icon slot is a ReactNode so pages keep control of the
 *  glyph treatment (filled, tinted…) while position and rhythm stay fixed. */
export function PageHeader({
  icon,
  title,
  subtitle,
  actions,
  className,
}: {
  icon?: ReactNode;
  title: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("mb-8 flex flex-wrap items-start justify-between gap-x-4 gap-y-3", className)}>
      <div className="min-w-0">
        <h1 className="flex items-center gap-2.5 text-3xl font-bold tracking-tight">
          {icon}
          <span className="min-w-0 truncate">{title}</span>
        </h1>
        {subtitle && (
          <p className="mt-1 text-sm text-muted-foreground">{subtitle}</p>
        )}
      </div>
      {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
    </div>
  );
}

/** Eyebrow heading above a page section — small caps in the accent color. */
export function SectionLabel({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <h2
      className={cn(
        "font-display mb-3 text-xs font-bold uppercase tracking-[0.12em] text-primary",
        className,
      )}
    >
      {children}
    </h2>
  );
}

/** Empty state: an invitation to act, not a dead end — dashed panel with an
 *  icon, a plain-verb title, one line of direction, and an optional action. */
export function EmptyState({
  icon: Icon,
  title,
  description,
  action,
  className,
}: {
  icon: LucideIcon;
  title: ReactNode;
  description?: ReactNode;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center rounded-2xl border border-dashed px-6 py-20 text-center",
        className,
      )}
    >
      <Icon className="mb-4 size-10 text-muted-foreground" aria-hidden />
      <h2 className="text-lg font-medium">{title}</h2>
      {description && (
        <p className="mt-1 max-w-sm text-sm text-muted-foreground">{description}</p>
      )}
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}

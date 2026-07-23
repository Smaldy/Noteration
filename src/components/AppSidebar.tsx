/** The persistent left nav.
 *
 *  Replaces the per-page header buttons that used to live on LibraryPage, so
 *  every route now reaches every destination. It is `fixed`, so routed content
 *  is inset by AppSidebar.WIDTH (see App.tsx) rather than sharing a flex row —
 *  that keeps the page-transition animation from reflowing the nav on every
 *  navigation.
 *
 *  `data-arcade-sector` must stay on these buttons: the arcade minigame finds
 *  its real-nav targets by that attribute (see arcade/game/types.ts ArenaId),
 *  lighting a sector when a bomb is planted there and locking sectors that
 *  haven't unlocked yet. The five sector ids are library/exam/calendar/queue/
 *  settings; other entries simply have no sector.
 */

import {
  CalendarDays,
  Copy,
  GraduationCap,
  LibraryBig,
  ListChecks,
  Lock,
  Settings,
  type LucideIcon,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { useLocation, useNavigate } from "react-router-dom";

import { JoystickButton } from "@/features/arcade/JoystickButton";
import { cn } from "@/lib/utils";
import { useArcadeStore } from "@/stores/arcade";

/** Kept in sync with the content inset in App.tsx. Icon-only rail below `lg`,
 *  full labels above it — a drawer would be a third layout to maintain for a
 *  local-first desktop app. */
export const SIDEBAR_WIDTH = "w-[4.5rem] lg:w-60";

interface NavEntry {
  to: string;
  icon: LucideIcon;
  label: string;
  sector?: string;
}

export function AppSidebar() {
  const navigate = useNavigate();
  const location = useLocation();
  const { t } = useTranslation();

  const bombSectors = useArcadeStore((s) => s.bombSectors);
  const unlockedSectors = useArcadeStore((s) => s.unlockedSectors);
  const playing = useArcadeStore((s) => s.phase) === "playing";

  const main: NavEntry[] = [
    { to: "/", icon: LibraryBig, label: t("nav.library"), sector: "library" },
  ];
  const study: NavEntry[] = [
    { to: "/exam", icon: GraduationCap, label: t("nav.examPrep"), sector: "exam" },
    { to: "/queue", icon: ListChecks, label: t("nav.queue"), sector: "queue" },
    { to: "/calendar", icon: CalendarDays, label: t("nav.calendar"), sector: "calendar" },
    { to: "/duplicator", icon: Copy, label: t("nav.duplicator") },
  ];

  function renderEntry({ to, icon: Icon, label, sector }: NavEntry) {
    // "/" would prefix-match every route, so home is an exact comparison.
    const active = to === "/" ? location.pathname === "/" : location.pathname.startsWith(to);
    const bombed = sector != null && bombSectors.includes(sector);
    const locked = playing && sector != null && !unlockedSectors.includes(sector);

    return (
      <button
        key={to}
        type="button"
        data-arcade-sector={sector}
        aria-current={active ? "page" : undefined}
        title={label}
        onClick={() => navigate(to)}
        className={cn(
          "relative flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition-colors",
          "justify-center lg:justify-start",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
          active
            ? "bg-primary-soft text-primary-soft-foreground"
            : "text-muted-foreground hover:bg-muted hover:text-foreground",
          bombed && "arcade-bomb-alert",
          locked && "opacity-50",
        )}
      >
        <Icon className="size-[1.15rem] shrink-0" />
        <span className="hidden lg:inline">{label}</span>
        {locked && (
          <Lock className="absolute right-1 top-1 size-3.5 text-destructive/70 lg:right-2" />
        )}
      </button>
    );
  }

  return (
    <aside
      className={cn(
        "fixed inset-y-0 left-0 z-30 flex flex-col gap-1 bg-card px-3 py-5 print:hidden",
        SIDEBAR_WIDTH,
      )}
    >
      <div className="mb-6 flex items-center gap-2.5 px-1 lg:px-2">
        <span className="grid size-9 shrink-0 place-items-center rounded-xl bg-primary text-primary-foreground">
          <LibraryBig className="size-[1.15rem]" />
        </span>
        <span className="hidden font-display text-lg font-bold tracking-tight lg:inline">
          Noteration
        </span>
      </div>

      <SidebarLabel>{t("nav.sectionMain")}</SidebarLabel>
      {main.map(renderEntry)}

      <SidebarLabel className="mt-5">{t("nav.sectionStudy")}</SidebarLabel>
      {study.map(renderEntry)}

      {/* Settings sits apart at the foot, as in the reference layouts. The
          arcade joystick shares the row: it used to be fixed to this same
          corner and ended up underneath the Settings button. */}
      <div className="mt-auto flex items-center gap-1 pt-5">
        <div className="min-w-0 flex-1">
          {renderEntry({
            to: "/settings",
            icon: Settings,
            label: t("nav.settings"),
            sector: "settings",
          })}
        </div>
        <JoystickButton />
      </div>
    </aside>
  );
}

/** Hidden on the icon rail, where a text heading would have nothing to label. */
function SidebarLabel({ className, children }: { className?: string; children: string }) {
  return (
    <p
      className={cn(
        "mb-1 hidden px-3 text-[0.7rem] font-semibold uppercase tracking-wider text-muted-foreground/70 lg:block",
        className,
      )}
    >
      {children}
    </p>
  );
}

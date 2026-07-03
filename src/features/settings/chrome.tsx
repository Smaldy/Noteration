/** Settings page chrome: the header/footer shell, the scroll-spy section nav,
 *  and the sticky save/discard action bar. */

import {
  closestCenter,
  DndContext,
  type DragEndEvent,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
} from "@dnd-kit/core";
import {
  arrayMove,
  SortableContext,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { AnimatePresence, motion } from "framer-motion";
import { Check, Eye, EyeOff, GripVertical, RotateCcw } from "lucide-react";
import { type ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { BackLink } from "@/components/PageShell";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

import { SECTIONS } from "./form";

export function Shell({
  children,
  footer,
  onBack,
}: {
  children: ReactNode;
  footer?: ReactNode;
  onBack: () => void;
}) {
  const { t } = useTranslation();
  return (
    <div className="flex min-h-screen flex-col">
      {/* py-5 centers the header row on the fixed provider badge (top-4). */}
      <header className="glass sticky top-0 z-20 border-b">
        <div className="mx-auto flex max-w-5xl items-center justify-between px-6 py-5">
          <BackLink className="mb-0" onClick={onBack} />
          <span className="font-display text-sm font-semibold tracking-tight text-muted-foreground">
            {t("settings.headerTag")}
          </span>
        </div>
      </header>
      <main className="flex-1">
        <div className="mx-auto max-w-5xl px-6 py-10">{children}</div>
      </main>
      {footer}
    </div>
  );
}

/** Sticky scroll-spy navigation. A single sliding pill (layoutId) tracks the
 *  active section as you scroll. Each row also carries a drag handle (reorder
 *  the section cards) and an eye toggle (hide a section you're done with);
 *  both fade in on hover so the resting state stays quiet. */
export function SectionNav({
  order,
  hidden,
  active,
  onJump,
  onToggleHidden,
  onReorder,
}: {
  order: string[];
  hidden: string[];
  active: string;
  onJump: (id: string) => void;
  onToggleHidden: (id: string) => void;
  onReorder: (ids: string[]) => void;
}) {
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );

  function handleDragEnd(event: DragEndEvent) {
    const { active: dragged, over } = event;
    if (!over || dragged.id === over.id) return;
    const oldIndex = order.indexOf(String(dragged.id));
    const newIndex = order.indexOf(String(over.id));
    if (oldIndex < 0 || newIndex < 0) return;
    onReorder(arrayMove(order, oldIndex, newIndex));
  }

  return (
    <nav className="hidden lg:block">
      <div className="sticky top-24 space-y-0.5">
        <DndContext
          sensors={sensors}
          collisionDetection={closestCenter}
          onDragEnd={handleDragEnd}
        >
          <SortableContext items={order} strategy={verticalListSortingStrategy}>
            {order.map((id) => {
              const section = SECTIONS.find((s) => s.id === id);
              if (!section) return null;
              return (
                <NavRow
                  key={id}
                  section={section}
                  on={active === id}
                  sectionHidden={hidden.includes(id)}
                  onJump={() => onJump(id)}
                  onToggleHidden={() => onToggleHidden(id)}
                />
              );
            })}
          </SortableContext>
        </DndContext>
      </div>
    </nav>
  );
}

function NavRow({
  section,
  on,
  sectionHidden,
  onJump,
  onToggleHidden,
}: {
  section: (typeof SECTIONS)[number];
  on: boolean;
  sectionHidden: boolean;
  onJump: () => void;
  onToggleHidden: () => void;
}) {
  const { t } = useTranslation();
  const Icon = section.icon;
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } =
    useSortable({ id: section.id });
  const eyeLabel = t(sectionHidden ? "settings.nav.showSection" : "settings.nav.hideSection");

  return (
    <div
      ref={setNodeRef}
      style={{ transform: CSS.Transform.toString(transform), transition }}
      className={cn(
        "group relative flex w-full items-center rounded-lg pr-1",
        isDragging && "z-10",
        on ? "text-foreground" : "text-muted-foreground",
      )}
    >
      {on && (
        <motion.span
          layoutId="settings-nav-active"
          className="absolute inset-0 rounded-lg bg-secondary"
          transition={{ type: "spring", stiffness: 420, damping: 34 }}
        />
      )}
      <button
        type="button"
        {...attributes}
        {...listeners}
        title={t("settings.nav.reorder")}
        aria-label={t("settings.nav.reorder")}
        className="relative z-10 flex h-8 w-5 shrink-0 cursor-grab touch-none items-center justify-center rounded-md text-muted-foreground/60 opacity-0 transition-opacity hover:text-foreground focus-visible:opacity-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring group-hover:opacity-100 active:cursor-grabbing"
      >
        <GripVertical className="size-4" />
      </button>
      <button
        type="button"
        onClick={onJump}
        className={cn(
          "relative z-10 flex min-w-0 flex-1 items-center gap-2.5 rounded-lg py-2 pr-1 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
          sectionHidden && "opacity-50",
          !on && "hover:text-foreground",
        )}
      >
        <Icon
          className={cn(
            "size-4 shrink-0 transition-colors",
            on ? "text-primary" : "text-muted-foreground group-hover:text-foreground",
          )}
        />
        <span className="truncate">{t(section.labelKey)}</span>
      </button>
      <button
        type="button"
        onClick={onToggleHidden}
        title={eyeLabel}
        aria-label={eyeLabel}
        aria-pressed={sectionHidden}
        className={cn(
          "relative z-10 flex size-7 shrink-0 items-center justify-center rounded-md text-muted-foreground/60 transition-all hover:text-foreground focus-visible:opacity-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
          sectionHidden ? "opacity-100" : "opacity-0 group-hover:opacity-100",
        )}
      >
        {sectionHidden ? <EyeOff className="size-3.5" /> : <Eye className="size-3.5" />}
      </button>
    </div>
  );
}

export function ActionBar({
  dirty,
  saving,
  saved,
  saveError,
  onSave,
  onDiscard,
}: {
  dirty: boolean;
  saving: boolean;
  saved: boolean;
  saveError: string | null;
  onSave: () => void;
  onDiscard: () => void;
}) {
  const { t } = useTranslation();
  return (
    <footer className="glass sticky bottom-0 z-20 border-t">
      <div className="mx-auto flex max-w-5xl items-center justify-between gap-3 px-6 py-4">
        <div className="min-h-5 text-sm">
          <AnimatePresence mode="wait" initial={false}>
            {saveError ? (
              <motion.span
                key="err"
                initial={{ opacity: 0, y: 4 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -4 }}
                className="text-destructive"
              >
                {saveError}
              </motion.span>
            ) : saved ? (
              <motion.span
                key="ok"
                initial={{ opacity: 0, y: 4 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -4 }}
                className="inline-flex items-center gap-1.5 font-medium text-success"
              >
                <Check className="size-4" />
                {t("settings.save.saved")}
              </motion.span>
            ) : dirty ? (
              <motion.span
                key="dirty"
                initial={{ opacity: 0, y: 4 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -4 }}
                className="inline-flex items-center gap-1.5 text-muted-foreground"
              >
                <span className="size-1.5 rounded-full bg-warning" />
                {t("settings.save.unsaved")}
              </motion.span>
            ) : (
              <span className="text-muted-foreground/60">
                {t("settings.save.allSaved")}
              </span>
            )}
          </AnimatePresence>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="ghost"
            size="sm"
            onClick={onDiscard}
            disabled={!dirty || saving}
          >
            <RotateCcw />
            {t("settings.save.discard")}
          </Button>
          <Button onClick={onSave} disabled={!dirty || saving}>
            {saving ? t("settings.save.saving") : t("settings.save.save")}
          </Button>
        </div>
      </div>
    </footer>
  );
}

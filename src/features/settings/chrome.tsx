/** Settings page chrome: the header/footer shell, the scroll-spy section nav,
 *  and the sticky save/discard action bar. */

import { AnimatePresence, motion } from "framer-motion";
import { Check, RotateCcw } from "lucide-react";
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
      <header className="glass sticky top-0 z-20 border-b">
        <div className="mx-auto flex max-w-4xl items-center justify-between px-6 py-3.5">
          <BackLink className="mb-0" onClick={onBack} />
          <span className="font-display text-sm font-semibold tracking-tight text-muted-foreground">
            {t("settings.headerTag")}
          </span>
        </div>
      </header>
      <main className="flex-1">
        <div className="mx-auto max-w-4xl px-6 py-10">{children}</div>
      </main>
      {footer}
    </div>
  );
}

/** Sticky scroll-spy navigation. A single sliding pill (layoutId) tracks the
 *  active section as you scroll, which reads far more refined than per-item
 *  background toggles. */
export function SectionNav({
  active,
  onJump,
}: {
  active: string;
  onJump: (id: string) => void;
}) {
  const { t } = useTranslation();
  return (
    <nav className="hidden lg:block">
      <div className="sticky top-24 space-y-0.5">
        {SECTIONS.map((s) => {
          const Icon = s.icon;
          const on = active === s.id;
          return (
            <button
              key={s.id}
              type="button"
              onClick={() => onJump(s.id)}
              className={cn(
                "group relative flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                on
                  ? "text-foreground"
                  : "text-muted-foreground hover:text-foreground",
              )}
            >
              {on && (
                <motion.span
                  layoutId="settings-nav-active"
                  className="absolute inset-0 rounded-lg bg-secondary"
                  transition={{ type: "spring", stiffness: 420, damping: 34 }}
                />
              )}
              <Icon
                className={cn(
                  "relative z-10 size-4 transition-colors",
                  on ? "text-primary" : "text-muted-foreground group-hover:text-foreground",
                )}
              />
              <span className="relative z-10">{t(s.labelKey)}</span>
            </button>
          );
        })}
      </div>
    </nav>
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
      <div className="mx-auto flex max-w-4xl items-center justify-between gap-3 px-6 py-4">
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

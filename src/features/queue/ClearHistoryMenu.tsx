import { AnimatePresence, motion } from "framer-motion";
import { Check, ChevronDown, Clock3, Loader2, Sun, Trash2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { cn } from "@/lib/utils";
import { useLanesStore, type HistoryClearScope } from "@/stores/lanes";

interface ScopeOption {
  scope: HistoryClearScope;
  label: string;
  hint: string;
  icon: typeof Clock3;
  /** "all" wipes the whole log, so it gets a destructive look + a confirm step. */
  destructive?: boolean;
}

const OPTIONS: ScopeOption[] = [
  { scope: "hour", label: "Last hour", hint: "Events from the past 60 minutes", icon: Clock3 },
  { scope: "day", label: "Last 24 hours", hint: "Everything since yesterday", icon: Sun },
  {
    scope: "all",
    label: "Everything",
    hint: "Wipe the entire log",
    icon: Trash2,
    destructive: true,
  },
];

/**
 * "Clear history" control for the Processing → History tab: a small button that
 * opens an animated menu offering last-hour / last-day / all scopes. The full
 * wipe asks for a second click to confirm; the timed scopes act immediately.
 */
export function ClearHistoryMenu() {
  const clearHistory = useLanesStore((s) => s.clearHistory);
  const clearing = useLanesStore((s) => s.clearing);

  const [open, setOpen] = useState(false);
  const [armed, setArmed] = useState<HistoryClearScope | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  // Close on outside click or Escape; reset any pending confirm when closing.
  useEffect(() => {
    if (!open) {
      setArmed(null);
      return;
    }
    const onPointer = (e: PointerEvent) => {
      if (!containerRef.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("pointerdown", onPointer);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onPointer);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const choose = async (option: ScopeOption) => {
    if (option.destructive && armed !== option.scope) {
      setArmed(option.scope); // first click arms, second confirms
      return;
    }
    await clearHistory(option.scope);
    setOpen(false);
  };

  return (
    <div ref={containerRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        disabled={clearing}
        className={cn(
          "inline-flex items-center gap-1.5 rounded-lg border border-border/70 bg-background/60 px-2.5 py-1.5",
          "text-xs font-medium text-muted-foreground shadow-xs transition-all duration-150",
          "hover:border-destructive/40 hover:bg-destructive/5 hover:text-destructive",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background",
          "active:scale-[0.97] disabled:pointer-events-none disabled:opacity-50",
          open && "border-destructive/40 bg-destructive/5 text-destructive",
        )}
        aria-haspopup="menu"
        aria-expanded={open}
      >
        {clearing ? (
          <Loader2 className="size-3.5 animate-spin" />
        ) : (
          <Trash2 className="size-3.5" />
        )}
        Clear
        <ChevronDown
          className={cn("size-3.5 transition-transform duration-200", open && "rotate-180")}
        />
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            role="menu"
            initial={{ opacity: 0, y: -6, scale: 0.97 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -6, scale: 0.97 }}
            transition={{ duration: 0.16, ease: [0.16, 1, 0.3, 1] }}
            className={cn(
              "absolute right-0 z-20 mt-2 w-60 origin-top-right overflow-hidden rounded-xl",
              "border border-border/70 bg-card/95 p-1 shadow-lg shadow-black/5 backdrop-blur-sm",
            )}
          >
            <p className="px-2.5 pb-1 pt-1.5 text-[0.65rem] font-semibold uppercase tracking-wider text-muted-foreground/70">
              Clear history
            </p>
            {OPTIONS.map((option) => {
              const Icon = option.icon;
              const isArmed = armed === option.scope;
              return (
                <button
                  key={option.scope}
                  type="button"
                  role="menuitem"
                  disabled={clearing}
                  onClick={() => void choose(option)}
                  className={cn(
                    "group flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left transition-colors duration-150",
                    "focus-visible:outline-none disabled:pointer-events-none disabled:opacity-50",
                    option.destructive
                      ? "hover:bg-destructive/10 focus-visible:bg-destructive/10"
                      : "hover:bg-accent focus-visible:bg-accent",
                    isArmed && "bg-destructive/10",
                  )}
                >
                  <span
                    className={cn(
                      "flex size-7 shrink-0 items-center justify-center rounded-md transition-colors",
                      option.destructive
                        ? "bg-destructive/10 text-destructive"
                        : "bg-muted text-muted-foreground group-hover:text-foreground",
                    )}
                  >
                    {isArmed ? <Check className="size-3.5" /> : <Icon className="size-3.5" />}
                  </span>
                  <span className="min-w-0 flex-1">
                    <span
                      className={cn(
                        "block text-sm font-medium",
                        option.destructive ? "text-destructive" : "text-foreground",
                      )}
                    >
                      {isArmed ? "Click again to confirm" : option.label}
                    </span>
                    <span className="block truncate text-xs text-muted-foreground">
                      {option.hint}
                    </span>
                  </span>
                </button>
              );
            })}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { cn } from "@/lib/utils";
import { providerInfo } from "@/lib/providers";
import { usePolling } from "@/lib/usePolling";
import { useLanesStore } from "@/stores/lanes";

const POLL_MS = 10_000;

/**
 * Persistent active-provider badge. Always visible in the top-right
 * strip; polls lane status every ~10s and shows the active provider tier-colored —
 * green free · amber local · red paid — so the free-first mission stays in view. On
 * a mid-session failover the label swaps and the badge briefly pulses.
 */
export function ProviderBadge() {
  const navigate = useNavigate();
  const { t } = useTranslation();
  const status = useLanesStore((s) => s.status);
  const fetchLanes = useLanesStore((s) => s.fetchLanes);

  usePolling(fetchLanes, POLL_MS);

  const active = status?.active_provider ?? null;
  const info = providerInfo(active);
  // "Idle" is the only provider label that is UI copy (not a proper name).
  const label = active ? info.label : t("queue.idle");

  // Pulse when the active provider actually changes (a failover/switch).
  // `undefined` = not yet seen, so the very first load doesn't pulse.
  const [pulse, setPulse] = useState(false);
  const prev = useRef<string | null | undefined>(undefined);
  useEffect(() => {
    const changed = prev.current !== undefined && prev.current !== active;
    prev.current = active;
    if (!changed) return;
    setPulse(true);
    const t = setTimeout(() => setPulse(false), 1100);
    return () => clearTimeout(t);
  }, [active]);

  return (
    <motion.button
      type="button"
      onClick={() => navigate("/queue")}
      title={t("queue.providerBadgeTitle")}
      initial={{ opacity: 0, y: -8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: [0.22, 1, 0.36, 1] }}
      className={cn(
        "fixed right-4 top-4 z-40 print:hidden",
        "inline-flex items-center gap-2 rounded-full border px-3 py-1.5",
        "bg-card/80 text-xs font-medium shadow-sm backdrop-blur-md",
        "transition-colors hover:bg-card",
        info.border,
      )}
    >
      <span className="relative flex size-2.5 items-center justify-center">
        {pulse && (
          <motion.span
            className={cn("absolute inline-flex size-2.5 rounded-full", info.dot)}
            initial={{ scale: 1, opacity: 0.7 }}
            animate={{ scale: 3, opacity: 0 }}
            transition={{ duration: 1, ease: "easeOut", repeat: 2 }}
          />
        )}
        <span className={cn("relative inline-flex size-2.5 rounded-full", info.dot)} />
      </span>
      <AnimatePresence mode="wait">
        <motion.span
          key={label}
          initial={{ opacity: 0, y: 4 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -4 }}
          transition={{ duration: 0.18 }}
          className={cn("tracking-tight", info.text)}
        >
          {label}
        </motion.span>
      </AnimatePresence>
    </motion.button>
  );
}

import { motion } from "framer-motion";
import { Joystick } from "lucide-react";

import { useArcadeStore } from "@/stores/arcade";

/**
 * The arcade entry point: a joystick button fixed at the bottom-left, styled to
 * read as a playful "secret" control distinct from the real app chrome. Clicking
 * it opens the Arcade Machine overlay. Hidden while the game/overlay is active.
 */
export function JoystickButton() {
  const open = useArcadeStore((s) => s.openOverlay);
  const overlayOpen = useArcadeStore((s) => s.overlayOpen);
  const phase = useArcadeStore((s) => s.phase);
  const coins = useArcadeStore((s) => s.state?.coins ?? null);

  if (overlayOpen || phase !== "off") return null;

  return (
    <motion.button
      type="button"
      onClick={open}
      aria-label="Open the arcade"
      title="Arcade"
      className="group fixed bottom-4 left-4 z-[60] grid size-12 place-items-center rounded-2xl border border-fuchsia-400/30 bg-gradient-to-br from-indigo-900 to-violet-950 text-fuchsia-200 shadow-[0_8px_30px_-6px_rgba(150,90,255,0.55)] outline-none"
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      whileHover={{ scale: 1.1, rotate: -6 }}
      whileTap={{ scale: 0.92 }}
      transition={{ type: "spring", stiffness: 320, damping: 18 }}
    >
      <Joystick className="size-6 transition-transform group-hover:-translate-y-0.5" />
      {coins != null && coins > 0 && (
        <span className="absolute -right-1.5 -top-1.5 min-w-5 rounded-full bg-amber-400 px-1 text-center text-[10px] font-bold leading-4 text-amber-950 shadow">
          {coins > 99 ? "99+" : coins}
        </span>
      )}
    </motion.button>
  );
}

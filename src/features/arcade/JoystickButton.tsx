import { motion } from "framer-motion";
import { Joystick } from "lucide-react";

import { useArcadeStore } from "@/stores/arcade";

/**
 * The arcade entry point: a small, muted joystick icon. It stays quiet (dim, no
 * fill/glow) so it blends with the app chrome, and only gains presence on
 * hover/focus. Clicking it opens the Arcade Machine overlay. Hidden while the
 * game/overlay is active.
 *
 * Rendered inline in the sidebar footer rather than fixed to the bottom-left
 * corner, which the sidebar's Settings button now occupies.
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
      className="group relative grid size-9 shrink-0 place-items-center rounded-lg text-muted-foreground/40 opacity-60 outline-none transition-[color,opacity,background-color] duration-200 hover:bg-muted/60 hover:text-foreground hover:opacity-100 focus-visible:bg-muted/60 focus-visible:text-foreground focus-visible:opacity-100"
      initial={{ opacity: 0 }}
      animate={{ opacity: 0.6 }}
      whileTap={{ scale: 0.94 }}
      transition={{ duration: 0.3 }}
    >
      <Joystick className="size-[18px]" />
      {coins != null && coins > 0 && (
        // Coin count is only revealed on hover/focus so it doesn't draw the eye.
        <span className="absolute -right-1 -top-1 min-w-4 rounded-full bg-muted px-1 text-center text-[9px] font-medium leading-4 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100 group-focus-visible:opacity-100">
          {coins > 99 ? "99+" : coins}
        </span>
      )}
    </motion.button>
  );
}

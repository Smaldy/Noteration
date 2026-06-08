import { motion } from "framer-motion";

/**
 * A casino-style pull lever mounted on the cabinet's right side: a chrome rod
 * with a red ball knob that pivots at its base. Clicking yanks it down and lets
 * it spring back; the parent drives the `pulled` state and the start sequence.
 */
const REST = -6; // degrees, resting up-and-slightly-back
const PULL = 84; // degrees, yanked down toward the player

export function ArcadeLever({
  pulled,
  disabled,
  onPull,
}: {
  pulled: boolean;
  disabled?: boolean;
  onPull: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onPull}
      disabled={disabled}
      aria-label="Pull the lever to start"
      className={`relative block h-[120px] w-[64px] ${disabled ? "cursor-not-allowed opacity-50" : "cursor-pointer"}`}
    >
      {/* side mount bracket */}
      <span className="arcade-lever-mount absolute bottom-0 left-1/2 -translate-x-1/2" />

      {/* pivoting arm (rod + knob), hinged at the mount */}
      <motion.span
        className="absolute bottom-3 left-1/2 flex flex-col items-center"
        style={{ transformOrigin: "bottom center", x: "-50%" }}
        initial={{ rotate: REST }}
        animate={{ rotate: pulled ? [REST, PULL, REST] : REST }}
        transition={{ duration: 0.62, ease: [0.34, 1.56, 0.64, 1], times: [0, 0.45, 1] }}
      >
        <span className="arcade-lever-knob" />
        <span className="arcade-lever-rod" style={{ height: 70 }} />
      </motion.span>

      {/* pivot cap over the hinge */}
      <span className="arcade-lever-pivot absolute bottom-2 left-1/2 -translate-x-1/2" />
    </button>
  );
}

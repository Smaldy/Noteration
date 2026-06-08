import { motion } from "framer-motion";

/**
 * Slot-machine pull lever (profile), mounted on the right of the screen housing:
 * a metal base, a chrome stick, and a big red ball. Clicking yanks it down and
 * lets it spring back; the parent drives `pulled` and the start sequence.
 */
const REST = -35; // degrees — stick resting up
const PULL = 26; // degrees — yanked down

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
      className={`lever-assembly ${disabled ? "cursor-not-allowed opacity-50" : "cursor-pointer"}`}
    >
      <span className="lever-base block" />
      <motion.span
        className="lever-arm block"
        style={{ transformOrigin: "left center", y: "-50%" }}
        initial={{ rotate: REST }}
        animate={{ rotate: pulled ? [REST, PULL, REST] : REST }}
        transition={{ duration: 0.66, ease: [0.34, 1.56, 0.64, 1], times: [0, 0.42, 1] }}
      >
        <span className="lever-stick block" />
        <span className="lever-ball" />
      </motion.span>
    </button>
  );
}

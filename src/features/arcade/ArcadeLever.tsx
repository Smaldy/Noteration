import { motion } from "framer-motion";

/**
 * A slot-machine pull lever drawn in profile, mounted on the cabinet's right
 * side: a chrome hub bolted to the chassis, a thick chrome shaft angling up to a
 * big red ball. Clicking yanks it down and lets it spring back; the parent drives
 * the `pulled` state and the start sequence.
 */
const REST = 30; // degrees clockwise — shaft resting up-and-to-the-right
const PULL = 114; // degrees — yanked down/forward

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
      className={`relative block ${disabled ? "cursor-not-allowed opacity-50" : "cursor-pointer"}`}
      style={{ width: 130, height: 196 }}
    >
      {/* pivoting arm (shaft + ball), hinged at the hub */}
      <motion.span
        className="absolute bottom-[26px] left-1/2 flex flex-col items-center"
        style={{ transformOrigin: "bottom center", x: "-50%" }}
        initial={{ rotate: REST }}
        animate={{ rotate: pulled ? [REST, PULL, REST] : REST }}
        transition={{ duration: 0.66, ease: [0.34, 1.56, 0.64, 1], times: [0, 0.42, 1] }}
      >
        <span className="arcade-lever-knob" />
        <span className="arcade-lever-shaft" style={{ height: 122, marginTop: -6 }} />
      </motion.span>

      {/* chrome hub bolted to the cabinet side */}
      <span className="arcade-lever-hub absolute bottom-2 left-1/2 grid -translate-x-1/2 place-items-center">
        <span className="arcade-lever-hub-bolt" />
      </span>
    </button>
  );
}

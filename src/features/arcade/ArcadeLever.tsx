/** The ball-top start lever, sitting on the control deck (outside the screen).
 *  Pulling it tilts the arm forward; the parent drives the `pulled` state and
 *  fires the coin-insert + run-start sequence. */
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
      className={`arcade-lever ${pulled ? "arcade-lever-pulled" : ""} ${
        disabled ? "cursor-not-allowed opacity-50" : "cursor-pointer"
      }`}
    >
      <span className="arcade-lever-base" />
      <span className="arcade-lever-arm">
        <span className="arcade-lever-ball" />
        <span className="arcade-lever-shaft" />
      </span>
    </button>
  );
}

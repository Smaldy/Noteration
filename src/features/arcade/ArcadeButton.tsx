import type { ReactNode } from "react";

/** A chunky, semi-3-D arcade button (the kind that sits proud of the deck and
 *  physically sinks when pressed). Used for the directional controls. */
export function ArcadeButton({
  children,
  onClick,
  disabled,
  variant = "red",
  ariaLabel,
  pressed = false,
}: {
  children: ReactNode;
  onClick: () => void;
  disabled?: boolean;
  variant?: "red" | "amber";
  ariaLabel: string;
  /** Force the pressed (sunk) state — used to mirror keyboard presses. */
  pressed?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-label={ariaLabel}
      className={`arcade-btn ${variant === "amber" ? "arcade-btn-amber" : ""} ${
        pressed ? "arcade-btn-press" : ""
      }`}
    >
      {children}
    </button>
  );
}

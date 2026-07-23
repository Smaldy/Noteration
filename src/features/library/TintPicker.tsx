import { Check, Pipette } from "lucide-react";
import { useRef } from "react";
import { useTranslation } from "react-i18next";

import { isCustomTint, tint, TINT_NAMES } from "@/lib/tints";
import { cn } from "@/lib/utils";

/** The pastel swatch row used by the folder and group dialogs, plus a custom
 *  color well.
 *
 *  Swatches show the **ink** color, not the pastel panel fill: the panel is a
 *  ~92% lightness wash designed to sit behind white cards, so a row of them
 *  reads as eight barely distinguishable greys. The saturated ink is what
 *  actually tells the colors apart at swatch size.
 */
export function TintPicker({
  value,
  onChange,
  label,
}: {
  value: string;
  onChange: (next: string) => void;
  label?: string;
}) {
  const { t } = useTranslation();
  const colorInput = useRef<HTMLInputElement>(null);
  const custom = isCustomTint(value);

  return (
    <div>
      <p className="mb-2 text-sm font-medium">{label ?? t("folders.color")}</p>
      <div className="flex flex-wrap items-center gap-2">
        {TINT_NAMES.map((name) => {
          const selected = !custom && name === value;
          return (
            <button
              key={name}
              type="button"
              aria-label={t(`folders.tints.${name}`)}
              title={t(`folders.tints.${name}`)}
              aria-pressed={selected}
              onClick={() => onChange(name)}
              className={cn(
                "grid size-8 place-items-center rounded-full transition-transform",
                tint(name).dot,
                "hover:scale-110 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                selected && "ring-2 ring-foreground/50 ring-offset-2 ring-offset-background",
              )}
            >
              {selected && <Check className="size-4 text-background" />}
            </button>
          );
        })}

        {/* Native color input: a full picker for free, no dependency, and it
            keeps working in the packaged desktop build. */}
        <button
          type="button"
          aria-label={t("folders.customColor")}
          title={t("folders.customColor")}
          aria-pressed={custom}
          onClick={() => colorInput.current?.click()}
          style={custom ? { backgroundColor: value } : undefined}
          className={cn(
            "grid size-8 place-items-center rounded-full border-2 border-dashed border-foreground/25 transition-transform",
            "hover:scale-110 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
            custom && "border-solid ring-2 ring-foreground/50 ring-offset-2 ring-offset-background",
          )}
        >
          {custom ? (
            <Check className="size-4 text-background" />
          ) : (
            <Pipette className="size-3.5 text-muted-foreground" />
          )}
        </button>
        <input
          ref={colorInput}
          type="color"
          className="sr-only"
          value={custom ? value : "#6366f1"}
          onChange={(e) => onChange(e.target.value.toLowerCase())}
        />
      </div>
    </div>
  );
}

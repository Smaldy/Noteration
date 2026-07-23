/** The folder/sub-group pastel palette.
 *
 *  Every class string here is spelled out in full and never assembled by
 *  concatenation: Tailwind discovers classes by scanning source text, so a
 *  computed `bg-tint-${name}-soft` would be purged from the build and the
 *  folder would render untinted. Adding a tint means adding the CSS variable
 *  pair in index.css *and* a literal row below.
 *
 *  `panel` is the pastel tray a folder is drawn on, `ink` the readable title
 *  color on it, `dot` the solid swatch used in pickers and group chips.
 */

export const TINT_NAMES = [
  "rose",
  "amber",
  "mint",
  "sky",
  "lilac",
  "peach",
  "sage",
  "slate",
] as const;

export type TintName = (typeof TINT_NAMES)[number];

/** Mirrors DEFAULT_TINT in backend/models/folders.py. */
export const DEFAULT_TINT: TintName = "slate";

interface Tint {
  panel: string;
  ink: string;
  dot: string;
}

const TINTS: Record<TintName, Tint> = {
  rose: {
    panel: "bg-tint-rose-soft",
    ink: "text-tint-rose",
    dot: "bg-tint-rose",
  },
  amber: {
    panel: "bg-tint-amber-soft",
    ink: "text-tint-amber",
    dot: "bg-tint-amber",
  },
  mint: {
    panel: "bg-tint-mint-soft",
    ink: "text-tint-mint",
    dot: "bg-tint-mint",
  },
  sky: {
    panel: "bg-tint-sky-soft",
    ink: "text-tint-sky",
    dot: "bg-tint-sky",
  },
  lilac: {
    panel: "bg-tint-lilac-soft",
    ink: "text-tint-lilac",
    dot: "bg-tint-lilac",
  },
  peach: {
    panel: "bg-tint-peach-soft",
    ink: "text-tint-peach",
    dot: "bg-tint-peach",
  },
  sage: {
    panel: "bg-tint-sage-soft",
    ink: "text-tint-sage",
    dot: "bg-tint-sage",
  },
  slate: {
    panel: "bg-tint-slate-soft",
    ink: "text-tint-slate",
    dot: "bg-tint-slate",
  },
};

/** A stored tint is either a name from TINT_NAMES or a custom "#rrggbb". */
export function isCustomTint(value: string | null | undefined): value is string {
  return typeof value === "string" && /^#[0-9a-f]{6}$/i.test(value);
}

/** Inline styles for a custom hex tint.
 *
 *  Custom colors can't go through Tailwind classes (they aren't known at build
 *  time), so they're applied as inline styles instead. The panel is the color
 *  at low alpha so it reads as a pastel tray like the named tints, while the
 *  ink stays the full-strength color for the title.
 */
export function customTintStyle(hex: string): {
  panel: React.CSSProperties;
  ink: React.CSSProperties;
  dot: React.CSSProperties;
} {
  return {
    panel: { backgroundColor: `color-mix(in srgb, ${hex} 18%, transparent)` },
    ink: { color: hex },
    dot: { backgroundColor: hex },
  };
}

/** Fallback keeps an unknown/legacy stored tint rendering as a neutral folder
 *  rather than an unstyled one. Custom hex tints return empty class strings —
 *  callers pair this with `customTintStyle` for the inline half. */
export function tint(name: string | null | undefined): Tint {
  if (isCustomTint(name)) return { panel: "", ink: "", dot: "" };
  return (name != null && TINTS[name as TintName]) || TINTS.slate;
}

/** Everything a component needs to paint one tinted surface, named or custom.
 *
 *  Named tints resolve to Tailwind classes and no styles; custom hex tints to
 *  inline styles and no classes. Callers spread both without caring which kind
 *  they got, so no component has to branch on `isCustomTint` itself.
 */
export function tintSkin(value: string | null | undefined): {
  panel: string;
  ink: string;
  dot: string;
  panelStyle?: React.CSSProperties;
  inkStyle?: React.CSSProperties;
  dotStyle?: React.CSSProperties;
} {
  const classes = tint(value);
  if (!isCustomTint(value)) return classes;
  const style = customTintStyle(value);
  return {
    ...classes,
    panelStyle: style.panel,
    inkStyle: style.ink,
    dotStyle: style.dot,
  };
}

/** Stable per-id tint, so folders the user never colored still come out varied
 *  instead of a wall of grey — and keep the same color across reloads. */
export function autoTint(id: number): TintName {
  return TINT_NAMES[id % TINT_NAMES.length];
}

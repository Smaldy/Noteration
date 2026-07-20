/**
 * Provider identity + tier styling — one source of truth for the active-provider
 * badge, the lane cards, the history log, and the in-view note stamp.
 *
 * Tier colors are intentionally FIXED hues (not theme-derived): green = free,
 * amber = local (docs/architecture.md). The student should read "which tier is
 * serving me?" at a glance, independent of the accent theme.
 */

export type ProviderTier = "free" | "local";

export interface ProviderInfo {
  /** Friendly label, e.g. "Gemini Free". */
  label: string;
  /** Short label for tight spots (the in-view note stamp). */
  short: string;
  tier: ProviderTier;
  /** Tailwind class fragments, tinted per tier (match the calendar chip idiom). */
  dot: string;
  text: string;
  bg: string;
  border: string;
}

const TIER_STYLE: Record<ProviderTier, Omit<ProviderInfo, "label" | "short" | "tier">> = {
  free: {
    dot: "bg-emerald-500",
    text: "text-emerald-700 dark:text-emerald-300",
    bg: "bg-emerald-500/10",
    border: "border-emerald-500/30",
  },
  local: {
    dot: "bg-amber-500",
    text: "text-amber-700 dark:text-amber-300",
    bg: "bg-amber-500/10",
    border: "border-amber-500/30",
  },
};

const KNOWN: Record<string, { label: string; short: string; tier: ProviderTier }> = {
  gemini_free: { label: "Gemini Free", short: "Gemini", tier: "free" },
  ollama: { label: "Ollama (local)", short: "Ollama", tier: "local" },
};

/** Selectable provider names in waterfall (cheapest-first) order, so callers
 *  can offer a model choice without hardcoding names elsewhere. */
export const PROVIDER_NAMES: string[] = Object.keys(KNOWN);

export function providerInfo(name: string | null | undefined): ProviderInfo {
  if (!name) {
    return {
      label: "Idle",
      short: "Idle",
      tier: "free",
      dot: "bg-muted-foreground/40",
      text: "text-muted-foreground",
      bg: "bg-muted/60",
      border: "border-border",
    };
  }
  const known = KNOWN[name] ?? {
    // Unknown/mock providers (e.g. a custom name) default to a free-tier look.
    label: name,
    short: name,
    tier: "free" as ProviderTier,
  };
  return { ...TIER_STYLE[known.tier], label: known.label, short: known.short, tier: known.tier };
}

/**
 * Provider identity + tier styling — one source of truth for the active-provider
 * badge, the lane cards, the history log, and the in-view note stamp.
 *
 * Tier colors are intentionally FIXED hues (not theme-derived): green = free,
 * amber = local, red = paid (docs/architecture.md). The student
 * should read "am I spending money?" at a glance, independent of the accent theme.
 */

export type ProviderTier = "free" | "local" | "paid";

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
  paid: {
    dot: "bg-rose-500",
    text: "text-rose-700 dark:text-rose-300",
    bg: "bg-rose-500/10",
    border: "border-rose-500/30",
  },
};

const KNOWN: Record<string, { label: string; short: string; tier: ProviderTier }> = {
  gemini_free: { label: "Gemini Free", short: "Gemini", tier: "free" },
  ollama: { label: "Ollama (local)", short: "Ollama", tier: "local" },
  claude_paid: { label: "Claude (paid)", short: "Claude", tier: "paid" },
};

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

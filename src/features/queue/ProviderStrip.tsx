import { cn } from "@/lib/utils";
import { providerInfo } from "@/lib/providers";
import type { ProviderLaneState } from "@/types/lanes";

/**
 * The cheapest-first waterfall, shown in order with each provider's live state:
 * active · cooling (quota window resetting) · disabled (off / never-spend).
 */
export function ProviderStrip({
  providers,
  active,
}: {
  providers: ProviderLaneState[];
  active: string | null;
}) {
  if (providers.length === 0) return null;
  return (
    <div className="flex flex-wrap items-center gap-2">
      <span className="text-xs font-medium text-muted-foreground">Waterfall</span>
      {providers.map((p, i) => {
        const info = providerInfo(p.provider);
        const isActive = p.provider === active;
        return (
          <div key={p.provider} className="flex items-center gap-2">
            {i > 0 && <span className="text-muted-foreground/40">→</span>}
            <span
              className={cn(
                "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium",
                p.state === "disabled"
                  ? "border-border bg-muted/50 text-muted-foreground/60 line-through"
                  : cn(info.border, info.bg, info.text),
                isActive && p.state !== "disabled" && "ring-2 ring-primary/40",
              )}
            >
              <span
                className={cn(
                  "size-2 rounded-full",
                  p.state === "disabled"
                    ? "bg-muted-foreground/40"
                    : p.state === "cooling"
                      ? "bg-amber-500 animate-pulse"
                      : info.dot,
                )}
              />
              {info.label}
              {p.state === "cooling" && (
                <span className="text-[10px] text-amber-600 dark:text-amber-400">cooling</span>
              )}
            </span>
          </div>
        );
      })}
    </div>
  );
}

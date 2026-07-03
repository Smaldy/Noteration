/** Generic form controls shared by the settings sections: section card, field
 *  wrapper, toggle row, segmented picker, numeric stepper, swatch, status pill. */

import { motion } from "framer-motion";
import { Check, Minus, Plus } from "lucide-react";
import { type ComponentType, type ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { cn } from "@/lib/utils";

export function Section({
  id,
  icon: Icon,
  title,
  description,
  delay = 0,
  children,
}: {
  id: string;
  icon: ComponentType<{ className?: string }>;
  title: string;
  description?: string;
  delay?: number;
  children: ReactNode;
}) {
  return (
    <section
      id={id}
      style={{ animationDelay: `${delay}ms` }}
      className="animate-rise scroll-mt-24 rounded-2xl border border-border/70 bg-card/70 p-6 shadow-sm backdrop-blur-sm"
    >
      <div className="flex items-start gap-3">
        <span className="mt-0.5 inline-flex size-9 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary ring-1 ring-inset ring-primary/15">
          <Icon className="size-[18px]" />
        </span>
        <div className="min-w-0">
          <h2 className="font-display text-base font-semibold tracking-tight text-foreground">
            {title}
          </h2>
          {description && (
            <p className="mt-0.5 text-xs text-muted-foreground">{description}</p>
          )}
        </div>
      </div>
      <div className="mt-4 space-y-5 border-t border-border/60 pt-5">{children}</div>
    </section>
  );
}

export function Segmented<T extends string>({
  group,
  value,
  options,
  onChange,
}: {
  group: string;
  value: T;
  options: { value: T; label: string }[];
  onChange: (value: T) => void;
}) {
  return (
    <div className="inline-flex rounded-xl border bg-secondary/40 p-1">
      {options.map((o) => {
        const active = o.value === value;
        return (
          <button
            key={o.value}
            type="button"
            onClick={() => onChange(o.value)}
            className={cn(
              "relative rounded-lg px-3.5 py-1.5 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
              active ? "text-primary-foreground" : "text-muted-foreground hover:text-foreground",
            )}
          >
            {active && (
              <motion.span
                layoutId={`seg-${group}`}
                className="absolute inset-0 rounded-lg bg-primary shadow-sm"
                transition={{ type: "spring", stiffness: 420, damping: 34 }}
              />
            )}
            <span className="relative z-10">{o.label}</span>
          </button>
        );
      })}
    </div>
  );
}

export function Swatch({
  color,
  selected,
  onClick,
  title,
  dashed = false,
}: {
  color?: string;
  selected: boolean;
  onClick: () => void;
  title: string;
  dashed?: boolean;
}) {
  return (
    <button
      type="button"
      title={title}
      onClick={onClick}
      style={color ? { backgroundColor: color } : undefined}
      className={cn(
        "flex size-8 items-center justify-center rounded-full transition-transform duration-150 hover:scale-110 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-card active:scale-95",
        dashed && "border-2 border-dashed border-muted-foreground/50",
        selected
          ? "ring-2 ring-foreground ring-offset-2 ring-offset-card"
          : "ring-1 ring-black/10 dark:ring-white/15",
      )}
    >
      {selected && (
        <Check
          strokeWidth={3}
          className={cn(
            "size-4",
            dashed
              ? "text-foreground"
              : "text-white drop-shadow-[0_1px_1px_rgba(0,0,0,0.45)]",
          )}
        />
      )}
    </button>
  );
}

export function Field({
  label,
  badge,
  children,
}: {
  label: string;
  badge?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="space-y-2.5">
      <div className="flex items-center gap-2">
        <Label className="block">{label}</Label>
        {badge}
      </div>
      {children}
    </div>
  );
}

/** Refined numeric stepper: a − / value / + control that replaces the cheap,
 *  unthemed native number-input spinners. Clamps to min/max and supports step. */
export function NumberField({
  value,
  onChange,
  min,
  max,
  step = 1,
  className,
}: {
  value: number;
  onChange: (v: number) => void;
  min?: number;
  max?: number;
  step?: number;
  className?: string;
}) {
  const clamp = (n: number) => {
    if (Number.isNaN(n)) return min ?? 0;
    let v = n;
    if (min != null) v = Math.max(min, v);
    if (max != null) v = Math.min(max, v);
    return v;
  };
  const { t } = useTranslation();
  const atMin = min != null && value <= min;
  const atMax = max != null && value >= max;

  return (
    <div
      className={cn(
        "inline-flex h-9 items-stretch overflow-hidden rounded-lg border border-input bg-transparent shadow-sm transition-colors focus-within:ring-1 focus-within:ring-ring",
        className,
      )}
    >
      <StepButton
        label={t("settings.number.decrease")}
        disabled={atMin}
        onClick={() => onChange(clamp(value - step))}
      >
        <Minus className="size-3.5" />
      </StepButton>
      <input
        type="number"
        inputMode="numeric"
        value={value}
        min={min}
        max={max}
        step={step}
        onChange={(e) => onChange(clamp(Number(e.target.value)))}
        className="w-full min-w-0 border-x border-input bg-transparent text-center text-sm tabular-nums outline-none"
      />
      <StepButton
        label={t("settings.number.increase")}
        disabled={atMax}
        onClick={() => onChange(clamp(value + step))}
      >
        <Plus className="size-3.5" />
      </StepButton>
    </div>
  );
}

function StepButton({
  children,
  label,
  disabled,
  onClick,
}: {
  children: ReactNode;
  label: string;
  disabled?: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      disabled={disabled}
      onClick={onClick}
      className="flex w-9 shrink-0 items-center justify-center text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring active:bg-secondary/70 disabled:pointer-events-none disabled:opacity-30"
    >
      {children}
    </button>
  );
}

/** Small "key is configured" status pill. */
export function SetBadge() {
  const { t } = useTranslation();
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-success/12 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-success">
      <Check className="size-3" strokeWidth={3} />
      {t("settings.apiKeys.set")}
    </span>
  );
}

export function Toggle({
  label,
  hint,
  checked,
  onChange,
}: {
  label: string;
  hint?: string;
  checked: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <div className="flex items-center justify-between gap-4">
      <div>
        <p className="text-sm font-medium">{label}</p>
        {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
      </div>
      <Switch checked={checked} onCheckedChange={onChange} />
    </div>
  );
}

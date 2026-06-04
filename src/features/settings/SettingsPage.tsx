import { AnimatePresence, motion } from "framer-motion";
import {
  ArrowLeft,
  CalendarClock,
  Check,
  FileText,
  KeyRound,
  Minus,
  Palette,
  Plus,
  RotateCcw,
  Sparkles,
  Timer,
} from "lucide-react";
import {
  type ComponentType,
  type ReactNode,
  useEffect,
  useMemo,
  useState,
} from "react";
import { useNavigate } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { cn } from "@/lib/utils";
import { applyAppearance, useSettingsStore } from "@/stores/settings";
import type { CalendarSlot, GeminiModel, Settings, Theme } from "@/types/settings";

interface FormState {
  allow_paid: boolean;
  ollama_enabled: boolean;
  gemini_model: GeminiModel;
  per_document_token_budget: number;
  note_length: number;
  pomodoro_work_min: number;
  pomodoro_break_min: number;
  calendar_day_start_hour: number;
  calendar_day_end_hour: number;
  calendar_slot_minutes: CalendarSlot;
  theme: Theme;
  accent_color: string; // "" = follow theme default
  font_family: string;
  font_size: number;
}

const SLOT_OPTIONS: { value: CalendarSlot; label: string }[] = [
  { value: 15, label: "15 min" },
  { value: 30, label: "30 min" },
  { value: 60, label: "1 hour" },
  { value: 90, label: "1.5 hr" },
  { value: 120, label: "2 hours" },
];

const SLOT_VALUES: CalendarSlot[] = [15, 30, 60, 90, 120];

/** Snap an arbitrary stored slot value to the nearest allowed option. */
function toSlot(n: number): CalendarSlot {
  return SLOT_VALUES.includes(n as CalendarSlot)
    ? (n as CalendarSlot)
    : SLOT_VALUES.reduce((best, v) =>
        Math.abs(v - n) < Math.abs(best - n) ? v : best,
      );
}

/** Format an hour (0–24) as a clock label, e.g. 8 → "8:00", 23 → "23:00". */
function hourLabel(h: number): string {
  return `${h}:00`;
}

const GEMINI_MODELS: { value: GeminiModel; label: string; hint: string }[] = [
  {
    value: "gemini-2.5-flash-lite",
    label: "Flash Lite",
    hint: "Cheapest, fastest — recommended for bulk generation.",
  },
  {
    value: "gemini-2.5-flash",
    label: "Flash",
    hint: "More capable, uses more quota per topic.",
  },
];

// Curated accent palette (hex drives the whole derived palette live).
const PRESET_ACCENTS: { name: string; hex: string }[] = [
  { name: "Indigo", hex: "#6366f1" },
  { name: "Violet", hex: "#8b5cf6" },
  { name: "Blue", hex: "#3b82f6" },
  { name: "Sky", hex: "#0ea5e9" },
  { name: "Teal", hex: "#14b8a6" },
  { name: "Emerald", hex: "#10b981" },
  { name: "Amber", hex: "#f59e0b" },
  { name: "Rose", hex: "#f43f5e" },
  { name: "Slate", hex: "#475569" },
];

const FONT_OPTIONS: { value: string; label: string }[] = [
  { value: "sans", label: "Jakarta" },
  { value: "system", label: "System" },
  { value: "inter", label: "Inter" },
  { value: "serif", label: "Newsreader" },
  { value: "mono", label: "Mono" },
];

// Render each font button in its own typeface as a preview.
const FONT_PREVIEW: Record<string, string> = {
  sans: '"Plus Jakarta Sans Variable", system-ui, sans-serif',
  system: "system-ui, sans-serif",
  inter: '"Inter Variable", system-ui, sans-serif',
  serif: '"Newsreader Variable", Georgia, serif',
  mono: '"JetBrains Mono", ui-monospace, monospace',
};

// Section registry powers both the scroll-spy sidebar and the rendered cards,
// so the nav can never drift out of sync with the content.
const SECTIONS: {
  id: string;
  label: string;
  icon: ComponentType<{ className?: string }>;
}[] = [
  { id: "api-keys", label: "API keys", icon: KeyRound },
  { id: "providers", label: "Providers", icon: Sparkles },
  { id: "generation", label: "Generation", icon: FileText },
  { id: "pomodoro", label: "Pomodoro", icon: Timer },
  { id: "calendar", label: "Calendar", icon: CalendarClock },
  { id: "appearance", label: "Appearance", icon: Palette },
];

function toForm(s: Settings): FormState {
  return {
    allow_paid: s.allow_paid,
    ollama_enabled: s.ollama_enabled,
    gemini_model: (s.gemini_model as GeminiModel) ?? "gemini-2.5-flash-lite",
    per_document_token_budget: s.per_document_token_budget,
    note_length: s.note_length ?? 3,
    pomodoro_work_min: s.pomodoro_work_min,
    pomodoro_break_min: s.pomodoro_break_min,
    calendar_day_start_hour: s.calendar_day_start_hour,
    calendar_day_end_hour: s.calendar_day_end_hour,
    calendar_slot_minutes: toSlot(s.calendar_slot_minutes),
    theme: (s.theme as Theme) ?? "system",
    accent_color: s.accent_color ?? "",
    font_family: s.font_family ?? "sans",
    font_size: s.font_size,
  };
}

export function SettingsPage() {
  const navigate = useNavigate();
  const { settings, loadState, saving, saveError, fetchSettings, updateSettings } =
    useSettingsStore();

  const [form, setForm] = useState<FormState | null>(null);
  const [geminiKey, setGeminiKey] = useState("");
  const [claudeKey, setClaudeKey] = useState("");
  const [saved, setSaved] = useState(false);
  const [active, setActive] = useState(SECTIONS[0].id);

  useEffect(() => {
    void fetchSettings();
  }, [fetchSettings]);

  useEffect(() => {
    if (settings) setForm(toForm(settings));
  }, [settings]);

  // Live preview: reflect appearance edits immediately (persisted on Save).
  useEffect(() => {
    if (!form) return;
    applyAppearance({
      theme: form.theme,
      font_size: form.font_size,
      accent_color: form.accent_color || null,
      font_family: form.font_family || null,
    });
  }, [form]);

  // On leaving, snap back to the persisted appearance (discard unsaved preview).
  useEffect(() => {
    return () => {
      const s = useSettingsStore.getState().settings;
      if (s) {
        applyAppearance({
          theme: s.theme,
          font_size: s.font_size,
          accent_color: s.accent_color,
          font_family: s.font_family,
        });
      }
    };
  }, []);

  // Scroll-spy: highlight the nav item whose section sits in the upper band of
  // the viewport. Runs once the form (and therefore the sections) is mounted.
  useEffect(() => {
    if (!form) return;
    const observer = new IntersectionObserver(
      (entries) => {
        const top = entries
          .filter((e) => e.isIntersecting)
          .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top)[0];
        if (top) setActive(top.target.id);
      },
      { rootMargin: "-18% 0px -72% 0px", threshold: 0 },
    );
    for (const s of SECTIONS) {
      const el = document.getElementById(s.id);
      if (el) observer.observe(el);
    }
    return () => observer.disconnect();
  }, [form]);

  const baseline = useMemo(() => (settings ? toForm(settings) : null), [settings]);
  const dirty =
    !!form &&
    !!baseline &&
    (JSON.stringify(form) !== JSON.stringify(baseline) ||
      geminiKey.trim() !== "" ||
      claudeKey.trim() !== "");

  if (loadState === "error") {
    return (
      <Shell onBack={() => navigate("/")}>
        <p className="text-sm text-destructive">Failed to load settings.</p>
      </Shell>
    );
  }
  if (!form || !settings || !baseline) {
    return (
      <Shell onBack={() => navigate("/")}>
        <p className="text-sm text-muted-foreground">Loading…</p>
      </Shell>
    );
  }

  function set<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((f) => (f ? { ...f, [key]: value } : f));
    setSaved(false);
  }

  function discard() {
    if (baseline) setForm(baseline);
    setGeminiKey("");
    setClaudeKey("");
    setSaved(false);
  }

  function jumpTo(id: string) {
    setActive(id);
    document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  async function handleSave() {
    if (!form) return;
    try {
      await updateSettings({
        allow_paid: form.allow_paid,
        ollama_enabled: form.ollama_enabled,
        gemini_model: form.gemini_model,
        per_document_token_budget: form.per_document_token_budget,
        note_length: form.note_length,
        pomodoro_work_min: form.pomodoro_work_min,
        pomodoro_break_min: form.pomodoro_break_min,
        calendar_day_start_hour: form.calendar_day_start_hour,
        calendar_day_end_hour: form.calendar_day_end_hour,
        calendar_slot_minutes: form.calendar_slot_minutes,
        theme: form.theme,
        accent_color: form.accent_color || null,
        font_family: form.font_family,
        font_size: form.font_size,
        ...(geminiKey.trim() ? { api_key_gemini: geminiKey.trim() } : {}),
        ...(claudeKey.trim() ? { api_key_claude: claudeKey.trim() } : {}),
      });
      setGeminiKey("");
      setClaudeKey("");
      setSaved(true);
    } catch {
      // saveError surfaced from the store
    }
  }

  return (
    <Shell
      onBack={() => navigate("/")}
      footer={
        <ActionBar
          dirty={dirty}
          saving={saving}
          saved={saved}
          saveError={saveError}
          onSave={() => void handleSave()}
          onDiscard={discard}
        />
      }
    >
      <div className="grid gap-x-12 gap-y-8 lg:grid-cols-[180px_minmax(0,1fr)]">
        <SectionNav active={active} onJump={jumpTo} />

        <div className="min-w-0 space-y-7">
          <header className="animate-rise space-y-1.5">
            <h1 className="text-3xl font-bold tracking-tight">Settings</h1>
            <p className="text-sm text-muted-foreground">
              Tune the providers, study rhythm, and how Noteration looks.
            </p>
          </header>

          <Section
            id="api-keys"
            icon={KeyRound}
            title="API keys"
            description="Stored locally; used by the provider waterfall."
            delay={40}
          >
            <Field
              label="Gemini key"
              badge={settings.gemini_key_set ? <SetBadge /> : undefined}
            >
              <Input
                type="password"
                placeholder={
                  settings.gemini_key_set ? "•••••••• (replace)" : "Add a key"
                }
                value={geminiKey}
                onChange={(e) => setGeminiKey(e.target.value)}
              />
            </Field>
            <Field
              label="Claude key"
              badge={settings.claude_key_set ? <SetBadge /> : undefined}
            >
              <Input
                type="password"
                placeholder={
                  settings.claude_key_set ? "•••••••• (replace)" : "Add a key"
                }
                value={claudeKey}
                onChange={(e) => setClaudeKey(e.target.value)}
              />
            </Field>
          </Section>

          <Section
            id="providers"
            icon={Sparkles}
            title="Provider waterfall"
            description="Free providers run first. Order is automatic (cheapest-first)."
            delay={100}
          >
            <Field label="Gemini model">
              <Segmented
                group="gemini"
                value={form.gemini_model}
                onChange={(v) => set("gemini_model", v)}
                options={GEMINI_MODELS.map((m) => ({ value: m.value, label: m.label }))}
              />
              <p className="text-xs text-muted-foreground">
                {GEMINI_MODELS.find((m) => m.value === form.gemini_model)?.hint}
              </p>
            </Field>
            <Toggle
              label="Allow paid fallback (Claude)"
              hint="Off = never spend; free tiers only."
              checked={form.allow_paid}
              onChange={(v) => set("allow_paid", v)}
            />
            <Toggle
              label="Use local Ollama"
              hint="Include a local $0 model in the waterfall (must be installed)."
              checked={form.ollama_enabled}
              onChange={(v) => set("ollama_enabled", v)}
            />
            <Field label="Per-document token budget">
              <NumberField
                min={0}
                step={1000}
                value={form.per_document_token_budget}
                onChange={(v) => set("per_document_token_budget", v)}
                className="w-44"
              />
              <p className="text-xs text-muted-foreground">
                Safety cap: a document is paused if it spends more than this many
                tokens. 0 = automatic (pauses only a clear runaway, ~3× the estimate).
              </p>
            </Field>
          </Section>

          <Section
            id="generation"
            icon={FileText}
            title="Note generation"
            description="How much content the AI generates per topic."
            delay={150}
          >
            <Field label={`Notes length — ${form.note_length} ${form.note_length === 1 ? "page" : "pages"} per topic`}>
              <div className="flex items-center gap-3">
                <span className="text-xs text-muted-foreground">Brief</span>
                <div className="w-60 max-w-full">
                  <input
                    type="range"
                    min={1}
                    max={10}
                    value={form.note_length}
                    onChange={(e) => set("note_length", Number(e.target.value))}
                    className="app-range"
                  />
                </div>
                <span className="text-xs text-muted-foreground">Detailed</span>
              </div>
              <p className="text-xs text-muted-foreground">
                A "page" is a unit of content (~300 words). The AI aims for this
                many pages per topic; if a topic doesn't have enough material it
                generates what it can. More pages use more tokens.
              </p>
            </Field>
          </Section>

          <Section id="pomodoro" icon={Timer} title="Pomodoro" delay={160}>
            <div className="flex flex-wrap gap-6">
              <Field label="Work minutes">
                <NumberField
                  min={1}
                  max={180}
                  value={form.pomodoro_work_min}
                  onChange={(v) => set("pomodoro_work_min", v)}
                  className="w-32"
                />
              </Field>
              <Field label="Break minutes">
                <NumberField
                  min={1}
                  max={120}
                  value={form.pomodoro_break_min}
                  onChange={(v) => set("pomodoro_break_min", v)}
                  className="w-32"
                />
              </Field>
            </div>
          </Section>

          <Section
            id="calendar"
            icon={CalendarClock}
            title="Calendar"
            description="The hourly Day view's visible window and slot size. Double-click the Day button in the calendar to switch it to the hourly grid."
            delay={220}
          >
            <div className="flex flex-wrap gap-6">
              <Field label="Day starts at">
                <NumberField
                  min={0}
                  max={form.calendar_day_end_hour - 1}
                  value={form.calendar_day_start_hour}
                  onChange={(v) => set("calendar_day_start_hour", v)}
                  className="w-32"
                />
              </Field>
              <Field label="Day ends at">
                <NumberField
                  min={form.calendar_day_start_hour + 1}
                  max={24}
                  value={form.calendar_day_end_hour}
                  onChange={(v) => set("calendar_day_end_hour", v)}
                  className="w-32"
                />
              </Field>
            </div>
            <p className="text-xs text-muted-foreground">
              Showing {hourLabel(form.calendar_day_start_hour)} –{" "}
              {hourLabel(form.calendar_day_end_hour)}.
            </p>
            <Field label="Time slot size">
              <Segmented
                group="slot"
                value={String(form.calendar_slot_minutes)}
                onChange={(v) =>
                  set("calendar_slot_minutes", Number(v) as CalendarSlot)
                }
                options={SLOT_OPTIONS.map((o) => ({
                  value: String(o.value),
                  label: o.label,
                }))}
              />
              <p className="text-xs text-muted-foreground">
                The gap between rows in the hourly Day view.
              </p>
            </Field>
          </Section>

          <Section
            id="appearance"
            icon={Palette}
            title="Appearance"
            description="Changes preview instantly; Save to keep them."
            delay={280}
          >
            <Field label="Theme">
              <Segmented
                group="theme"
                value={form.theme}
                onChange={(v) => set("theme", v as Theme)}
                options={(["system", "light", "dark"] as Theme[]).map((t) => ({
                  value: t,
                  label: t[0].toUpperCase() + t.slice(1),
                }))}
              />
            </Field>

            <Field label="Accent color">
              <div className="flex flex-wrap items-center gap-2.5">
                <Swatch
                  selected={form.accent_color === ""}
                  onClick={() => set("accent_color", "")}
                  title="Theme default"
                  dashed
                />
                {PRESET_ACCENTS.map((c) => (
                  <Swatch
                    key={c.hex}
                    color={c.hex}
                    title={c.name}
                    selected={form.accent_color.toLowerCase() === c.hex.toLowerCase()}
                    onClick={() => set("accent_color", c.hex)}
                  />
                ))}
                <label
                  className="relative ml-1 inline-flex size-8 cursor-pointer items-center justify-center rounded-full border border-dashed border-muted-foreground/50 text-base text-muted-foreground transition-transform hover:scale-110"
                  title="Custom color"
                >
                  +
                  <input
                    type="color"
                    value={form.accent_color || "#6366f1"}
                    onChange={(e) => set("accent_color", e.target.value)}
                    className="absolute inset-0 cursor-pointer opacity-0"
                  />
                </label>
              </div>
            </Field>

            <Field label="Font">
              <div className="inline-flex flex-wrap gap-2">
                {FONT_OPTIONS.map((f) => (
                  <button
                    key={f.value}
                    type="button"
                    onClick={() => set("font_family", f.value)}
                    style={{ fontFamily: FONT_PREVIEW[f.value] }}
                    className={cn(
                      "rounded-lg border px-3.5 py-2 text-sm transition-all duration-150 active:scale-95",
                      form.font_family === f.value
                        ? "border-primary bg-primary-soft text-primary-soft-foreground shadow-sm"
                        : "text-muted-foreground hover:border-ring/40 hover:text-foreground",
                    )}
                  >
                    {f.label}
                  </button>
                ))}
              </div>
            </Field>

            <Field label={`Base font size — ${form.font_size}px`}>
              <div className="flex items-center gap-3">
                <span className="text-xs text-muted-foreground">A</span>
                <div className="w-60 max-w-full">
                  <input
                    type="range"
                    min={12}
                    max={22}
                    value={form.font_size}
                    onChange={(e) => set("font_size", Number(e.target.value))}
                    className="app-range"
                  />
                </div>
                <span className="text-lg text-muted-foreground">A</span>
              </div>
            </Field>
          </Section>
        </div>
      </div>
    </Shell>
  );
}

function Shell({
  children,
  footer,
  onBack,
}: {
  children: ReactNode;
  footer?: ReactNode;
  onBack: () => void;
}) {
  return (
    <div className="flex min-h-screen flex-col">
      <header className="glass sticky top-0 z-20 border-b">
        <div className="mx-auto flex max-w-4xl items-center justify-between px-6 py-3.5">
          <button
            type="button"
            onClick={onBack}
            className="inline-flex items-center gap-1.5 text-sm font-medium text-muted-foreground transition-colors hover:text-foreground"
          >
            <ArrowLeft className="size-4" />
            Library
          </button>
          <span className="font-display text-sm font-semibold tracking-tight text-muted-foreground">
            Settings
          </span>
        </div>
      </header>
      <main className="flex-1">
        <div className="mx-auto max-w-4xl px-6 py-10">{children}</div>
      </main>
      {footer}
    </div>
  );
}

/** Sticky scroll-spy navigation. A single sliding pill (layoutId) tracks the
 *  active section as you scroll, which reads far more refined than per-item
 *  background toggles. */
function SectionNav({
  active,
  onJump,
}: {
  active: string;
  onJump: (id: string) => void;
}) {
  return (
    <nav className="hidden lg:block">
      <div className="sticky top-24 space-y-0.5">
        {SECTIONS.map((s) => {
          const Icon = s.icon;
          const on = active === s.id;
          return (
            <button
              key={s.id}
              type="button"
              onClick={() => onJump(s.id)}
              className={cn(
                "group relative flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                on
                  ? "text-foreground"
                  : "text-muted-foreground hover:text-foreground",
              )}
            >
              {on && (
                <motion.span
                  layoutId="settings-nav-active"
                  className="absolute inset-0 rounded-lg bg-secondary"
                  transition={{ type: "spring", stiffness: 420, damping: 34 }}
                />
              )}
              <Icon
                className={cn(
                  "relative z-10 size-4 transition-colors",
                  on ? "text-primary" : "text-muted-foreground group-hover:text-foreground",
                )}
              />
              <span className="relative z-10">{s.label}</span>
            </button>
          );
        })}
      </div>
    </nav>
  );
}

function ActionBar({
  dirty,
  saving,
  saved,
  saveError,
  onSave,
  onDiscard,
}: {
  dirty: boolean;
  saving: boolean;
  saved: boolean;
  saveError: string | null;
  onSave: () => void;
  onDiscard: () => void;
}) {
  return (
    <footer className="glass sticky bottom-0 z-20 border-t">
      <div className="mx-auto flex max-w-4xl items-center justify-between gap-3 px-6 py-4">
        <div className="min-h-5 text-sm">
          <AnimatePresence mode="wait" initial={false}>
            {saveError ? (
              <motion.span
                key="err"
                initial={{ opacity: 0, y: 4 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -4 }}
                className="text-destructive"
              >
                {saveError}
              </motion.span>
            ) : saved ? (
              <motion.span
                key="ok"
                initial={{ opacity: 0, y: 4 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -4 }}
                className="inline-flex items-center gap-1.5 font-medium text-emerald-600 dark:text-emerald-400"
              >
                <Check className="size-4" />
                Saved
              </motion.span>
            ) : dirty ? (
              <motion.span
                key="dirty"
                initial={{ opacity: 0, y: 4 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -4 }}
                className="inline-flex items-center gap-1.5 text-muted-foreground"
              >
                <span className="size-1.5 rounded-full bg-amber-500" />
                Unsaved changes
              </motion.span>
            ) : (
              <span className="text-muted-foreground/60">All changes saved</span>
            )}
          </AnimatePresence>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="ghost"
            size="sm"
            onClick={onDiscard}
            disabled={!dirty || saving}
          >
            <RotateCcw />
            Discard
          </Button>
          <Button onClick={onSave} disabled={!dirty || saving}>
            {saving ? "Saving…" : "Save changes"}
          </Button>
        </div>
      </div>
    </footer>
  );
}

function Section({
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
      <div className="mt-5 space-y-5">{children}</div>
    </section>
  );
}

function Segmented<T extends string>({
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
              "relative rounded-lg px-3.5 py-1.5 text-sm font-medium transition-colors",
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

function Swatch({
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
        "flex size-8 items-center justify-center rounded-full transition-transform duration-150 hover:scale-110 active:scale-95",
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

function Field({
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
function NumberField({
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
        label="Decrease"
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
        label="Increase"
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
      className="flex w-9 shrink-0 items-center justify-center text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground active:bg-secondary/70 disabled:pointer-events-none disabled:opacity-30"
    >
      {children}
    </button>
  );
}

/** Small "key is configured" status pill. */
function SetBadge() {
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/12 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-emerald-600 dark:text-emerald-400">
      <Check className="size-3" strokeWidth={3} />
      Set
    </span>
  );
}

function Toggle({
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

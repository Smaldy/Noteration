import { AnimatePresence, motion } from "framer-motion";
import { ArrowLeft, Check, RotateCcw } from "lucide-react";
import { type ReactNode, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { cn } from "@/lib/utils";
import { applyAppearance, useSettingsStore } from "@/stores/settings";
import type { GeminiModel, Settings, Theme } from "@/types/settings";

interface FormState {
  allow_paid: boolean;
  ollama_enabled: boolean;
  gemini_model: GeminiModel;
  pomodoro_work_min: number;
  pomodoro_break_min: number;
  theme: Theme;
  accent_color: string; // "" = follow theme default
  font_family: string;
  font_size: number;
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

function toForm(s: Settings): FormState {
  return {
    allow_paid: s.allow_paid,
    ollama_enabled: s.ollama_enabled,
    gemini_model: (s.gemini_model as GeminiModel) ?? "gemini-2.5-flash-lite",
    pomodoro_work_min: s.pomodoro_work_min,
    pomodoro_break_min: s.pomodoro_break_min,
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

  async function handleSave() {
    if (!form) return;
    try {
      await updateSettings({
        allow_paid: form.allow_paid,
        ollama_enabled: form.ollama_enabled,
        gemini_model: form.gemini_model,
        pomodoro_work_min: form.pomodoro_work_min,
        pomodoro_break_min: form.pomodoro_break_min,
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
      <div className="animate-rise space-y-2">
        <h1 className="text-3xl font-bold tracking-tight">Settings</h1>
        <p className="text-sm text-muted-foreground">
          Tune the providers, study rhythm, and how Noteration looks.
        </p>
      </div>

      <Section title="API keys" description="Stored locally; used by the provider waterfall.">
        <Field label={`Gemini key${settings.gemini_key_set ? " (set)" : ""}`}>
          <Input
            type="password"
            placeholder={settings.gemini_key_set ? "•••••••• (replace)" : "Add a key"}
            value={geminiKey}
            onChange={(e) => setGeminiKey(e.target.value)}
          />
        </Field>
        <Field label={`Claude key${settings.claude_key_set ? " (set)" : ""}`}>
          <Input
            type="password"
            placeholder={settings.claude_key_set ? "•••••••• (replace)" : "Add a key"}
            value={claudeKey}
            onChange={(e) => setClaudeKey(e.target.value)}
          />
        </Field>
      </Section>

      <Section
        title="Provider waterfall"
        description="Free providers run first. Order is automatic (cheapest-first)."
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
      </Section>

      <Section title="Pomodoro">
        <div className="flex flex-wrap gap-6">
          <Field label="Work minutes">
            <Input
              type="number"
              min={1}
              max={180}
              value={form.pomodoro_work_min}
              onChange={(e) => set("pomodoro_work_min", Number(e.target.value))}
              className="w-28"
            />
          </Field>
          <Field label="Break minutes">
            <Input
              type="number"
              min={1}
              max={120}
              value={form.pomodoro_break_min}
              onChange={(e) => set("pomodoro_break_min", Number(e.target.value))}
              className="w-28"
            />
          </Field>
        </div>
      </Section>

      <Section title="Appearance" description="Changes preview instantly; Save to keep them.">
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
              className="relative ml-1 inline-flex size-8 cursor-pointer items-center justify-center rounded-full border text-base text-muted-foreground transition-transform hover:scale-110"
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
          <input
            type="range"
            min={12}
            max={22}
            value={form.font_size}
            onChange={(e) => set("font_size", Number(e.target.value))}
            className="w-64 accent-[var(--primary)]"
          />
        </Field>
      </Section>
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
        <div className="mx-auto flex max-w-2xl items-center justify-between px-6 py-3.5">
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
        <div className="mx-auto max-w-2xl space-y-8 px-6 py-10">{children}</div>
      </main>
      {footer}
    </div>
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
      <div className="mx-auto flex max-w-2xl items-center justify-between gap-3 px-6 py-4">
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
                className="text-muted-foreground"
              >
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
  title,
  description,
  children,
}: {
  title: string;
  description?: string;
  children: ReactNode;
}) {
  return (
    <section className="animate-rise rounded-2xl border bg-card/60 p-6 shadow-sm">
      <h2 className="font-display text-xs font-bold uppercase tracking-[0.12em] text-primary">
        {title}
      </h2>
      {description && (
        <p className="mt-1 text-xs text-muted-foreground">{description}</p>
      )}
      <div className="mt-4 space-y-5">{children}</div>
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
        "size-8 rounded-full transition-transform duration-150 hover:scale-110 active:scale-95",
        dashed && "border-2 border-dashed border-muted-foreground/50",
        selected
          ? "ring-2 ring-foreground ring-offset-2 ring-offset-background"
          : "ring-1 ring-black/10",
      )}
    />
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="space-y-2.5">
      <Label className="block">{label}</Label>
      {children}
    </div>
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

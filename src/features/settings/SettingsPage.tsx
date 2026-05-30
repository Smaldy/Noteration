import { ArrowLeft } from "lucide-react";
import { type ReactNode, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { cn } from "@/lib/utils";
import { applyAppearance, useSettingsStore } from "@/stores/settings";
import type { Settings, Theme } from "@/types/settings";

interface FormState {
  allow_paid: boolean;
  ollama_enabled: boolean;
  pomodoro_work_min: number;
  pomodoro_break_min: number;
  theme: Theme;
  accent_color: string; // "" = follow theme default
  font_family: string;
  font_size: number;
}

// Curated accent palette (hex drives --primary live).
const PRESET_ACCENTS: { name: string; hex: string }[] = [
  { name: "Indigo", hex: "#6366f1" },
  { name: "Violet", hex: "#8b5cf6" },
  { name: "Blue", hex: "#3b82f6" },
  { name: "Sky", hex: "#0ea5e9" },
  { name: "Emerald", hex: "#10b981" },
  { name: "Amber", hex: "#f59e0b" },
  { name: "Rose", hex: "#f43f5e" },
  { name: "Slate", hex: "#475569" },
];

const FONT_OPTIONS: { value: string; label: string }[] = [
  { value: "system", label: "System" },
  { value: "inter", label: "Inter" },
  { value: "serif", label: "Serif" },
  { value: "mono", label: "Monospace" },
];

// Render each font button in its own typeface as a preview.
const FONT_PREVIEW: Record<string, string> = {
  system: "system-ui, sans-serif",
  inter: '"Inter Variable", system-ui, sans-serif',
  serif: "Georgia, serif",
  mono: '"JetBrains Mono", ui-monospace, monospace',
};

function toForm(s: Settings): FormState {
  return {
    allow_paid: s.allow_paid,
    ollama_enabled: s.ollama_enabled,
    pomodoro_work_min: s.pomodoro_work_min,
    pomodoro_break_min: s.pomodoro_break_min,
    theme: (s.theme as Theme) ?? "system",
    accent_color: s.accent_color ?? "",
    font_family: s.font_family ?? "system",
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

  if (loadState === "error") {
    return (
      <Shell onBack={() => navigate("/")}>
        <p className="text-sm text-destructive">Failed to load settings.</p>
      </Shell>
    );
  }
  if (!form || !settings) {
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

  async function handleSave() {
    if (!form) return;
    try {
      await updateSettings({
        allow_paid: form.allow_paid,
        ollama_enabled: form.ollama_enabled,
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
    <Shell onBack={() => navigate("/")}>
      <h1 className="text-2xl font-semibold tracking-tight">Settings</h1>

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
      </Section>

      <Section title="Appearance" description="Changes preview instantly; Save to keep them.">
        <Field label="Theme">
          <div className="inline-flex rounded-lg border p-1">
            {(["system", "light", "dark"] as Theme[]).map((t) => (
              <button
                key={t}
                type="button"
                onClick={() => set("theme", t)}
                className={cn(
                  "rounded-md px-3 py-1 text-sm font-medium capitalize transition-colors",
                  form.theme === t
                    ? "bg-primary text-primary-foreground shadow-sm"
                    : "text-muted-foreground hover:text-foreground",
                )}
              >
                {t}
              </button>
            ))}
          </div>
        </Field>

        <Field label="Accent color">
          <div className="flex flex-wrap items-center gap-2">
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
              className="relative ml-1 inline-flex size-7 cursor-pointer items-center justify-center rounded-full border text-xs text-muted-foreground"
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
                  "rounded-md border px-3 py-1.5 text-sm transition-colors",
                  form.font_family === f.value
                    ? "border-primary bg-primary/10 text-foreground"
                    : "text-muted-foreground hover:text-foreground",
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

      <div className="mt-8 flex items-center gap-3 border-t pt-6">
        <Button onClick={() => void handleSave()} disabled={saving}>
          {saving ? "Saving…" : "Save changes"}
        </Button>
        {saved && <span className="text-sm text-emerald-600">Saved</span>}
        {saveError && <span className="text-sm text-destructive">{saveError}</span>}
      </div>
    </Shell>
  );
}

function Shell({ children, onBack }: { children: ReactNode; onBack: () => void }) {
  return (
    <div className="mx-auto max-w-2xl px-6 py-10">
      <button
        type="button"
        onClick={onBack}
        className="mb-4 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="size-4" />
        Library
      </button>
      {children}
    </div>
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
    <section className="mt-8">
      <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
        {title}
      </h2>
      {description && (
        <p className="mt-1 text-xs text-muted-foreground">{description}</p>
      )}
      <div className="mt-3 space-y-4">{children}</div>
    </section>
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
        "size-7 rounded-full transition-transform hover:scale-110",
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
    <div className="space-y-1.5">
      <Label>{label}</Label>
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

import { ArrowLeft } from "lucide-react";
import { type ReactNode, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { useSettingsStore } from "@/stores/settings";
import type { Settings, Theme } from "@/types/settings";

interface FormState {
  allow_paid: boolean;
  ollama_enabled: boolean;
  pomodoro_work_min: number;
  pomodoro_break_min: number;
  theme: Theme;
  accent_color: string;
  font_size: number;
}

function toForm(s: Settings): FormState {
  return {
    allow_paid: s.allow_paid,
    ollama_enabled: s.ollama_enabled,
    pomodoro_work_min: s.pomodoro_work_min,
    pomodoro_break_min: s.pomodoro_break_min,
    theme: (s.theme as Theme) ?? "system",
    accent_color: s.accent_color ?? "#6366f1",
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

      <Section title="Appearance">
        <Field label="Theme">
          <select
            className="flex h-9 w-40 rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
            value={form.theme}
            onChange={(e) => set("theme", e.target.value as Theme)}
          >
            <option value="system">System</option>
            <option value="light">Light</option>
            <option value="dark">Dark</option>
          </select>
        </Field>
        <Field label="Accent color">
          <Input
            type="color"
            value={form.accent_color}
            onChange={(e) => set("accent_color", e.target.value)}
            className="h-9 w-16 p-1"
          />
        </Field>
        <Field label="Base font size">
          <Input
            type="number"
            min={10}
            max={32}
            value={form.font_size}
            onChange={(e) => set("font_size", Number(e.target.value))}
            className="w-28"
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

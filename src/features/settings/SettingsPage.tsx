/** Settings page: owns the form state, live preview, scroll-spy, and save/
 *  discard flow, and composes the section cards (sections.tsx) inside the page
 *  chrome (chrome.tsx). The form model + option tables live in form.ts. */

import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { setLanguage } from "@/i18n";
import { applyAppearance, useSettingsStore } from "@/stores/settings";

import { ActionBar, SectionNav, Shell } from "./chrome";
import { SECTIONS, toForm, type FormState } from "./form";
import {
  ApiKeysSection,
  AppearanceSection,
  CalendarSection,
  GenerationSection,
  LanguageSection,
  PomodoroSection,
  ProvidersSection,
} from "./sections";

export function SettingsPage() {
  const navigate = useNavigate();
  const { t } = useTranslation();
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

  // Live preview: reflect appearance + language edits immediately (persisted on Save).
  useEffect(() => {
    if (!form) return;
    applyAppearance({
      theme: form.theme,
      font_size: form.font_size,
      accent_color: form.accent_color || null,
      font_family: form.font_family || null,
    });
    setLanguage(form.language);
  }, [form]);

  // On leaving, snap back to the persisted appearance + language (discard preview).
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
        setLanguage(s.language);
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
        ollama_model: form.ollama_model.trim(),
        gemini_enabled: form.gemini_enabled,
        gemini_rotation: form.gemini_rotation,
        gemini_model: form.gemini_model,
        per_document_token_budget: form.per_document_token_budget,
        note_length: form.note_length,
        study_field: form.study_field,
        ai_style: form.ai_style,
        pomodoro_work_min: form.pomodoro_work_min,
        pomodoro_break_min: form.pomodoro_break_min,
        calendar_day_start_hour: form.calendar_day_start_hour,
        calendar_day_end_hour: form.calendar_day_end_hour,
        calendar_slot_minutes: form.calendar_slot_minutes,
        theme: form.theme,
        accent_color: form.accent_color || null,
        font_family: form.font_family,
        font_size: form.font_size,
        language: form.language,
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
            <h1 className="text-3xl font-bold tracking-tight">
              {t("settings.title")}
            </h1>
            <p className="text-sm text-muted-foreground">
              {t("settings.subtitle")}
            </p>
          </header>

          <ApiKeysSection
            settings={settings}
            geminiKey={geminiKey}
            claudeKey={claudeKey}
            onGeminiKey={(v) => {
              setGeminiKey(v);
              setSaved(false);
            }}
            onClaudeKey={(v) => {
              setClaudeKey(v);
              setSaved(false);
            }}
          />
          <ProvidersSection form={form} set={set} />
          <GenerationSection form={form} set={set} />
          <LanguageSection form={form} set={set} />
          <PomodoroSection form={form} set={set} />
          <CalendarSection form={form} set={set} />
          <AppearanceSection form={form} set={set} />
        </div>
      </div>
    </Shell>
  );
}

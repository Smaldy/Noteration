/** The seven settings section cards. Each renders one `Section` from the
 *  shared form state + `set` patcher; the page composes them in SECTIONS order. */

import { AnimatePresence, motion } from "framer-motion";
import {
  ArrowRight,
  CalendarClock,
  FileText,
  Globe,
  KeyRound,
  Palette,
  Sparkles,
  Timer,
} from "lucide-react";
import { Fragment, useState } from "react";
import { useTranslation } from "react-i18next";

import { Input } from "@/components/ui/input";
import { LANGUAGE_NAMES, SUPPORTED_LANGUAGES, type Language } from "@/i18n";
import { cn } from "@/lib/utils";
import type {
  AIStyle,
  CalendarSlot,
  GeminiModel,
  Settings,
  StudyField,
  Theme,
} from "@/types/settings";

import {
  Field,
  NumberField,
  Section,
  Segmented,
  SetBadge,
  Swatch,
  Toggle,
} from "./controls";
import {
  AI_STYLE_VALUES,
  FONT_OPTIONS,
  FONT_PREVIEW,
  GEMINI_MODELS,
  HEADING_FONT_OPTIONS,
  PRESET_ACCENTS,
  ROTATION_ORDER,
  SLOT_OPTIONS,
  STUDY_FIELD_VALUES,
  hourLabel,
  modelLabel,
  type FormState,
  type SetField,
} from "./form";

// Selected vs. unselected styling shared by every option-card picker below
// (model grid, study-field/style grids, font picker).
const cardState = (active: boolean) =>
  active
    ? "border-primary bg-primary-soft text-primary-soft-foreground shadow-sm"
    : "text-muted-foreground hover:border-ring/40 hover:text-foreground";

export function ApiKeysSection({
  settings,
  geminiKey,
  claudeKey,
  onGeminiKey,
  onClaudeKey,
}: {
  settings: Settings;
  geminiKey: string;
  claudeKey: string;
  onGeminiKey: (v: string) => void;
  onClaudeKey: (v: string) => void;
}) {
  const { t } = useTranslation();
  return (
    <Section
      id="api-keys"
      icon={KeyRound}
      title={t("settings.apiKeys.title")}
      description={t("settings.apiKeys.description")}
      delay={200}
    >
      <Field
        label={t("settings.apiKeys.geminiKey")}
        badge={settings.gemini_key_set ? <SetBadge /> : undefined}
      >
        <Input
          type="password"
          placeholder={
            settings.gemini_key_set
              ? t("settings.apiKeys.placeholderReplace")
              : t("settings.apiKeys.placeholderAdd")
          }
          value={geminiKey}
          onChange={(e) => onGeminiKey(e.target.value)}
        />
      </Field>
      <Field
        label={t("settings.apiKeys.claudeKey")}
        badge={settings.claude_key_set ? <SetBadge /> : undefined}
      >
        <Input
          type="password"
          placeholder={
            settings.claude_key_set
              ? t("settings.apiKeys.placeholderReplace")
              : t("settings.apiKeys.placeholderAdd")
          }
          value={claudeKey}
          onChange={(e) => onClaudeKey(e.target.value)}
        />
      </Field>
    </Section>
  );
}

export function ProvidersSection({
  form,
  set,
}: {
  form: FormState;
  set: SetField;
}) {
  const { t } = useTranslation();
  return (
    <Section
      id="providers"
      icon={Sparkles}
      title={t("settings.providers.title")}
      description={t("settings.providers.description")}
      delay={240}
    >
      <Toggle
        label={t("settings.providers.gemini.label")}
        hint={t("settings.providers.gemini.hint")}
        checked={form.gemini_enabled}
        onChange={(v) => set("gemini_enabled", v)}
      />

      <AnimatePresence initial={false}>
        {form.gemini_enabled ? (
          <motion.div
            key="gemini-config"
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden"
          >
            <div className="space-y-5 rounded-xl border border-border/60 bg-secondary/20 p-4">
              <Toggle
                label={t("settings.providers.gemini.rotation.label")}
                hint={t("settings.providers.gemini.rotation.hint")}
                checked={form.gemini_rotation}
                onChange={(v) => set("gemini_rotation", v)}
              />
              {form.gemini_rotation ? (
                <Field label={t("settings.providers.gemini.rotationOrder")}>
                  <div className="flex flex-wrap items-center gap-1.5">
                    {ROTATION_ORDER.map((value, i) => (
                      <Fragment key={value}>
                        {i > 0 && (
                          <ArrowRight className="size-3.5 shrink-0 text-muted-foreground/50" />
                        )}
                        <span className="rounded-lg border bg-card px-2.5 py-1 text-xs font-medium tabular-nums">
                          {modelLabel(value)}
                        </span>
                      </Fragment>
                    ))}
                  </div>
                  <p className="text-xs text-muted-foreground">
                    {t("settings.providers.gemini.rotationOrderHint")}
                  </p>
                </Field>
              ) : (
                <Field label={t("settings.providers.gemini.pick")}>
                  <ModelGrid
                    value={form.gemini_model}
                    onChange={(v) => set("gemini_model", v)}
                  />
                </Field>
              )}
            </div>
          </motion.div>
        ) : (
          <motion.p
            key="gemini-off"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="text-xs text-muted-foreground"
          >
            {t("settings.providers.gemini.disabledNote")}
          </motion.p>
        )}
      </AnimatePresence>

      <Toggle
        label={t("settings.providers.allowPaid.label")}
        hint={t("settings.providers.allowPaid.hint")}
        checked={form.allow_paid}
        onChange={(v) => set("allow_paid", v)}
      />
      <Field label={t("settings.providers.budget.label")}>
        <NumberField
          min={0}
          step={1000}
          value={form.per_document_token_budget}
          onChange={(v) => set("per_document_token_budget", v)}
          className="w-44"
        />
        <p className="text-xs text-muted-foreground">
          {t("settings.providers.budget.hint")}
        </p>
      </Field>
    </Section>
  );
}

/** 2×2 grid of selectable Gemini model cards (shown when rotation is off). Each
 *  card carries the model name and its tier hint, styled like the font picker. */
function ModelGrid({
  value,
  onChange,
}: {
  value: GeminiModel;
  onChange: (v: GeminiModel) => void;
}) {
  const { t } = useTranslation();
  return (
    <div className="grid grid-cols-2 gap-2 sm:max-w-md">
      {GEMINI_MODELS.map((m) => {
        const active = m.value === value;
        return (
          <button
            key={m.value}
            type="button"
            onClick={() => onChange(m.value)}
            className={cn(
              "rounded-xl border px-3.5 py-2.5 text-left transition-all duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring active:scale-[0.98]",
              cardState(active),
            )}
          >
            <span className="block text-sm font-medium">{m.label}</span>
            <span className="mt-0.5 block text-xs opacity-70">{t(m.hintKey)}</span>
          </button>
        );
      })}
    </div>
  );
}

/** Grid of selectable option cards (label + localized hint) — the ModelGrid
 *  styling generalized for the study-field and writing-style pickers. */
function ChoiceGrid<V extends string>({
  values,
  value,
  onChange,
  i18nBase,
  columns = "grid-cols-2 sm:grid-cols-3",
}: {
  values: readonly V[];
  value: V;
  onChange: (v: V) => void;
  /** i18n prefix; each value reads `${i18nBase}.${value}.label` / `.hint`. */
  i18nBase: string;
  columns?: string;
}) {
  const { t } = useTranslation();
  return (
    <div className={cn("grid gap-2 sm:max-w-2xl", columns)}>
      {values.map((v) => {
        const active = v === value;
        return (
          <button
            key={v}
            type="button"
            onClick={() => onChange(v)}
            className={cn(
              "rounded-xl border px-3 py-2 text-left transition-all duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring active:scale-[0.98]",
              cardState(active),
            )}
          >
            <span className="block text-sm font-medium">
              {t(`${i18nBase}.${v}.label`)}
            </span>
            <span className="mt-0.5 block text-[11px] leading-snug opacity-70">
              {t(`${i18nBase}.${v}.hint`)}
            </span>
          </button>
        );
      })}
    </div>
  );
}

export function GenerationSection({
  form,
  set,
}: {
  form: FormState;
  set: SetField;
}) {
  const { t } = useTranslation();
  return (
    <Section
      id="generation"
      icon={FileText}
      title={t("settings.generation.title")}
      description={t("settings.generation.description")}
      delay={280}
    >
      <Field label={t("settings.generation.studyFieldLabel")}>
        <ChoiceGrid<StudyField>
          values={STUDY_FIELD_VALUES}
          value={form.study_field}
          onChange={(v) => set("study_field", v)}
          i18nBase="settings.generation.fields"
        />
        <p className="text-xs text-muted-foreground">
          {t("settings.generation.studyFieldHint")}
        </p>
      </Field>
      <Field label={t("settings.generation.styleLabel")}>
        <ChoiceGrid<AIStyle>
          values={AI_STYLE_VALUES}
          value={form.ai_style}
          onChange={(v) => set("ai_style", v)}
          i18nBase="settings.generation.styles"
        />
        <p className="text-xs text-muted-foreground">
          {t("settings.generation.styleHint")}
        </p>
      </Field>
      <Field
        label={t("settings.generation.notesLength", {
          count: form.note_length,
        })}
      >
        <div className="flex items-center gap-3">
          <span className="text-xs text-muted-foreground">
            {t("settings.generation.brief")}
          </span>
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
          <span className="text-xs text-muted-foreground">
            {t("settings.generation.detailed")}
          </span>
        </div>
        <p className="text-xs text-muted-foreground">
          {t("settings.generation.explanation")}
        </p>
      </Field>
    </Section>
  );
}

export function LanguageSection({
  form,
  set,
}: {
  form: FormState;
  set: SetField;
}) {
  const { t } = useTranslation();
  return (
    <Section
      id="language"
      icon={Globe}
      title={t("settings.language.title")}
      description={t("settings.language.description")}
      delay={120}
    >
      <Field label={t("settings.language.fieldLabel")}>
        <Segmented
          group="language"
          value={form.language}
          onChange={(v) => set("language", v as Language)}
          options={SUPPORTED_LANGUAGES.map((code) => ({
            value: code,
            label: LANGUAGE_NAMES[code],
          }))}
        />
        <p className="text-xs text-muted-foreground">
          {t("settings.language.hint")}
        </p>
      </Field>
    </Section>
  );
}

export function PomodoroSection({
  form,
  set,
}: {
  form: FormState;
  set: SetField;
}) {
  const { t } = useTranslation();
  return (
    <Section
      id="pomodoro"
      icon={Timer}
      title={t("settings.pomodoro.title")}
      delay={80}
    >
      <div className="flex flex-wrap gap-6">
        <Field label={t("settings.pomodoro.workMinutes")}>
          <NumberField
            min={1}
            max={180}
            value={form.pomodoro_work_min}
            onChange={(v) => set("pomodoro_work_min", v)}
            className="w-32"
          />
        </Field>
        <Field label={t("settings.pomodoro.breakMinutes")}>
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
  );
}

export function CalendarSection({
  form,
  set,
}: {
  form: FormState;
  set: SetField;
}) {
  const { t } = useTranslation();
  return (
    <Section
      id="calendar"
      icon={CalendarClock}
      title={t("settings.calendar.title")}
      description={t("settings.calendar.description")}
      delay={160}
    >
      <div className="flex flex-wrap gap-6">
        <Field label={t("settings.calendar.dayStartsAt")}>
          <NumberField
            min={0}
            max={form.calendar_day_end_hour - 1}
            value={form.calendar_day_start_hour}
            onChange={(v) => set("calendar_day_start_hour", v)}
            className="w-32"
          />
        </Field>
        <Field label={t("settings.calendar.dayEndsAt")}>
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
        {t("settings.calendar.showing", {
          start: hourLabel(form.calendar_day_start_hour),
          end: hourLabel(form.calendar_day_end_hour),
        })}
      </p>
      <Field label={t("settings.calendar.slotSize")}>
        <Segmented
          group="slot"
          value={String(form.calendar_slot_minutes)}
          onChange={(v) => set("calendar_slot_minutes", Number(v) as CalendarSlot)}
          options={SLOT_OPTIONS.map((o) => ({
            value: String(o.value),
            label: t(`settings.calendar.slots.${o.value}`),
          }))}
        />
        <p className="text-xs text-muted-foreground">
          {t("settings.calendar.slotHint")}
        </p>
      </Field>
    </Section>
  );
}

/** Two-target font picker: a Titles/Text switch chooses which role you're
 *  customizing (the active one is colored), and the grid below lists the faces
 *  for that role, each previewed in its own typeface. */
function FontPicker({ form, set }: { form: FormState; set: SetField }) {
  const { t } = useTranslation();
  const [target, setTarget] = useState<"titles" | "text">("titles");
  const forTitles = target === "titles";
  const options = forTitles ? HEADING_FONT_OPTIONS : FONT_OPTIONS;
  const current = forTitles ? form.font_family_heading : form.font_family;

  return (
    <div className="space-y-3">
      <Segmented
        group="font-target"
        value={target}
        onChange={setTarget}
        options={[
          { value: "titles", label: t("settings.appearance.fontTitles") },
          { value: "text", label: t("settings.appearance.fontText") },
        ]}
      />
      <div className="inline-flex flex-wrap gap-2">
        {options.map((f) => (
          <button
            key={f.value}
            type="button"
            onClick={() => set(forTitles ? "font_family_heading" : "font_family", f.value)}
            style={{ fontFamily: FONT_PREVIEW[f.value] }}
            className={cn(
              "rounded-lg border px-3.5 py-2 text-sm transition-all duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring active:scale-95",
              forTitles && "font-semibold",
              cardState(current === f.value),
            )}
          >
            {f.label}
          </button>
        ))}
      </div>
    </div>
  );
}

export function AppearanceSection({
  form,
  set,
}: {
  form: FormState;
  set: SetField;
}) {
  const { t } = useTranslation();
  return (
    <Section
      id="appearance"
      icon={Palette}
      title={t("settings.appearance.title")}
      description={t("settings.appearance.description")}
      delay={40}
    >
      <Field label={t("settings.appearance.theme")}>
        <Segmented
          group="theme"
          value={form.theme}
          onChange={(v) => set("theme", v as Theme)}
          options={(["system", "light", "dark"] as Theme[]).map((th) => ({
            value: th,
            label: t(`settings.appearance.themes.${th}`),
          }))}
        />
      </Field>

      <Field label={t("settings.appearance.accent")}>
        <div className="flex flex-wrap items-center gap-2.5">
          <Swatch
            selected={form.accent_color === ""}
            onClick={() => set("accent_color", "")}
            title={t("settings.appearance.accentDefault")}
            dashed
          />
          {PRESET_ACCENTS.map((c) => (
            <Swatch
              key={c.hex}
              color={c.hex}
              title={t(`settings.appearance.colors.${c.key}`)}
              selected={form.accent_color.toLowerCase() === c.hex.toLowerCase()}
              onClick={() => set("accent_color", c.hex)}
            />
          ))}
          <label
            className="relative ml-1 inline-flex size-8 cursor-pointer items-center justify-center rounded-full border border-dashed border-muted-foreground/50 text-base text-muted-foreground transition-transform hover:scale-110"
            title={t("settings.appearance.accentCustom")}
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

      <Field label={t("settings.appearance.font")}>
        <FontPicker form={form} set={set} />
      </Field>

      <Field
        label={t("settings.appearance.baseFontSize", {
          size: form.font_size,
        })}
      >
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
  );
}

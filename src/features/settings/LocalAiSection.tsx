/** Local AI section: the status-aware setup control (detect → confirm →
 *  install → ready) next to the provider config. Self-contained server state:
 *  it talks to /api/local-ai directly and polls while an install runs, instead
 *  of riding the page's save/discard form flow (setup is a wizard, not a
 *  preference). Only the "prefer quality" toggle writes through the settings
 *  store, since it is a plain persisted setting. */

import {
  Check,
  Copy,
  Cpu,
  Download,
  HardDrive,
  Loader2,
  MonitorCog,
  Moon,
  RefreshCw,
  TriangleAlert,
  Zap,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { api, ApiError } from "@/lib/api";
import { usePolling } from "@/lib/usePolling";
import { cn } from "@/lib/utils";
import { useSettingsStore } from "@/stores/settings";
import type {
  LocalAiStatus,
  ModelChoiceSnapshot,
  SelectionSnapshot,
} from "@/types/localAi";

import { Section, Toggle } from "./controls";

const IN_PROGRESS = new Set(["queued", "installing_ollama", "pulling"]);

function formatBytes(n: number): string {
  if (n >= 1e9) return `${(n / 1e9).toFixed(1)} GB`;
  if (n >= 1e6) return `${Math.round(n / 1e6)} MB`;
  return `${n} B`;
}

/** Sum of the distinct downloads (converged selections pull one model). */
function totalDownloadBytes(selection: SelectionSnapshot): number {
  const seen = new Map<string, number>();
  for (const choice of [selection.quality, selection.fast]) {
    if (choice) seen.set(`${choice.tag}@${choice.quant}`, choice.download_bytes);
  }
  return [...seen.values()].reduce((a, b) => a + b, 0);
}

export function LocalAiSection() {
  const { t } = useTranslation();
  const [status, setStatus] = useState<LocalAiStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setStatus(await api.get<LocalAiStatus>("/local-ai/status"));
    } catch {
      // Transient poll failure; the next tick retries.
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  // Live progress while the worker installs/pulls; quiet otherwise.
  usePolling(refresh, 1500, {
    enabled: status !== null && IN_PROGRESS.has(status.status),
    immediate: false,
  });

  async function run(action: () => Promise<LocalAiStatus>) {
    setBusy(true);
    setActionError(null);
    try {
      setStatus(await action());
    } catch (e) {
      setActionError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  const detect = () => run(() => api.post<LocalAiStatus>("/local-ai/detect"));
  const install = () => run(() => api.post<LocalAiStatus>("/local-ai/install", {}));
  const reset = () => {
    if (window.confirm(t("settings.localAi.ready.removeConfirm"))) {
      void run(() => api.post<LocalAiStatus>("/local-ai/reset"));
    }
  };

  return (
    <Section
      id="local-ai"
      icon={Cpu}
      title={t("settings.localAi.title")}
      description={t("settings.localAi.description")}
      delay={260}
    >
      {status === null ? (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="size-4 animate-spin" />
          {t("common.loading")}
        </div>
      ) : (
        <>
          {status.status === "not_configured" && (
            <NotConfigured status={status} busy={busy} onDetect={detect} />
          )}
          {status.status === "detected" && (
            <Detected
              status={status}
              busy={busy}
              onInstall={install}
              onRedetect={detect}
            />
          )}
          {IN_PROGRESS.has(status.status) && <InProgress status={status} />}
          {status.status === "ready" && (
            <Ready status={status} busy={busy} onRedetect={detect} onRemove={reset} />
          )}
          {status.status === "failed" && (
            <Failed
              status={status}
              busy={busy}
              onRetry={install}
              onRedetect={detect}
            />
          )}
          {actionError && (
            <p className="text-xs text-destructive" role="alert">
              {actionError}
            </p>
          )}
          <LocalModelsPanel status={status} />
        </>
      )}
    </Section>
  );
}

/** Manual control over which installed Ollama model serves which role. The
 *  pickers list the models actually present on this computer (no typing tag
 *  names); changes persist immediately. "Always use" overrides both roles and
 *  defaults to none. */
function LocalModelsPanel({ status }: { status: LocalAiStatus }) {
  const { t } = useTranslation();
  const { settings, updateSettings } = useSettingsStore();
  if (!settings) return null;
  // Union of what Ollama reports and what's currently assigned, so a value
  // set elsewhere (or while Ollama is stopped) still shows in its picker.
  const options = [
    ...new Set(
      [
        ...status.ollama.installed_models,
        settings.ollama_fast_model,
        settings.ollama_quality_model,
        settings.ollama_always_model,
        settings.ollama_model,
      ].filter((m): m is string => !!m),
    ),
  ];
  if (options.length === 0 && !status.ollama.binary_present) return null;

  const NONE = "__none__";
  const pick = (field: string) => (value: string) =>
    void updateSettings({ [field]: value === NONE ? "" : value });

  const rolePicker = (
    field: "ollama_fast_model" | "ollama_quality_model" | "ollama_always_model",
    labelKey: string,
  ) => (
    <div className="flex flex-col gap-1.5">
      <span className="text-xs font-medium text-muted-foreground">
        {t(labelKey)}
      </span>
      <Select value={settings[field] ?? NONE} onValueChange={pick(field)}>
        <SelectTrigger className="w-56 max-w-full">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={NONE}>
            {t("settings.localAi.models.none")}
          </SelectItem>
          {options.map((m) => (
            <SelectItem key={m} value={m}>
              {m}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );

  return (
    <div className="space-y-4 rounded-xl border border-border/60 bg-secondary/20 p-4">
      <div>
        <p className="text-sm font-medium">{t("settings.localAi.models.title")}</p>
        <p className="text-xs text-muted-foreground">
          {t("settings.localAi.models.hint")}
        </p>
      </div>
      <Toggle
        label={t("settings.localAi.models.enable.label")}
        hint={t("settings.localAi.models.enable.hint")}
        checked={settings.ollama_enabled}
        onChange={(v) => void updateSettings({ ollama_enabled: v })}
      />
      {options.length === 0 ? (
        <p className="text-xs text-muted-foreground">
          {t("settings.localAi.models.empty")}
        </p>
      ) : (
        <>
          <div className="flex flex-wrap gap-4">
            {rolePicker("ollama_fast_model", "settings.localAi.models.fastLabel")}
            {rolePicker("ollama_quality_model", "settings.localAi.models.slowLabel")}
            {rolePicker("ollama_always_model", "settings.localAi.models.alwaysLabel")}
          </div>
          <p className="text-xs text-muted-foreground">
            {t("settings.localAi.models.alwaysHint")}
          </p>
        </>
      )}
    </div>
  );
}

function NotConfigured({
  status,
  busy,
  onDetect,
}: {
  status: LocalAiStatus;
  busy: boolean;
  onDetect: () => void;
}) {
  const { t } = useTranslation();
  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">
        {t("settings.localAi.notSetUp.lead")}
      </p>
      <OllamaChip status={status} />
      <Button onClick={onDetect} disabled={busy}>
        {busy ? (
          <Loader2 className="size-4 animate-spin" />
        ) : (
          <MonitorCog className="size-4" />
        )}
        {busy
          ? t("settings.localAi.notSetUp.detecting")
          : t("settings.localAi.notSetUp.detect")}
      </Button>
    </div>
  );
}

function OllamaChip({ status }: { status: LocalAiStatus }) {
  const { t } = useTranslation();
  const { binary_present, server_reachable } = status.ollama;
  const key = server_reachable
    ? "running"
    : binary_present
      ? "installed"
      : "missing";
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs",
        key === "missing"
          ? "border-border text-muted-foreground"
          : "border-emerald-500/40 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400",
      )}
    >
      <HardDrive className="size-3.5" />
      {t(`settings.localAi.ollama.${key}`)}
    </span>
  );
}

/** The Stage 5 confirm screen: what was detected, what will be installed,
 *  how big the download is, and the low-confidence override escape hatch. */
function Detected({
  status,
  busy,
  onInstall,
  onRedetect,
}: {
  status: LocalAiStatus;
  busy: boolean;
  onInstall: () => void;
  onRedetect: () => void;
}) {
  const { t } = useTranslation();
  const hardware = status.hardware;
  const selection = status.selection;
  if (!hardware || !selection) return null;
  const noModels = !selection.quality && !selection.fast;

  return (
    <div className="space-y-5">
      <DetectionSummary status={status} />

      {noModels ? (
        <MessageList messages={selection.messages} tone="warn" />
      ) : (
        <>
          <div className="grid gap-2 sm:grid-cols-2">
            {selection.converged && selection.quality ? (
              <ModelCard choice={selection.quality} role="both" />
            ) : (
              <>
                {selection.quality && (
                  <ModelCard choice={selection.quality} role="quality" />
                )}
                {selection.fast && <ModelCard choice={selection.fast} role="fast" />}
              </>
            )}
          </div>
          <MessageList messages={selection.messages} tone="info" />
          <p className="flex items-center gap-2 text-sm">
            <Download className="size-4 text-muted-foreground" />
            {t("settings.localAi.detected.download", {
              size: formatBytes(totalDownloadBytes(selection)),
            })}
          </p>
          {!status.ollama.binary_present && (
            <p className="text-xs text-muted-foreground">
              {t("settings.localAi.detected.elevationNote")}
            </p>
          )}
          <ManualInstall status={status} />
          <div className="flex flex-wrap items-center gap-2">
            <Button onClick={onInstall} disabled={busy}>
              {busy && <Loader2 className="size-4 animate-spin" />}
              {t("settings.localAi.detected.install")}
            </Button>
            <Button variant="outline" onClick={onRedetect} disabled={busy}>
              <RefreshCw className="size-4" />
              {t("settings.localAi.detected.redetect")}
            </Button>
            <CopyReportButton status={status} />
          </div>
        </>
      )}
    </div>
  );
}

function DetectionSummary({ status }: { status: LocalAiStatus }) {
  const { t } = useTranslation();
  const hardware = status.hardware;
  if (!hardware) return null;
  const facts: [string, string][] = [
    [
      t("settings.localAi.detected.gpu"),
      hardware.gpu_name ??
        (hardware.graphics_class === "cpu_only"
          ? t("settings.localAi.detected.noGpu")
          : (hardware.gpu_vendor ?? t("settings.localAi.detected.unknownGpu"))),
    ],
    [
      t("settings.localAi.detected.memoryForModels"),
      formatBytes(hardware.usable_memory_bytes),
    ],
  ];
  if (hardware.vram_bytes != null) {
    facts.splice(1, 0, [
      t("settings.localAi.detected.vram"),
      formatBytes(hardware.vram_bytes),
    ]);
  }
  if (hardware.ram_bytes != null) {
    facts.push([t("settings.localAi.detected.ram"), formatBytes(hardware.ram_bytes)]);
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-x-6 gap-y-2 rounded-xl border border-border/60 bg-secondary/20 p-4">
        {facts.map(([label, value]) => (
          <div key={label}>
            <p className="text-[11px] uppercase tracking-wide text-muted-foreground">
              {label}
            </p>
            <p className="text-sm font-medium">{value}</p>
          </div>
        ))}
      </div>
      {hardware.confidence === "low" && (
        <p className="flex items-start gap-2 rounded-lg border border-amber-500/40 bg-amber-500/10 p-3 text-xs text-amber-700 dark:text-amber-400">
          <TriangleAlert className="mt-0.5 size-4 shrink-0" />
          {t("settings.localAi.detected.lowConfidence")}
        </p>
      )}
      {hardware.notes.map((note) => (
        <p key={note} className="text-xs text-muted-foreground">
          {note}
        </p>
      ))}
    </div>
  );
}

function ModelCard({
  choice,
  role,
}: {
  choice: ModelChoiceSnapshot;
  role: "quality" | "fast" | "both";
}) {
  const { t } = useTranslation();
  const Icon = role === "fast" ? Zap : Moon;
  return (
    <div className="rounded-xl border border-border/60 p-4">
      <p className="flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
        <Icon className="size-3.5" />
        {t(`settings.localAi.roles.${role}.title`)}
      </p>
      <p className="mt-1 text-sm font-semibold">{choice.display}</p>
      <p className="text-xs text-muted-foreground">
        {choice.tag} · {formatBytes(choice.download_bytes)} ·{" "}
        {t("settings.localAi.detected.estSpeed", {
          speed: Math.round(choice.est_tok_s),
        })}
      </p>
      <p className="mt-1.5 text-xs opacity-80">
        {t(`settings.localAi.roles.${role}.hint`)}
      </p>
    </div>
  );
}

function MessageList({
  messages,
  tone,
}: {
  messages: string[];
  tone: "info" | "warn";
}) {
  if (messages.length === 0) return null;
  return (
    <div
      className={cn(
        "space-y-1 rounded-lg border p-3 text-xs",
        tone === "warn"
          ? "border-amber-500/40 bg-amber-500/10 text-amber-700 dark:text-amber-400"
          : "border-border/60 bg-secondary/20 text-muted-foreground",
      )}
    >
      {messages.map((m) => (
        <p key={m}>{m}</p>
      ))}
    </div>
  );
}

/** The type-it-yourself alternative to the elevated automatic install. */
function ManualInstall({ status }: { status: LocalAiStatus }) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const commands = status.manual_commands.filter((c) => !c.startsWith("#"));
  if (status.ollama.binary_present) return null;
  return (
    <div>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="text-xs font-medium text-primary hover:underline"
      >
        {t("settings.localAi.manual.title")}
      </button>
      {open && (
        <div className="mt-2 space-y-2">
          <p className="text-xs text-muted-foreground">
            {t("settings.localAi.manual.hint")}
          </p>
          {commands.map((command) => (
            <CopyableCommand key={command} command={command} />
          ))}
        </div>
      )}
    </div>
  );
}

function CopyableCommand({ command }: { command: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="flex items-center gap-2 rounded-lg border border-border/60 bg-secondary/30 px-3 py-2">
      <code className="min-w-0 flex-1 overflow-x-auto whitespace-nowrap text-xs">
        {command}
      </code>
      <button
        type="button"
        className="shrink-0 text-muted-foreground transition-colors hover:text-foreground"
        onClick={() => {
          void navigator.clipboard.writeText(command).then(() => {
            setCopied(true);
            setTimeout(() => setCopied(false), 1500);
          });
        }}
      >
        {copied ? <Check className="size-4" /> : <Copy className="size-4" />}
      </button>
    </div>
  );
}

function CopyReportButton({ status }: { status: LocalAiStatus }) {
  const { t } = useTranslation();
  const [copied, setCopied] = useState(false);
  return (
    <Button
      variant="ghost"
      onClick={() => {
        const report = JSON.stringify(
          { hardware: status.hardware, selection: status.selection },
          null,
          2,
        );
        void navigator.clipboard.writeText(report).then(() => {
          setCopied(true);
          setTimeout(() => setCopied(false), 1500);
        });
      }}
    >
      {copied ? <Check className="size-4" /> : <Copy className="size-4" />}
      {copied
        ? t("settings.localAi.detected.copied")
        : t("settings.localAi.detected.copyReport")}
    </Button>
  );
}

function InProgress({ status }: { status: LocalAiStatus }) {
  const { t } = useTranslation();
  const pulling = status.status === "pulling" && status.pull_total > 0;
  const percent = pulling
    ? Math.min(100, Math.round((status.pull_completed / status.pull_total) * 100))
    : null;
  const label =
    status.status === "pulling"
      ? t("settings.localAi.progress.pulling", { tag: status.pull_tag ?? "" })
      : t(`settings.localAi.progress.${status.status}`);
  return (
    <div className="space-y-3">
      <p className="flex items-center gap-2 text-sm">
        <Loader2 className="size-4 animate-spin text-primary" />
        {label}
      </p>
      {pulling && percent !== null && (
        <div className="space-y-1.5">
          <div className="h-2 overflow-hidden rounded-full bg-secondary">
            <div
              className="h-full rounded-full bg-primary transition-all duration-500"
              style={{ width: `${percent}%` }}
            />
          </div>
          <p className="text-xs tabular-nums text-muted-foreground">
            {formatBytes(status.pull_completed)} / {formatBytes(status.pull_total)} ·{" "}
            {percent}%
          </p>
        </div>
      )}
      <p className="text-xs text-muted-foreground">
        {t("settings.localAi.progress.backgroundNote")}
      </p>
    </div>
  );
}

function Ready({
  status,
  busy,
  onRedetect,
  onRemove,
}: {
  status: LocalAiStatus;
  busy: boolean;
  onRedetect: () => void;
  onRemove: () => void;
}) {
  const { t } = useTranslation();
  const { settings, updateSettings } = useSettingsStore();
  const converged =
    status.quality_model !== null && status.quality_model === status.fast_model;

  return (
    <div className="space-y-4">
      <p className="flex items-center gap-2 text-sm font-medium text-emerald-600 dark:text-emerald-400">
        <Check className="size-4" />
        {t("settings.localAi.ready.title")}
      </p>
      <div className="space-y-2">
        {converged ? (
          <InstalledRow role="both" tag={status.quality_model} />
        ) : (
          <>
            <InstalledRow role="quality" tag={status.quality_model} />
            <InstalledRow role="fast" tag={status.fast_model} />
          </>
        )}
      </div>
      {!converged && (
        <Toggle
          label={t("settings.localAi.ready.preferQuality.label")}
          hint={t("settings.localAi.ready.preferQuality.hint")}
          checked={settings?.ollama_prefer_quality ?? false}
          onChange={(v) => void updateSettings({ ollama_prefer_quality: v })}
        />
      )}
      <div className="flex flex-wrap gap-2">
        <Button variant="outline" onClick={onRedetect} disabled={busy}>
          <RefreshCw className="size-4" />
          {t("settings.localAi.ready.redetect")}
        </Button>
        <Button variant="ghost" onClick={onRemove} disabled={busy}>
          {t("settings.localAi.ready.remove")}
        </Button>
      </div>
    </div>
  );
}

function InstalledRow({
  role,
  tag,
}: {
  role: "quality" | "fast" | "both";
  tag: string | null;
}) {
  const { t } = useTranslation();
  if (!tag) return null;
  const Icon = role === "fast" ? Zap : Moon;
  return (
    <div className="flex items-center gap-3 rounded-lg border border-border/60 px-3 py-2">
      <Icon className="size-4 text-muted-foreground" />
      <div className="min-w-0">
        <p className="truncate text-sm font-medium">{tag}</p>
        <p className="text-xs text-muted-foreground">
          {t(`settings.localAi.roles.${role}.hint`)}
        </p>
      </div>
    </div>
  );
}

function Failed({
  status,
  busy,
  onRetry,
  onRedetect,
}: {
  status: LocalAiStatus;
  busy: boolean;
  onRetry: () => void;
  onRedetect: () => void;
}) {
  const { t } = useTranslation();
  return (
    <div className="space-y-4">
      <p className="flex items-start gap-2 rounded-lg border border-destructive/40 bg-destructive/10 p-3 text-xs text-destructive">
        <TriangleAlert className="mt-0.5 size-4 shrink-0" />
        {status.error ?? t("settings.localAi.failed.title")}
      </p>
      <ManualInstall status={status} />
      <div className="flex flex-wrap gap-2">
        <Button onClick={onRetry} disabled={busy}>
          {busy && <Loader2 className="size-4 animate-spin" />}
          {t("settings.localAi.failed.retry")}
        </Button>
        <Button variant="outline" onClick={onRedetect} disabled={busy}>
          <RefreshCw className="size-4" />
          {t("settings.localAi.detected.redetect")}
        </Button>
      </div>
    </div>
  );
}

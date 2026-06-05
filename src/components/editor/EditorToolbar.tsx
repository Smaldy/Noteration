import type { Editor } from "@tiptap/react";
import {
  Bold,
  Code,
  Heading1,
  Heading2,
  Heading3,
  Highlighter,
  Italic,
  List,
  ListOrdered,
  Quote,
  Redo2,
  RemoveFormatting,
  Sigma,
  Strikethrough,
  Type,
  Underline as UnderlineIcon,
  Undo2,
} from "lucide-react";
import { type ReactNode, useState } from "react";
import { useTranslation } from "react-i18next";

import { cn } from "@/lib/utils";
import { FONT_STACKS } from "@/stores/settings";

/** Word/Docs-style formatting bar driving the TipTap editor commands. */
export function EditorToolbar({ editor }: { editor: Editor }) {
  const { t } = useTranslation();
  return (
    <div className="sticky top-0 z-10 flex flex-wrap items-center gap-0.5 rounded-t-lg border-b bg-muted/60 px-2 py-1.5 backdrop-blur">
      <Btn
        label={t("editor.bold")}
        active={editor.isActive("bold")}
        onClick={() => editor.chain().focus().toggleBold().run()}
      >
        <Bold className="size-4" />
      </Btn>
      <Btn
        label={t("editor.italic")}
        active={editor.isActive("italic")}
        onClick={() => editor.chain().focus().toggleItalic().run()}
      >
        <Italic className="size-4" />
      </Btn>
      <Btn
        label={t("editor.underline")}
        active={editor.isActive("underline")}
        onClick={() => editor.chain().focus().toggleUnderline().run()}
      >
        <UnderlineIcon className="size-4" />
      </Btn>
      <Btn
        label={t("editor.strikethrough")}
        active={editor.isActive("strike")}
        onClick={() => editor.chain().focus().toggleStrike().run()}
      >
        <Strikethrough className="size-4" />
      </Btn>

      <Divider />

      <Btn
        label={t("editor.heading1")}
        active={editor.isActive("heading", { level: 1 })}
        onClick={() => editor.chain().focus().toggleHeading({ level: 1 }).run()}
      >
        <Heading1 className="size-4" />
      </Btn>
      <Btn
        label={t("editor.heading2")}
        active={editor.isActive("heading", { level: 2 })}
        onClick={() => editor.chain().focus().toggleHeading({ level: 2 }).run()}
      >
        <Heading2 className="size-4" />
      </Btn>
      <Btn
        label={t("editor.heading3")}
        active={editor.isActive("heading", { level: 3 })}
        onClick={() => editor.chain().focus().toggleHeading({ level: 3 }).run()}
      >
        <Heading3 className="size-4" />
      </Btn>

      <Divider />

      <Btn
        label={t("editor.bulletList")}
        active={editor.isActive("bulletList")}
        onClick={() => editor.chain().focus().toggleBulletList().run()}
      >
        <List className="size-4" />
      </Btn>
      <Btn
        label={t("editor.numberedList")}
        active={editor.isActive("orderedList")}
        onClick={() => editor.chain().focus().toggleOrderedList().run()}
      >
        <ListOrdered className="size-4" />
      </Btn>
      <Btn
        label={t("editor.quote")}
        active={editor.isActive("blockquote")}
        onClick={() => editor.chain().focus().toggleBlockquote().run()}
      >
        <Quote className="size-4" />
      </Btn>
      <Btn
        label={t("editor.codeBlock")}
        active={editor.isActive("codeBlock")}
        onClick={() => editor.chain().focus().toggleCodeBlock().run()}
      >
        <Code className="size-4" />
      </Btn>

      <Divider />

      <FontControl editor={editor} />
      <ColorControl editor={editor} />
      <HighlightControl editor={editor} />

      <Divider />

      <Btn
        label={t("editor.insertMath")}
        onClick={() => {
          editor.chain().focus().insertContent("$x$").run();
        }}
      >
        <Sigma className="size-4" />
      </Btn>
      <Btn
        label={t("editor.clearFormatting")}
        onClick={() =>
          editor.chain().focus().unsetAllMarks().clearNodes().run()
        }
      >
        <RemoveFormatting className="size-4" />
      </Btn>

      <Divider />

      <Btn
        label={t("editor.undo")}
        disabled={!editor.can().undo()}
        onClick={() => editor.chain().focus().undo().run()}
      >
        <Undo2 className="size-4" />
      </Btn>
      <Btn
        label={t("editor.redo")}
        disabled={!editor.can().redo()}
        onClick={() => editor.chain().focus().redo().run()}
      >
        <Redo2 className="size-4" />
      </Btn>
    </div>
  );
}

// Font options for the per-selection override. "Default" clears the mark so the
// text falls back to the user's Settings font; the rest reuse the app's bundled
// font stacks so a picked face renders without any network fetch.
const FONT_OPTIONS: { label: string; value: string | null }[] = [
  { label: "Default (settings font)", value: null },
  { label: "Sans", value: FONT_STACKS.sans },
  { label: "Serif", value: FONT_STACKS.serif },
  { label: "Mono", value: FONT_STACKS.mono },
  { label: "Inter", value: FONT_STACKS.inter },
  { label: "System", value: FONT_STACKS.system },
];

/** Font-family control: apply one of the bundled faces to the selection, or
 *  reset to the user's default Settings font. */
function FontControl({ editor }: { editor: Editor }) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const current = (editor.getAttributes("textStyle").fontFamily as string) || "";

  const apply = (value: string | null) => {
    if (value) editor.chain().focus().setFontFamily(value).run();
    else editor.chain().focus().unsetFontFamily().run();
    setOpen(false);
  };

  return (
    <div className="relative">
      <Btn
        label={t("editor.font")}
        active={!!current}
        onClick={() => setOpen((o) => !o)}
      >
        <Type className="size-4" />
      </Btn>
      {open && (
        <>
          <div
            className="fixed inset-0 z-20"
            onClick={() => setOpen(false)}
            aria-hidden
          />
          <div className="absolute left-0 top-full z-30 mt-1 w-52 rounded-lg border bg-popover p-1 shadow-md">
            {FONT_OPTIONS.map((opt) => {
              const active = (opt.value || "") === current;
              return (
                <button
                  key={opt.label}
                  type="button"
                  onClick={() => apply(opt.value)}
                  style={opt.value ? { fontFamily: opt.value } : undefined}
                  className={cn(
                    "block w-full rounded-md px-2.5 py-1.5 text-left text-sm transition hover:bg-muted",
                    active && "bg-muted text-primary",
                  )}
                >
                  {opt.value === null ? t("editor.fontDefault") : opt.label}
                </button>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}

// ── Shared popover building blocks ─────────────────────────────────────────
// Both the font-colour and highlight controls share one visual language: a
// frosted, softly-shadowed panel; a titled section; round swatches with a clear
// selected ring; and a custom-colour + reset footer. Keeping them identical is
// what makes the toolbar read as "designed" rather than two ad-hoc menus.

/** Dismiss-on-outside-click popover panel anchored under its trigger. */
function Popover({
  open,
  onClose,
  children,
}: {
  open: boolean;
  onClose: () => void;
  children: ReactNode;
}) {
  if (!open) return null;
  return (
    <>
      <div className="fixed inset-0 z-20" onClick={onClose} aria-hidden />
      <div
        className={cn(
          "absolute left-0 top-full z-30 mt-2 w-60 origin-top-left rounded-xl border border-border/70 bg-popover/95 p-3 backdrop-blur",
          "shadow-[0_18px_44px_-18px_color-mix(in_oklab,var(--primary)_28%,transparent),0_6px_16px_-10px_rgb(0_0_0/0.18)]",
          "animate-in fade-in-0 zoom-in-95 duration-150",
        )}
      >
        {children}
      </div>
    </>
  );
}

/** Small uppercase section label in the display face. */
function PanelLabel({ children }: { children: ReactNode }) {
  return (
    <p className="mb-2 font-display text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">
      {children}
    </p>
  );
}

/** A round colour chip with a subtle definition border and a clear selected ring. */
function Swatch({
  color,
  selected,
  title,
  onClick,
}: {
  color: string;
  selected: boolean;
  title: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      title={title}
      aria-pressed={selected}
      onClick={onClick}
      style={{ backgroundColor: color }}
      className={cn(
        "aspect-square w-full rounded-full border border-black/10 transition dark:border-white/20",
        "hover:scale-110 hover:border-black/25 dark:hover:border-white/30",
        selected &&
          "ring-2 ring-ring ring-offset-2 ring-offset-popover hover:scale-105",
      )}
    />
  );
}

/** Footer: a circular native-colour trigger ("Custom") + a quiet reset action. */
function PanelFooter({
  color,
  onPick,
  resetLabel,
  onReset,
}: {
  color: string;
  onPick: (hex: string) => void;
  resetLabel: string;
  onReset: () => void;
}) {
  const { t } = useTranslation();
  return (
    <>
      <div className="my-2.5 h-px bg-border/70" />
      <div className="flex items-center justify-between">
        <label className="group flex cursor-pointer items-center gap-2 text-xs font-medium text-muted-foreground transition hover:text-foreground">
          <span
            className="relative inline-block size-5 overflow-hidden rounded-full border border-black/10 transition group-hover:scale-110 dark:border-white/20"
            style={{ backgroundColor: color }}
          >
            <input
              type="color"
              value={color}
              onChange={(e) => onPick(e.target.value)}
              className="absolute inset-0 size-full cursor-pointer opacity-0"
            />
          </span>
          {t("editor.custom")}
        </label>
        <button
          type="button"
          className="rounded-md px-2 py-1 text-xs font-medium text-muted-foreground transition hover:bg-secondary hover:text-foreground"
          onClick={onReset}
        >
          {resetLabel}
        </button>
      </div>
    </>
  );
}

// ── Font colour ────────────────────────────────────────────────────────────
const SWATCHES = [
  "#ef4444",
  "#f97316",
  "#eab308",
  "#22c55e",
  "#0ea5e9",
  "#6366f1",
  "#a855f7",
  "#ec4899",
];

/** Font-color control: a row of swatches, a native picker, and a reset. */
function ColorControl({ editor }: { editor: Editor }) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const active = (editor.getAttributes("textStyle").color as string) || "";
  const indicator = active || "currentColor";

  const apply = (c: string) => {
    editor.chain().focus().setColor(c).run();
    setOpen(false);
  };

  return (
    <div className="relative">
      <Btn label={t("editor.fontColor")} active={!!active} onClick={() => setOpen((o) => !o)}>
        <span className="flex flex-col items-center leading-none">
          <span className="text-[13px] font-semibold">A</span>
          <span
            className="mt-0.5 h-1 w-4 rounded-full"
            style={{ backgroundColor: indicator }}
          />
        </span>
      </Btn>
      <Popover open={open} onClose={() => setOpen(false)}>
        <PanelLabel>{t("editor.textColor")}</PanelLabel>
        <div className="grid grid-cols-8 gap-1.5">
          {SWATCHES.map((c) => (
            <Swatch
              key={c}
              color={c}
              title={c}
              selected={active.toLowerCase() === c.toLowerCase()}
              onClick={() => apply(c)}
            />
          ))}
        </div>
        <PanelFooter
          color={active || "#6366f1"}
          onPick={(hex) => editor.chain().focus().setColor(hex).run()}
          resetLabel={t("editor.reset")}
          onReset={() => {
            editor.chain().focus().unsetColor().run();
            setOpen(false);
          }}
        />
      </Popover>
    </div>
  );
}

// ── Highlight ──────────────────────────────────────────────────────────────
// The swatches are base hues; the chosen opacity is mixed in when the mark is
// applied, so one colour spans a faint wash to a bold marker.
const HIGHLIGHT_SWATCHES = [
  "#facc15",
  "#fb923c",
  "#f87171",
  "#4ade80",
  "#38bdf8",
  "#818cf8",
  "#c084fc",
  "#f472b6",
];

/** Convert a `#rrggbb` hex + 0–1 alpha to an `rgba()` string TipTap stores on the mark. */
function hexToRgba(hex: string, alpha: number): string {
  const n = Number.parseInt(hex.slice(1), 16);
  const r = (n >> 16) & 255;
  const g = (n >> 8) & 255;
  const b = n & 255;
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

/** Highlight control: pick a color and an opacity (default 80%), with a live
 *  preview of the resulting marker. Applies the blended color as the mark's color. */
function HighlightControl({ editor }: { editor: Editor }) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  // Default 80% per spec; remembered across openings within the editing session.
  const [opacity, setOpacity] = useState(0.8);
  const [color, setColor] = useState(HIGHLIGHT_SWATCHES[0]);
  const blended = hexToRgba(color, opacity);

  const apply = (hex: string) => {
    setColor(hex);
    editor.chain().focus().setHighlight({ color: hexToRgba(hex, opacity) }).run();
  };

  const setOpacityLive = (next: number) => {
    setOpacity(next);
    // Re-apply to a live selection so dragging previews directly on the text.
    if (editor.isActive("highlight")) {
      editor.chain().focus().setHighlight({ color: hexToRgba(color, next) }).run();
    }
  };

  return (
    <div className="relative">
      <Btn
        label={t("editor.highlight")}
        active={editor.isActive("highlight")}
        onClick={() => setOpen((o) => !o)}
      >
        <span className="flex flex-col items-center leading-none">
          <Highlighter className="size-[15px]" />
          <span
            className="mt-0.5 h-1 w-4 rounded-full"
            style={{ backgroundColor: blended }}
          />
        </span>
      </Btn>
      <Popover open={open} onClose={() => setOpen(false)}>
        <PanelLabel>{t("editor.highlightColor")}</PanelLabel>
        <div className="grid grid-cols-8 gap-1.5">
          {HIGHLIGHT_SWATCHES.map((c) => (
            <Swatch
              key={c}
              color={hexToRgba(c, opacity)}
              title={c}
              selected={color.toLowerCase() === c.toLowerCase()}
              onClick={() => apply(c)}
            />
          ))}
        </div>

        <div className="mt-3 flex items-center justify-between text-[11px] font-medium text-muted-foreground">
          <span className="font-display uppercase tracking-[0.14em]">{t("editor.opacity")}</span>
          <span className="tabular-nums text-foreground/80">
            {Math.round(opacity * 100)}%
          </span>
        </div>
        <input
          type="range"
          min={10}
          max={100}
          step={5}
          value={Math.round(opacity * 100)}
          onChange={(e) => setOpacityLive(Number(e.target.value) / 100)}
          className="app-range mt-1.5"
          aria-label="Highlight opacity"
        />

        <div
          className="mt-3 rounded-lg border border-border/60 px-2.5 py-2 text-center text-sm"
          style={{ backgroundColor: "color-mix(in oklab, var(--muted) 40%, transparent)" }}
        >
          <span
            className="rounded px-1.5 py-0.5"
            style={{ backgroundColor: blended }}
          >
            {t("editor.highlightedText")}
          </span>
        </div>

        <PanelFooter
          color={color}
          onPick={apply}
          resetLabel={t("editor.removeHighlight")}
          onReset={() => {
            editor.chain().focus().unsetHighlight().run();
            setOpen(false);
          }}
        />
      </Popover>
    </div>
  );
}

function Btn({
  children,
  label,
  active = false,
  disabled = false,
  onClick,
}: {
  children: ReactNode;
  label: string;
  active?: boolean;
  disabled?: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      title={label}
      aria-label={label}
      aria-pressed={active}
      disabled={disabled}
      onClick={onClick}
      className={cn(
        "inline-flex size-8 items-center justify-center rounded-md text-foreground/80 transition",
        "hover:bg-background hover:text-foreground",
        "disabled:pointer-events-none disabled:opacity-40",
        active && "bg-background text-primary shadow-sm",
      )}
    >
      {children}
    </button>
  );
}

function Divider() {
  return <span className="mx-1 h-5 w-px shrink-0 bg-border" />;
}

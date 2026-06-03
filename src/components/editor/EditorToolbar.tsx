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
  Underline as UnderlineIcon,
  Undo2,
} from "lucide-react";
import { type ReactNode, useState } from "react";

import { cn } from "@/lib/utils";

/** Word/Docs-style formatting bar driving the TipTap editor commands. */
export function EditorToolbar({ editor }: { editor: Editor }) {
  return (
    <div className="sticky top-0 z-10 flex flex-wrap items-center gap-0.5 rounded-t-lg border-b bg-muted/60 px-2 py-1.5 backdrop-blur">
      <Btn
        label="Bold"
        active={editor.isActive("bold")}
        onClick={() => editor.chain().focus().toggleBold().run()}
      >
        <Bold className="size-4" />
      </Btn>
      <Btn
        label="Italic"
        active={editor.isActive("italic")}
        onClick={() => editor.chain().focus().toggleItalic().run()}
      >
        <Italic className="size-4" />
      </Btn>
      <Btn
        label="Underline"
        active={editor.isActive("underline")}
        onClick={() => editor.chain().focus().toggleUnderline().run()}
      >
        <UnderlineIcon className="size-4" />
      </Btn>
      <Btn
        label="Strikethrough"
        active={editor.isActive("strike")}
        onClick={() => editor.chain().focus().toggleStrike().run()}
      >
        <Strikethrough className="size-4" />
      </Btn>

      <Divider />

      <Btn
        label="Heading 1"
        active={editor.isActive("heading", { level: 1 })}
        onClick={() => editor.chain().focus().toggleHeading({ level: 1 }).run()}
      >
        <Heading1 className="size-4" />
      </Btn>
      <Btn
        label="Heading 2"
        active={editor.isActive("heading", { level: 2 })}
        onClick={() => editor.chain().focus().toggleHeading({ level: 2 }).run()}
      >
        <Heading2 className="size-4" />
      </Btn>
      <Btn
        label="Heading 3"
        active={editor.isActive("heading", { level: 3 })}
        onClick={() => editor.chain().focus().toggleHeading({ level: 3 }).run()}
      >
        <Heading3 className="size-4" />
      </Btn>

      <Divider />

      <Btn
        label="Bullet list"
        active={editor.isActive("bulletList")}
        onClick={() => editor.chain().focus().toggleBulletList().run()}
      >
        <List className="size-4" />
      </Btn>
      <Btn
        label="Numbered list"
        active={editor.isActive("orderedList")}
        onClick={() => editor.chain().focus().toggleOrderedList().run()}
      >
        <ListOrdered className="size-4" />
      </Btn>
      <Btn
        label="Quote"
        active={editor.isActive("blockquote")}
        onClick={() => editor.chain().focus().toggleBlockquote().run()}
      >
        <Quote className="size-4" />
      </Btn>
      <Btn
        label="Code block"
        active={editor.isActive("codeBlock")}
        onClick={() => editor.chain().focus().toggleCodeBlock().run()}
      >
        <Code className="size-4" />
      </Btn>

      <Divider />

      <ColorControl editor={editor} />
      <Btn
        label="Highlight"
        active={editor.isActive("highlight")}
        onClick={() => editor.chain().focus().toggleHighlight().run()}
      >
        <Highlighter className="size-4" />
      </Btn>

      <Divider />

      <Btn
        label="Insert math ($…$)"
        onClick={() => {
          editor.chain().focus().insertContent("$x$").run();
        }}
      >
        <Sigma className="size-4" />
      </Btn>
      <Btn
        label="Clear formatting"
        onClick={() =>
          editor.chain().focus().unsetAllMarks().clearNodes().run()
        }
      >
        <RemoveFormatting className="size-4" />
      </Btn>

      <Divider />

      <Btn
        label="Undo"
        disabled={!editor.can().undo()}
        onClick={() => editor.chain().focus().undo().run()}
      >
        <Undo2 className="size-4" />
      </Btn>
      <Btn
        label="Redo"
        disabled={!editor.can().redo()}
        onClick={() => editor.chain().focus().redo().run()}
      >
        <Redo2 className="size-4" />
      </Btn>
    </div>
  );
}

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

/** Font-color control: quick swatches + a native picker, with a reset. */
function ColorControl({ editor }: { editor: Editor }) {
  const [open, setOpen] = useState(false);
  const current = (editor.getAttributes("textStyle").color as string) || "#1e1e2e";

  return (
    <div className="relative">
      <Btn
        label="Font color"
        active={!!editor.getAttributes("textStyle").color}
        onClick={() => setOpen((o) => !o)}
      >
        <span className="flex flex-col items-center leading-none">
          <span className="text-[13px] font-semibold">A</span>
          <span
            className="mt-0.5 h-1 w-4 rounded-sm"
            style={{ backgroundColor: current }}
          />
        </span>
      </Btn>
      {open && (
        <>
          <div
            className="fixed inset-0 z-20"
            onClick={() => setOpen(false)}
            aria-hidden
          />
          <div className="absolute left-0 top-full z-30 mt-1 w-44 rounded-lg border bg-popover p-2 shadow-md">
            <div className="grid grid-cols-4 gap-1.5">
              {SWATCHES.map((c) => (
                <button
                  key={c}
                  type="button"
                  title={c}
                  className="size-7 rounded-md border transition hover:scale-110"
                  style={{ backgroundColor: c }}
                  onClick={() => {
                    editor.chain().focus().setColor(c).run();
                    setOpen(false);
                  }}
                />
              ))}
            </div>
            <div className="mt-2 flex items-center justify-between gap-2">
              <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
                <input
                  type="color"
                  className="size-6 cursor-pointer rounded border bg-transparent p-0"
                  onChange={(e) =>
                    editor.chain().focus().setColor(e.target.value).run()
                  }
                />
                Custom
              </label>
              <button
                type="button"
                className="text-xs text-muted-foreground underline-offset-2 hover:underline"
                onClick={() => {
                  editor.chain().focus().unsetColor().run();
                  setOpen(false);
                }}
              >
                Reset
              </button>
            </div>
          </div>
        </>
      )}
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

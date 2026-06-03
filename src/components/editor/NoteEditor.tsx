import { Color } from "@tiptap/extension-color";
import { FontFamily } from "@tiptap/extension-font-family";
import { Highlight } from "@tiptap/extension-highlight";
import { Mathematics } from "@tiptap/extension-mathematics";
import { TextStyle } from "@tiptap/extension-text-style";
import { Underline } from "@tiptap/extension-underline";
import { EditorContent, useEditor } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import { Markdown } from "tiptap-markdown";

import { EditorToolbar } from "./EditorToolbar";

// Inline `$…$` and block `$$…$$`. The first non-empty capture group is the LaTeX
// the extension feeds to KaTeX; the raw `$…$` text stays in the document, so it
// round-trips cleanly through markdown.
const MATH_REGEX = /\$\$([^$]+?)\$\$|\$([^$\n]+?)\$/g;

const extensions = [
  StarterKit,
  Underline,
  TextStyle,
  Color,
  // Per-selection font override (emits `<span style="font-family">`, kept on
  // save via Markdown html:true and rendered back by MarkdownView's rehype-raw).
  FontFamily,
  Highlight.configure({ multicolor: true }),
  Mathematics.configure({
    regex: MATH_REGEX,
    katexOptions: { throwOnError: false },
  }),
  // html:true so font color (`<span style="color">`) and highlight (`<mark>`),
  // which markdown can't express, survive serialization as inline HTML.
  Markdown.configure({ html: true, transformPastedText: true }),
];

/**
 * WYSIWYG note editor. Initialised from markdown, returns markdown on save.
 *
 * Mounted fresh per edit (so `initialMarkdown` is the source of truth once),
 * which is why there's no content sync effect.
 */
export function NoteEditor({
  initialMarkdown,
  onSave,
  onCancel,
  saving = false,
}: {
  initialMarkdown: string;
  onSave: (markdown: string) => void;
  onCancel: () => void;
  saving?: boolean;
}) {
  const editor = useEditor({
    extensions,
    content: initialMarkdown,
    autofocus: "end",
    editorProps: {
      attributes: {
        class:
          "prose prose-sm max-w-none px-4 py-3 focus:outline-none dark:prose-invert min-h-[12rem]",
      },
    },
  });

  if (!editor) return null;

  const save = () => onSave(editor.storage.markdown.getMarkdown());

  return (
    <div className="rounded-lg border bg-card shadow-sm">
      <EditorToolbar editor={editor} />
      <EditorContent editor={editor} />
      <div className="flex items-center justify-between gap-3 border-t px-3 py-2">
        <p className="text-xs text-muted-foreground">
          Type <code className="rounded bg-muted px-1">$E=mc^2$</code> for inline
          math, <code className="rounded bg-muted px-1">$$…$$</code> for a block.
        </p>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={onCancel}
            disabled={saving}
            className="rounded-md px-3 py-1.5 text-sm text-muted-foreground transition hover:bg-muted disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={save}
            disabled={saving}
            className="rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground shadow-sm transition hover:opacity-90 disabled:opacity-50"
          >
            {saving ? "Saving…" : "Save"}
          </button>
        </div>
      </div>
    </div>
  );
}

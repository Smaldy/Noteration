import ReactMarkdown from "react-markdown";
import rehypeKatex from "rehype-katex";
import rehypeRaw from "rehype-raw";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";

/**
 * Renders a note's markdown with native LaTeX and inline-HTML support.
 *
 * - `remark-math` + `rehype-katex` render `$inline$` and `$$block$$` math.
 * - `rehype-raw` keeps inline HTML (e.g. the `<span style="color">` and `<mark>`
 *   the editor emits for font color / highlight, which plain markdown can't
 *   express).
 * - `rehypeSanitizeRaw` (below) then strips the genuinely dangerous bits —
 *   `<script>`/frames, `on*` handlers, `javascript:` URLs — while leaving the
 *   editor's styled spans and KaTeX's own markup intact. Content here is authored
 *   by the user and the AI (from uploaded PDFs), so this neutralizes injection
 *   from a crafted document without breaking legitimate formatting or math.
 */

// hast node shapes we touch (kept local — avoids pulling in @types/hast).
interface HastElement {
  type: "element";
  tagName: string;
  properties?: Record<string, unknown>;
  children: HastNode[];
}
type HastNode =
  | HastElement
  | { type: string; children?: HastNode[]; [k: string]: unknown };

// Elements that can execute or load active content — dropped entirely.
const FORBIDDEN_TAGS = new Set([
  "script",
  "iframe",
  "object",
  "embed",
  "link",
  "meta",
  "base",
  "form",
  "style",
]);

// URL-bearing attributes whose value must not point at executable schemes.
const URL_ATTRS = new Set(["href", "src", "xlinkHref", "action", "formAction"]);

// Control chars + whitespace that browsers strip before resolving a URL scheme.
const URL_NOISE = /[\x00-\x20]/g;

function isElement(node: HastNode): node is HastElement {
  return node.type === "element";
}

function safeUrl(value: unknown): boolean {
  if (typeof value !== "string") return true;
  const v = value.replace(URL_NOISE, "").toLowerCase();
  return !v.startsWith("javascript:") && !v.startsWith("data:text/html");
}

function scrubElement(el: HastElement): void {
  const props = el.properties;
  if (!props) return;
  for (const key of Object.keys(props)) {
    // Event handlers (onClick, onError, …) — never keep them.
    if (key.toLowerCase().startsWith("on")) {
      delete props[key];
      continue;
    }
    // Active-scheme URLs.
    if (URL_ATTRS.has(key) && !safeUrl(props[key])) {
      delete props[key];
    }
  }
}

/** rehype transformer: prune forbidden tags and scrub unsafe attributes. */
function rehypeSanitizeRaw() {
  return (tree: HastNode) => {
    const walk = (node: HastNode) => {
      if (!Array.isArray(node.children)) return;
      node.children = node.children.filter(
        (child) => !(isElement(child) && FORBIDDEN_TAGS.has(child.tagName)),
      );
      for (const child of node.children) {
        if (isElement(child)) scrubElement(child);
        walk(child);
      }
    };
    walk(tree);
  };
}

export function MarkdownView({ children }: { children: string }) {
  return (
    <div className="prose prose-sm max-w-none dark:prose-invert">
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkMath]}
        // Order matters: raw HTML is parsed, then sanitized, then KaTeX injects
        // its own trusted markup (which must not be stripped by the sanitizer).
        // `throwOnError: false` keeps one malformed expression (common in
        // AI/PDF-extracted text) from blowing up the whole render — KaTeX shows
        // the offending source in red instead of throwing.
        rehypePlugins={[
          rehypeRaw,
          rehypeSanitizeRaw,
          [rehypeKatex, { throwOnError: false, strict: false }],
        ]}
      >
        {children}
      </ReactMarkdown>
    </div>
  );
}
